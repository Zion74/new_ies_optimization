"""Price-agnostic PCC exposure over alternate D19-admissible dispatches.

The joint model reopens the two architectures' dispatch decisions while
retaining their common annual PCC service and explicit annual cost and
curtailment caps.  It then minimizes or maximizes half of the annualized L1
distance between their PCC traces.  For any bounded period-price vector, this
quantity is the exact settlement-difference coefficient per unit price spread.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import sys
from dataclasses import asdict, dataclass, replace
from enum import Enum
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Sequence

from tes_bess_boundary.e0d17_exploration import (
    DEFAULT_WINDOWS,
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
    SOLVER_THREADS,
    E0D17WindowSpec,
    _base_case,
    _window_rows,
    load_e0d17_inputs,
)
from tes_bess_boundary.e0d18_performance import (
    EXACT_PRIMARY_MIP_GAP,
    FORTNIGHT_PRIMARY_MIP_GAP,
    PRIMARY_SOLVE_TIME_LIMIT_SECONDS,
    _solver,
    _tight_case,
)
from tes_bess_boundary.model import (
    AnnualCurtailmentServiceSpec,
    AnnualPCCExportServiceSpec,
    Architecture,
    E0CCase,
    build_e0c_model,
)
from tes_bess_boundary.solver import create_highs_solver


E0D23_SCHEMA = "tes_bess_boundary.e0d23_alternative_dispatch_envelope.v1"
E0D19_SCHEMA = "tes_bess_boundary.e0d19_same_pcc_service.v2"
E0D22_SCHEMA = "tes_bess_boundary.e0d22_pcc_settlement_exposure.v1"
E0D19_CSV_SHA256 = (
    "4b07e91b010fa9d5aa525f196037bbf0c93bae16ac74035f6ca32292e36cf786"
)
E0D19_MANIFEST_SHA256 = (
    "c112c210aa9a86edfcb116f614c1f4a5da14f314a128e31ee329fbefd65aab63"
)
E0D22_TRACE_SHA256 = (
    "ad196e3bce2c1f02287de74d42a61c91dd98f8703c753172f5acc014b655ccc2"
)
E0D22_EXPOSURE_SHA256 = (
    "3f84d3b0ee4ef03c9edb4ccf395bedc2291262f2cb5e82746a001bcdce5a319f"
)
E0D22_MANIFEST_SHA256 = (
    "74ed9edb644a40af1ca9ede489958a25e430fa3b87f8760e6bf6b358692b2f87"
)
_CANONICAL_FLOAT_DECIMALS = 9
_LOCKED_CSV_CAP_TOLERANCE = 1e-3
_SERVICE_AUDIT_TOLERANCE_MWH = 1e-4


class RedistributionDirection(str, Enum):
    """Extreme of annual PCC redistribution requested from the joint MILP."""

    MINIMUM = "minimum"
    MAXIMUM = "maximum"


@dataclass(frozen=True)
class DispatchAdmissibility:
    """Annual objective caps defining one architecture's admissible set."""

    primary_cost_upper_bound_cny: float
    curtailment_upper_bound_mwh: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.primary_cost_upper_bound_cny)
            or self.primary_cost_upper_bound_cny < 0.0
        ):
            raise ValueError("primary cost upper bound must be finite and non-negative")
        if (
            not math.isfinite(self.curtailment_upper_bound_mwh)
            or self.curtailment_upper_bound_mwh < 0.0
        ):
            raise ValueError(
                "curtailment upper bound must be finite and non-negative"
            )


@dataclass(frozen=True)
class RedistributionSolve:
    """One feasible extreme and its solver-certified objective bound."""

    direction: RedistributionDirection
    termination: str
    runtime_seconds: float
    primal_bound_mwh: float
    dual_bound_mwh: float
    relative_gap: float
    incumbent_redistribution_mwh: float
    comparator_cost_cny: float
    candidate_cost_cny: float
    comparator_curtailment_mwh: float
    candidate_curtailment_mwh: float
    comparator_pcc_export_mwh: float
    candidate_pcc_export_mwh: float
    annual_pcc_export_difference_mwh: float
    max_abs_period_delta_mw: float


@dataclass(frozen=True)
class E0D23Record:
    """Canonical price-agnostic envelope for one representative window."""

    window_id: str
    window_start: str
    hours: int
    annual_weight_per_hour: float
    common_pcc_export_mwh: float
    comparator_primary_cost_cap_cny: float
    candidate_primary_cost_cap_cny: float
    comparator_curtailment_cap_mwh: float
    candidate_curtailment_cap_mwh: float
    selected_d22_redistribution_mwh: float
    minimum_primal_bound_mwh: float
    minimum_dual_bound_mwh: float
    minimum_relative_gap: float
    minimum_termination: str
    maximum_primal_bound_mwh: float
    maximum_dual_bound_mwh: float
    maximum_relative_gap: float
    maximum_termination: str
    robust_settlement_upper_bound_cny_per_year_per_cny_per_mwh_spread: float
    selected_within_feasible_extremes: bool
    selected_within_certified_outer_envelope: bool
    minimum_comparator_cost_cny: float
    minimum_candidate_cost_cny: float
    minimum_comparator_curtailment_mwh: float
    minimum_candidate_curtailment_mwh: float
    maximum_comparator_cost_cny: float
    maximum_candidate_cost_cny: float
    maximum_comparator_curtailment_mwh: float
    maximum_candidate_curtailment_mwh: float
    max_annual_pcc_service_residual_mwh: float
    max_admissibility_violation: float
    maximum_extreme_max_abs_period_delta_mw: float
    primary_integer_patterns_reopened: bool
    actual_price_path_assigned: bool
    time_varying_settlement_complete: bool
    formal_tac: bool
    e1_ready: bool
    scientific_status: str


@dataclass(frozen=True)
class E0D23ExecutionRecord:
    window_id: str
    warm_start_runtime_seconds: float
    minimum_runtime_seconds: float
    maximum_runtime_seconds: float


@dataclass(frozen=True)
class E0D23Run:
    records: tuple[E0D23Record, ...]
    execution: tuple[E0D23ExecutionRecord, ...]
    heat_path: Path
    vre_path: Path
    d19_source_dir: Path
    d22_source_dir: Path
    time_limit_seconds: float
    threads: int


@dataclass(frozen=True)
class E0D23Export:
    csv_path: Path
    manifest_path: Path
    execution_path: Path
    canonical_sha256: dict[str, str]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _locked_csv_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = tuple(csv.DictReader(handle))
    if not rows or any(not row.get("window_id") for row in rows):
        raise ValueError(f"locked source has no keyed rows: {path.name}")
    keyed = {row["window_id"]: row for row in rows}
    if len(keyed) != len(rows):
        raise ValueError(f"locked source repeats a window_id: {path.name}")
    return keyed


def load_e0d23_source_rows(
    d19_source_dir: str | Path,
    d22_source_dir: str | Path,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """Validate immutable D19/D22 artifacts and return their keyed CSV rows."""

    d19_dir = Path(d19_source_dir)
    d22_dir = Path(d22_source_dir)
    d19_csv = d19_dir / "e0d19_same_pcc_service.csv"
    d19_manifest = d19_dir / "manifest.json"
    d22_trace = d22_dir / "e0d22_pcc_dispatch_trace.csv"
    d22_exposure = d22_dir / "e0d22_settlement_exposure.csv"
    d22_manifest = d22_dir / "manifest.json"
    required = (d19_csv, d19_manifest, d22_trace, d22_exposure, d22_manifest)
    if any(not path.is_file() for path in required):
        raise ValueError("D23 requires complete locked D19 and D22 source directories")
    if _sha256(d19_csv) != E0D19_CSV_SHA256:
        raise ValueError("D19 CSV hash does not match the D23 source lock")
    if _sha256(d19_manifest) != E0D19_MANIFEST_SHA256:
        raise ValueError("D19 manifest hash does not match the D23 source lock")
    if _sha256(d22_trace) != E0D22_TRACE_SHA256:
        raise ValueError("D22 trace hash does not match the D23 source lock")
    if _sha256(d22_exposure) != E0D22_EXPOSURE_SHA256:
        raise ValueError("D22 exposure hash does not match the D23 source lock")
    if _sha256(d22_manifest) != E0D22_MANIFEST_SHA256:
        raise ValueError("D22 manifest hash does not match the D23 source lock")

    d19_metadata = json.loads(d19_manifest.read_text(encoding="utf-8"))
    d22_metadata = json.loads(d22_manifest.read_text(encoding="utf-8"))
    if d19_metadata.get("schema") != E0D19_SCHEMA:
        raise ValueError("D19 manifest schema is incompatible with D23")
    if d22_metadata.get("schema") != E0D22_SCHEMA:
        raise ValueError("D22 manifest schema is incompatible with D23")
    if d19_metadata.get("output", {}).get("csv_sha256") != E0D19_CSV_SHA256:
        raise ValueError("D19 manifest lost its canonical CSV identity")
    d22_output = d22_metadata.get("output", {})
    if (
        d22_output.get("e0d22_pcc_dispatch_trace.csv", {}).get("sha256")
        != E0D22_TRACE_SHA256
        or d22_output.get("e0d22_settlement_exposure.csv", {}).get("sha256")
        != E0D22_EXPOSURE_SHA256
    ):
        raise ValueError("D22 manifest lost its canonical output identities")
    d19_rows = _locked_csv_rows(d19_csv)
    d22_rows = _locked_csv_rows(d22_exposure)
    if set(d19_rows) != set(d22_rows):
        raise ValueError("D19 and D22 locked windows do not match")
    return d19_rows, d22_rows


def _finite_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def legacy_primal_dual_bounds(
    results: object,
    direction: RedistributionDirection,
) -> tuple[float | None, float | None]:
    """Return ``(primal, dual)`` with correct min/max bound orientation."""

    if not isinstance(direction, RedistributionDirection):
        raise ValueError("direction must be a RedistributionDirection")
    lower = _finite_float(results.problem.lower_bound)
    upper = _finite_float(results.problem.upper_bound)
    if direction is RedistributionDirection.MINIMUM:
        return upper, lower
    return lower, upper


def _validate_joint_cases(
    comparator_case: E0CCase,
    candidate_case: E0CCase,
) -> tuple[tuple[float, ...], float, float]:
    if not isinstance(comparator_case, E0CCase) or not isinstance(
        candidate_case, E0CCase
    ):
        raise TypeError("joint redistribution requires two E0CCase values")
    if comparator_case.economics is None or candidate_case.economics is None:
        raise ValueError("joint redistribution requires annual economics")
    if (
        comparator_case.pcc_export_service is None
        or candidate_case.pcc_export_service is None
    ):
        raise ValueError("joint redistribution requires a common annual PCC service")
    comparator_periods = comparator_case.timeseries.period_count
    candidate_periods = candidate_case.timeseries.period_count
    if comparator_periods != candidate_periods:
        raise ValueError("joint cases must have the same period count")
    if not math.isclose(
        comparator_case.timeseries.dt_hours,
        candidate_case.timeseries.dt_hours,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("joint cases must have the same period duration")
    comparator_weights = tuple(
        comparator_case.economics.horizon.period_weights
    )
    candidate_weights = tuple(candidate_case.economics.horizon.period_weights)
    if comparator_weights != candidate_weights:
        raise ValueError("joint cases must have identical annual period weights")
    comparator_target = comparator_case.pcc_export_service.target_export_mwh
    candidate_target = candidate_case.pcc_export_service.target_export_mwh
    if not math.isclose(
        comparator_target, candidate_target, rel_tol=0.0, abs_tol=1e-5
    ):
        raise ValueError("joint cases must have the same annual PCC export target")
    if not math.isclose(
        comparator_case.pcc_export_capacity_mw,
        candidate_case.pcc_export_capacity_mw,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("joint cases must have the same PCC export capacity")
    return (
        comparator_weights,
        comparator_case.timeseries.dt_hours,
        comparator_case.pcc_export_capacity_mw,
    )


def build_joint_redistribution_model(
    comparator_case: E0CCase,
    candidate_case: E0CCase,
    *,
    comparator_admissibility: DispatchAdmissibility,
    candidate_admissibility: DispatchAdmissibility,
    direction: RedistributionDirection,
) -> object:
    """Build the exact min/max annual PCC-redistribution joint MILP."""

    from pyomo.environ import (
        Binary,
        Block,
        ConcreteModel,
        Constraint,
        Expression,
        NonNegativeReals,
        Objective,
        RangeSet,
        Var,
        maximize,
        minimize,
    )

    if not isinstance(comparator_admissibility, DispatchAdmissibility) or not isinstance(
        candidate_admissibility, DispatchAdmissibility
    ):
        raise TypeError("both joint cases require DispatchAdmissibility caps")
    if not isinstance(direction, RedistributionDirection):
        raise ValueError("direction must be a RedistributionDirection")
    annual_weights, dt_hours, pcc_capacity_mw = _validate_joint_cases(
        comparator_case, candidate_case
    )

    model = ConcreteModel(name=f"e0d23_{direction.value}_redistribution")
    model.comparator = Block()
    model.comparator.transfer_attributes_from(build_e0c_model(comparator_case))
    model.candidate = Block()
    model.candidate.transfer_attributes_from(build_e0c_model(candidate_case))
    model.comparator.validation_cost.deactivate()
    model.candidate.validation_cost.deactivate()

    model.comparator_primary_cost_cap = Constraint(
        expr=model.comparator.annual_total_cost_cny
        <= comparator_admissibility.primary_cost_upper_bound_cny
    )
    model.candidate_primary_cost_cap = Constraint(
        expr=model.candidate.annual_total_cost_cny
        <= candidate_admissibility.primary_cost_upper_bound_cny
    )
    model.comparator_curtailment_cap = Constraint(
        expr=model.comparator.annual_curtailment_mwh
        <= comparator_admissibility.curtailment_upper_bound_mwh
    )
    model.candidate_curtailment_cap = Constraint(
        expr=model.candidate.annual_curtailment_mwh
        <= candidate_admissibility.curtailment_upper_bound_mwh
    )

    period_count = comparator_case.timeseries.period_count
    model.redistribution_periods = RangeSet(0, period_count - 1)
    model.delta_pcc_export_mw = Expression(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.candidate.pcc_export[period]
            - block.comparator.pcc_export[period]
        ),
    )
    model.absolute_delta_pcc_export_mw = Var(
        model.redistribution_periods,
        domain=NonNegativeReals,
        bounds=(0.0, pcc_capacity_mw),
    )
    model.absolute_delta_lower_positive = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.absolute_delta_pcc_export_mw[period]
            >= block.delta_pcc_export_mw[period]
        ),
    )
    model.absolute_delta_lower_negative = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.absolute_delta_pcc_export_mw[period]
            >= -block.delta_pcc_export_mw[period]
        ),
    )
    if direction is RedistributionDirection.MAXIMUM:
        model.delta_nonnegative = Var(model.redistribution_periods, domain=Binary)
        model.absolute_delta_upper_positive = Constraint(
            model.redistribution_periods,
            rule=lambda block, period: (
                block.absolute_delta_pcc_export_mw[period]
                <= block.delta_pcc_export_mw[period]
                + 2.0 * pcc_capacity_mw * (1.0 - block.delta_nonnegative[period])
            ),
        )
        model.absolute_delta_upper_negative = Constraint(
            model.redistribution_periods,
            rule=lambda block, period: (
                block.absolute_delta_pcc_export_mw[period]
                <= -block.delta_pcc_export_mw[period]
                + 2.0 * pcc_capacity_mw * block.delta_nonnegative[period]
            ),
        )

    model.redistribution_objective = Objective(
        expr=0.5
        * dt_hours
        * sum(
            annual_weights[period]
            * model.absolute_delta_pcc_export_mw[period]
            for period in model.redistribution_periods
        ),
        sense=(
            minimize
            if direction is RedistributionDirection.MINIMUM
            else maximize
        ),
    )
    return model


def _solve_d19_selected_model(
    case: E0CCase,
    *,
    primary_mip_gap: float,
    pcc_service_feasibility_warm_start: bool,
) -> object:
    """Retain the D19-selected model state for a joint-MILP warm start."""

    from pyomo.environ import (
        Constraint,
        NonNegativeReals,
        Objective,
        Var,
        minimize,
        value,
    )

    model = build_e0c_model(case)
    solver = _solver(primary_mip_gap)

    def termination_name(results: object) -> str:
        raw = results.solver.termination_condition
        return getattr(raw, "name", str(raw)).lower()

    if pcc_service_feasibility_warm_start:
        service = case.pcc_export_service
        if service is None:
            raise ValueError("D19 warm start requires an annual PCC service")
        model.validation_cost.deactivate()
        model.annual_pcc_export_service.deactivate()
        model.pcc_service_abs_deviation_mw = Var(domain=NonNegativeReals)
        average_export_mw = (
            model.annual_pcc_export_mwh / model.annual_weighted_hours
        )
        target_average_export_mw = (
            service.target_export_mwh / model.annual_weighted_hours
        )
        model.pcc_service_deviation_upper = Constraint(
            expr=(
                average_export_mw - target_average_export_mw
                <= model.pcc_service_abs_deviation_mw
            )
        )
        model.pcc_service_deviation_lower = Constraint(
            expr=(
                target_average_export_mw - average_export_mw
                <= model.pcc_service_abs_deviation_mw
            )
        )
        model.pcc_service_feasibility_objective = Objective(
            expr=model.pcc_service_abs_deviation_mw,
            sense=minimize,
        )
        feasibility = solver.solve(model, tee=False)
        if termination_name(feasibility) != "optimal":
            raise RuntimeError("D23 could not reproduce the D19 PCC warm start")
        if float(value(model.pcc_service_abs_deviation_mw)) > 1e-9:
            raise RuntimeError("D23 D19 warm start retained nonzero PCC deviation")
        model.pcc_service_feasibility_objective.deactivate()
        model.pcc_service_deviation_upper.deactivate()
        model.pcc_service_deviation_lower.deactivate()
        model.annual_pcc_export_service.activate()
        model.validation_cost.activate()

    primary = solver.solve(
        model,
        tee=False,
        warmstart=pcc_service_feasibility_warm_start,
    )
    if termination_name(primary) != "optimal":
        raise RuntimeError("D23 could not reproduce the D19 primary dispatch")
    primary_cost = float(value(model.annual_total_cost_cny))
    primary_cost_tolerance = max(
        1e-6,
        10.0 * math.ulp(primary_cost),
        (
            1e-9 * abs(primary_cost)
            if pcc_service_feasibility_warm_start
            else 0.0
        ),
    )
    model.lexicographic_primary_cost_cap = Constraint(
        expr=model.annual_total_cost_cny
        <= primary_cost + primary_cost_tolerance
    )
    model.validation_cost.deactivate()
    model.lexicographic_curtailment_objective = Objective(
        expr=model.annual_curtailment_mwh,
        sense=minimize,
    )
    for variable in model.component_data_objects(Var, active=True):
        if variable.is_binary() or variable.is_integer():
            incumbent = value(variable, exception=False)
            if incumbent is None:
                raise RuntimeError("D19 warm start contains an unset integer variable")
            variable.fix(round(float(incumbent)))
    secondary = solver.solve(model, tee=False, warmstart=True)
    if termination_name(secondary) != "optimal":
        raise RuntimeError("D23 could not reproduce the D19 secondary dispatch")
    return model


def _copy_dispatch_values(source: object, target: object) -> None:
    from pyomo.environ import Var, value

    copied = 0
    for source_component in source.component_objects(Var, active=True):
        target_component = target.find_component(source_component.name)
        if target_component is None:
            continue
        for index in source_component:
            incumbent = value(source_component[index], exception=False)
            if incumbent is None:
                continue
            target_component[index].set_value(float(incumbent), skip_validation=True)
            copied += 1
    if copied == 0:
        raise RuntimeError("D23 failed to transfer a D19 warm-start state")


def _seed_joint_model(
    model: object,
    comparator_source: object,
    candidate_source: object,
) -> None:
    from pyomo.environ import value

    _copy_dispatch_values(comparator_source, model.comparator)
    _copy_dispatch_values(candidate_source, model.candidate)
    for period in model.redistribution_periods:
        delta = float(value(model.delta_pcc_export_mw[period]))
        model.absolute_delta_pcc_export_mw[period].set_value(abs(delta))
        if hasattr(model, "delta_nonnegative"):
            model.delta_nonnegative[period].set_value(1 if delta >= 0.0 else 0)


def solve_joint_redistribution(
    model: object,
    *,
    direction: RedistributionDirection,
    mip_rel_gap: float,
    time_limit_seconds: float,
    threads: int,
    warm_start: bool = False,
) -> RedistributionSolve:
    """Solve one joint extreme while retaining valid time-limit bounds."""

    from pyomo.environ import value

    if not isinstance(direction, RedistributionDirection):
        raise ValueError("direction must be a RedistributionDirection")
    if not math.isfinite(mip_rel_gap) or not 0.0 <= mip_rel_gap < 1.0:
        raise ValueError("mip_rel_gap must be finite and in [0, 1)")
    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0.0:
        raise ValueError("time_limit_seconds must be finite and positive")
    if type(threads) is not int or threads <= 0:
        raise ValueError("threads must be a positive integer")
    if not isinstance(warm_start, bool):
        raise ValueError("warm_start must be boolean")

    solver = create_highs_solver(
        threads=threads,
        random_seed=0,
        mip_rel_gap=mip_rel_gap,
    )
    solver.options["time_limit"] = time_limit_seconds
    started = perf_counter()
    results = solver.solve(
        model,
        tee=False,
        load_solutions=False,
        warmstart=warm_start,
    )
    runtime_seconds = perf_counter() - started
    raw_termination = results.solver.termination_condition
    termination = getattr(
        raw_termination, "name", str(raw_termination)
    ).lower()
    primal, dual = legacy_primal_dual_bounds(results, direction)
    if primal is None or dual is None or len(results.solution) == 0:
        raise RuntimeError(
            "joint redistribution solve did not return a feasible bounded incumbent: "
            f"{termination}"
        )
    model.solutions.load_from(results)
    incumbent = float(value(model.redistribution_objective))
    scale = max(abs(incumbent), abs(primal), 1.0)
    if abs(incumbent - primal) > 1e-6 * scale:
        raise RuntimeError("loaded joint incumbent does not match the primal bound")
    relative_gap = abs(primal - dual) / max(abs(primal), 1e-12)
    comparator_export = float(value(model.comparator.annual_pcc_export_mwh))
    candidate_export = float(value(model.candidate.annual_pcc_export_mwh))
    max_abs_delta = max(
        abs(float(value(model.delta_pcc_export_mw[period])))
        for period in model.redistribution_periods
    )
    return RedistributionSolve(
        direction=direction,
        termination=termination,
        runtime_seconds=runtime_seconds,
        primal_bound_mwh=primal,
        dual_bound_mwh=dual,
        relative_gap=relative_gap,
        incumbent_redistribution_mwh=incumbent,
        comparator_cost_cny=float(value(model.comparator.annual_total_cost_cny)),
        candidate_cost_cny=float(value(model.candidate.annual_total_cost_cny)),
        comparator_curtailment_mwh=float(
            value(model.comparator.annual_curtailment_mwh)
        ),
        candidate_curtailment_mwh=float(
            value(model.candidate.annual_curtailment_mwh)
        ),
        comparator_pcc_export_mwh=comparator_export,
        candidate_pcc_export_mwh=candidate_export,
        annual_pcc_export_difference_mwh=candidate_export - comparator_export,
        max_abs_period_delta_mw=max_abs_delta,
    )


def _window_mip_gap(window: E0D17WindowSpec) -> float:
    if window.hours == 24:
        return EXACT_PRIMARY_MIP_GAP
    if window.hours == 14 * 24:
        return FORTNIGHT_PRIMARY_MIP_GAP
    raise ValueError(f"no D23 gap policy is registered for {window.window_id}")


def _float_field(row: dict[str, str], field: str) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"locked source has invalid numeric field {field}") from exc
    if not math.isfinite(value):
        raise ValueError(f"locked source has non-finite numeric field {field}")
    return value


def _d19_admissibility(
    row: dict[str, str],
) -> tuple[DispatchAdmissibility, DispatchAdmissibility]:
    comparator = DispatchAdmissibility(
        primary_cost_upper_bound_cny=(
            _float_field(row, "comparator_primary_cost_cny")
            + _LOCKED_CSV_CAP_TOLERANCE
        ),
        curtailment_upper_bound_mwh=(
            _float_field(row, "comparator_curtailment_mwh")
            + _LOCKED_CSV_CAP_TOLERANCE
        ),
    )
    candidate = DispatchAdmissibility(
        primary_cost_upper_bound_cny=(
            _float_field(row, "candidate_primary_primal_bound_cny")
            + _float_field(row, "candidate_primary_cost_tolerance_cny")
            + _LOCKED_CSV_CAP_TOLERANCE
        ),
        curtailment_upper_bound_mwh=(
            _float_field(row, "candidate_curtailment_mwh")
            + _LOCKED_CSV_CAP_TOLERANCE
        ),
    )
    return comparator, candidate


def run_e0d23(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    d19_source_dir: str | Path,
    d22_source_dir: str | Path,
    windows: tuple[E0D17WindowSpec, ...] = DEFAULT_WINDOWS,
    time_limit_seconds: float = PRIMARY_SOLVE_TIME_LIMIT_SECONDS,
    threads: int = SOLVER_THREADS,
) -> E0D23Run:
    """Solve min/max settlement exposure over D19-admissible dispatches."""

    if not windows:
        raise ValueError("at least one D23 window is required")
    d19_rows, d22_rows = load_e0d23_source_rows(
        d19_source_dir, d22_source_dir
    )
    inputs = load_e0d17_inputs(heat_path, vre_path)
    records: list[E0D23Record] = []
    execution: list[E0D23ExecutionRecord] = []
    for window in windows:
        if window.window_id not in d19_rows:
            raise ValueError(f"D23 window is absent from D19: {window.window_id}")
        d19 = d19_rows[window.window_id]
        d22 = d22_rows[window.window_id]
        if int(d19["hours"]) != window.hours or int(d22["hours"]) != window.hours:
            raise ValueError("locked source hours do not match the requested D23 window")
        rows = _window_rows(inputs, window)
        curtailment_service = AnnualCurtailmentServiceSpec(
            service_id=d19["curtailment_service_id"],
            maximum_curtailment_mwh=_float_field(
                d19, "service_curtailment_ceiling_mwh"
            ),
        )
        pcc_service = AnnualPCCExportServiceSpec(
            service_id=d19["pcc_export_service_id"],
            target_export_mwh=_float_field(d19, "pcc_export_target_mwh"),
        )
        comparator_case = replace(
            _tight_case(
                _base_case(
                    rows,
                    architecture=Architecture.NO_STORAGE,
                    service=curtailment_service,
                )
            ),
            pcc_export_service=pcc_service,
        )
        candidate_case = replace(
            _tight_case(
                _base_case(
                    rows,
                    architecture=Architecture.TES,
                    service=curtailment_service,
                )
            ),
            pcc_export_service=pcc_service,
        )
        comparator_admissibility, candidate_admissibility = _d19_admissibility(
            d19
        )
        mip_gap = _window_mip_gap(window)
        comparator_warm_model = None
        candidate_warm_model = None
        warm_start_runtime_seconds = 0.0
        if window.hours > 24:
            warm_started = perf_counter()
            comparator_warm_model = _solve_d19_selected_model(
                comparator_case,
                primary_mip_gap=EXACT_PRIMARY_MIP_GAP,
                pcc_service_feasibility_warm_start=False,
            )
            candidate_warm_model = _solve_d19_selected_model(
                candidate_case,
                primary_mip_gap=mip_gap,
                pcc_service_feasibility_warm_start=True,
            )
            warm_start_runtime_seconds = perf_counter() - warm_started
        minimum_model = build_joint_redistribution_model(
            comparator_case,
            candidate_case,
            comparator_admissibility=comparator_admissibility,
            candidate_admissibility=candidate_admissibility,
            direction=RedistributionDirection.MINIMUM,
        )
        if comparator_warm_model is not None and candidate_warm_model is not None:
            _seed_joint_model(
                minimum_model,
                comparator_warm_model,
                candidate_warm_model,
            )
        minimum = solve_joint_redistribution(
            minimum_model,
            direction=RedistributionDirection.MINIMUM,
            mip_rel_gap=mip_gap,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
            warm_start=(comparator_warm_model is not None),
        )
        maximum_model = build_joint_redistribution_model(
            comparator_case,
            candidate_case,
            comparator_admissibility=comparator_admissibility,
            candidate_admissibility=candidate_admissibility,
            direction=RedistributionDirection.MAXIMUM,
        )
        if comparator_warm_model is not None and candidate_warm_model is not None:
            _seed_joint_model(
                maximum_model,
                comparator_warm_model,
                candidate_warm_model,
            )
        maximum = solve_joint_redistribution(
            maximum_model,
            direction=RedistributionDirection.MAXIMUM,
            mip_rel_gap=mip_gap,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
            warm_start=(comparator_warm_model is not None),
        )
        selected = _float_field(d22, "redistributed_export_mwh")
        comparison_tolerance = max(
            _SERVICE_AUDIT_TOLERANCE_MWH,
            1e-9 * max(selected, maximum.dual_bound_mwh, 1.0),
        )
        feasible_extremes = (
            minimum.primal_bound_mwh - comparison_tolerance
            <= selected
            <= maximum.primal_bound_mwh + comparison_tolerance
        )
        certified_outer = (
            minimum.dual_bound_mwh - comparison_tolerance
            <= selected
            <= maximum.dual_bound_mwh + comparison_tolerance
        )
        service_residual = max(
            abs(minimum.annual_pcc_export_difference_mwh),
            abs(maximum.annual_pcc_export_difference_mwh),
            abs(minimum.comparator_pcc_export_mwh - pcc_service.target_export_mwh),
            abs(minimum.candidate_pcc_export_mwh - pcc_service.target_export_mwh),
            abs(maximum.comparator_pcc_export_mwh - pcc_service.target_export_mwh),
            abs(maximum.candidate_pcc_export_mwh - pcc_service.target_export_mwh),
        )
        if service_residual > _SERVICE_AUDIT_TOLERANCE_MWH:
            raise RuntimeError("D23 joint extreme lost the common annual PCC service")
        admissibility_violation = max(
            0.0,
            minimum.comparator_cost_cny
            - comparator_admissibility.primary_cost_upper_bound_cny,
            minimum.candidate_cost_cny
            - candidate_admissibility.primary_cost_upper_bound_cny,
            minimum.comparator_curtailment_mwh
            - comparator_admissibility.curtailment_upper_bound_mwh,
            minimum.candidate_curtailment_mwh
            - candidate_admissibility.curtailment_upper_bound_mwh,
            maximum.comparator_cost_cny
            - comparator_admissibility.primary_cost_upper_bound_cny,
            maximum.candidate_cost_cny
            - candidate_admissibility.primary_cost_upper_bound_cny,
            maximum.comparator_curtailment_mwh
            - comparator_admissibility.curtailment_upper_bound_mwh,
            maximum.candidate_curtailment_mwh
            - candidate_admissibility.curtailment_upper_bound_mwh,
        )
        if admissibility_violation > _LOCKED_CSV_CAP_TOLERANCE:
            raise RuntimeError("D23 joint extreme violates a D19 admissibility cap")
        exact = (
            minimum.termination == "optimal"
            and maximum.termination == "optimal"
            and minimum.relative_gap <= 1e-12
            and maximum.relative_gap <= 1e-12
        )
        records.append(
            E0D23Record(
                window_id=window.window_id,
                window_start=window.start.isoformat(timespec="seconds"),
                hours=window.hours,
                annual_weight_per_hour=8_784.0 / window.hours,
                common_pcc_export_mwh=pcc_service.target_export_mwh,
                comparator_primary_cost_cap_cny=(
                    comparator_admissibility.primary_cost_upper_bound_cny
                ),
                candidate_primary_cost_cap_cny=(
                    candidate_admissibility.primary_cost_upper_bound_cny
                ),
                comparator_curtailment_cap_mwh=(
                    comparator_admissibility.curtailment_upper_bound_mwh
                ),
                candidate_curtailment_cap_mwh=(
                    candidate_admissibility.curtailment_upper_bound_mwh
                ),
                selected_d22_redistribution_mwh=selected,
                minimum_primal_bound_mwh=minimum.primal_bound_mwh,
                minimum_dual_bound_mwh=max(0.0, minimum.dual_bound_mwh),
                minimum_relative_gap=minimum.relative_gap,
                minimum_termination=minimum.termination,
                maximum_primal_bound_mwh=maximum.primal_bound_mwh,
                maximum_dual_bound_mwh=maximum.dual_bound_mwh,
                maximum_relative_gap=maximum.relative_gap,
                maximum_termination=maximum.termination,
                robust_settlement_upper_bound_cny_per_year_per_cny_per_mwh_spread=(
                    maximum.dual_bound_mwh
                ),
                selected_within_feasible_extremes=feasible_extremes,
                selected_within_certified_outer_envelope=certified_outer,
                minimum_comparator_cost_cny=minimum.comparator_cost_cny,
                minimum_candidate_cost_cny=minimum.candidate_cost_cny,
                minimum_comparator_curtailment_mwh=(
                    minimum.comparator_curtailment_mwh
                ),
                minimum_candidate_curtailment_mwh=(
                    minimum.candidate_curtailment_mwh
                ),
                maximum_comparator_cost_cny=maximum.comparator_cost_cny,
                maximum_candidate_cost_cny=maximum.candidate_cost_cny,
                maximum_comparator_curtailment_mwh=(
                    maximum.comparator_curtailment_mwh
                ),
                maximum_candidate_curtailment_mwh=(
                    maximum.candidate_curtailment_mwh
                ),
                max_annual_pcc_service_residual_mwh=service_residual,
                max_admissibility_violation=admissibility_violation,
                maximum_extreme_max_abs_period_delta_mw=(
                    maximum.max_abs_period_delta_mw
                ),
                primary_integer_patterns_reopened=True,
                actual_price_path_assigned=False,
                time_varying_settlement_complete=False,
                formal_tac=False,
                e1_ready=False,
                scientific_status=(
                    "exact_alternative_dispatch_envelope_not_formal_tac"
                    if exact
                    else "bounded_alternative_dispatch_envelope_not_formal_tac"
                ),
            )
        )
        execution.append(
            E0D23ExecutionRecord(
                window_id=window.window_id,
                warm_start_runtime_seconds=warm_start_runtime_seconds,
                minimum_runtime_seconds=minimum.runtime_seconds,
                maximum_runtime_seconds=maximum.runtime_seconds,
            )
        )
    return E0D23Run(
        records=tuple(records),
        execution=tuple(execution),
        heat_path=Path(heat_path),
        vre_path=Path(vre_path),
        d19_source_dir=Path(d19_source_dir),
        d22_source_dir=Path(d22_source_dir),
        time_limit_seconds=time_limit_seconds,
        threads=threads,
    )


def _json_ready(value: object) -> object:
    if isinstance(value, float):
        rounded = round(value, 12)
        return 0.0 if rounded == 0.0 else rounded
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _csv_value(value: object) -> object:
    if isinstance(value, float):
        return f"{value:.{_CANONICAL_FLOAT_DECIMALS}f}"
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def write_e0d23(run: E0D23Run, output_dir: str | Path) -> E0D23Export:
    """Write canonical D23 bounds plus a noncanonical runtime sidecar."""

    if not isinstance(run, E0D23Run) or not run.records:
        raise ValueError("run must contain E0-D-23 records")
    load_e0d23_source_rows(run.d19_source_dir, run.d22_source_dir)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    csv_path = destination / "e0d23_alternative_dispatch_envelope.csv"
    manifest_path = destination / "manifest.json"
    execution_path = destination / "execution.json"
    field_names = tuple(asdict(run.records[0]))
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_names, lineterminator="\n")
        writer.writeheader()
        for record in run.records:
            writer.writerow(
                {key: _csv_value(value) for key, value in asdict(record).items()}
            )
    csv_hash = _sha256(csv_path)
    source_dir = Path(__file__).resolve().parent
    source_names = (
        "alternative_dispatch_envelope.py",
        "e0d19_same_pcc_service.py",
        "e0d18_performance.py",
        "model.py",
        "solver.py",
        "components/chp.py",
        "components/molten_salt.py",
    )
    manifest = _json_ready(
        {
            "schema": E0D23_SCHEMA,
            "scientific_scope": (
                "alternative_dispatch_price_spread_envelope_not_formal_tac_not_e1"
            ),
            "d19_source_lock": {
                "csv_sha256": E0D19_CSV_SHA256,
                "manifest_sha256": E0D19_MANIFEST_SHA256,
            },
            "d22_source_lock": {
                "trace_sha256": E0D22_TRACE_SHA256,
                "exposure_sha256": E0D22_EXPOSURE_SHA256,
                "manifest_sha256": E0D22_MANIFEST_SHA256,
            },
            "inputs": {
                "formal_heat": {
                    "file": run.heat_path.name,
                    "sha256": _sha256(run.heat_path),
                    "locked_sha256": FORMAL_HEAT_SHA256,
                },
                "renewable_shape": {
                    "file": run.vre_path.name,
                    "sha256": _sha256(run.vre_path),
                    "locked_sha256": LEGACY_VRE_SHA256,
                    "status": "legacy_2019_resource_year_mapped_to_2024_calendar",
                },
            },
            "admissibility_contract": {
                "common_heat_and_renewable_inputs": True,
                "common_annual_pcc_service": True,
                "cost_cap": (
                    "comparator:D19_exact_selected_cost;candidate:D19_primary_"
                    "primal_bound_plus_D19_primary_tolerance;both_plus_locked_"
                    "CSV_rounding_tolerance"
                ),
                "curtailment_cap": (
                    "D19_selected_secondary_curtailment_plus_locked_CSV_"
                    "rounding_tolerance"
                ),
                "locked_csv_rounding_tolerance": _LOCKED_CSV_CAP_TOLERANCE,
                "primary_integer_patterns_reopened": True,
                "interpretation": (
                    "conservative_superset_of_D19_fixed_primary_integer_"
                    "secondary_dispatch_face"
                ),
            },
            "mathematical_contract": {
                "redistribution_mwh": (
                    "0.5*sum_t(period_weight_t*dt*abs(P_candidate_t-P_comparator_t))"
                ),
                "same_service_identity": "sum_t(delta_E_t)=0",
                "bounded_price_identity": (
                    "abs(settlement_delta)<=price_spread*redistribution_mwh"
                ),
                "minimum": "MILP_minimum_over_D19_admissible_joint_dispatches",
                "maximum": "exact_big_M_MILP_maximum_over_D19_admissible_joint_dispatches",
                "robust_upper_coefficient": "maximum_dual_bound_mwh",
            },
            "solver_contract": {
                "solver": "appsi_highs",
                "threads": run.threads,
                "random_seed": 0,
                "time_limit_seconds_per_extreme": run.time_limit_seconds,
                "mip_gap_by_hours": {
                    "24": EXACT_PRIMARY_MIP_GAP,
                    "336": FORTNIGHT_PRIMARY_MIP_GAP,
                },
                "incomplete_maximization": (
                    "primal_is_feasible_lower_bound;dual_is_certified_upper_bound"
                ),
                "incomplete_minimization": (
                    "primal_is_feasible_upper_bound;dual_is_certified_lower_bound"
                ),
                "joint_warm_start_336h": (
                    "reproduce_D19_PCC_feasibility_then_primary_cost_then_fixed_"
                    "integer_secondary_dispatch_and_copy_values_only;admissible_"
                    "constraints_and_extreme_objectives_unchanged"
                ),
            },
            "scientific_boundary": {
                "actual_price_path_assigned": False,
                "time_varying_settlement_complete": False,
                "formal_tac": False,
                "e1_ready": False,
            },
            "sources": {name: _sha256(source_dir / name) for name in source_names},
            "windows": [
                {
                    "window_id": record.window_id,
                    "hours": record.hours,
                    "scientific_status": record.scientific_status,
                }
                for record in run.records
            ],
            "output": {
                "csv": csv_path.name,
                "rows": len(run.records),
                "float_decimals": _CANONICAL_FLOAT_DECIMALS,
                "csv_sha256": csv_hash,
            },
        }
    )
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
        )
        handle.write("\n")
    execution = {
        "schema": f"{E0D23_SCHEMA}.execution",
        "noncanonical": True,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "pyomo": version("pyomo"),
            "highspy": version("highspy"),
        },
        "records": [asdict(record) for record in run.execution],
    }
    with execution_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                _json_ready(execution),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        handle.write("\n")
    return E0D23Export(
        csv_path=csv_path,
        manifest_path=manifest_path,
        execution_path=execution_path,
        canonical_sha256={
            csv_path.name: csv_hash,
            manifest_path.name: _sha256(manifest_path),
        },
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the E0-D-23 alternate-dispatch PCC exposure envelope."
    )
    parser.add_argument("--heat-path", required=True, type=Path)
    parser.add_argument("--vre-path", required=True, type=Path)
    parser.add_argument("--d19-source-dir", required=True, type=Path)
    parser.add_argument("--d22-source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--window",
        action="append",
        choices=tuple(window.window_id for window in DEFAULT_WINDOWS),
    )
    parser.add_argument(
        "--time-limit-seconds",
        type=float,
        default=PRIMARY_SOLVE_TIME_LIMIT_SECONDS,
    )
    arguments = parser.parse_args(argv)
    selected = tuple(
        window
        for window in DEFAULT_WINDOWS
        if arguments.window is None or window.window_id in arguments.window
    )
    run = run_e0d23(
        arguments.heat_path,
        arguments.vre_path,
        d19_source_dir=arguments.d19_source_dir,
        d22_source_dir=arguments.d22_source_dir,
        windows=selected,
        time_limit_seconds=arguments.time_limit_seconds,
    )
    export = write_e0d23(run, arguments.output)
    print(
        json.dumps(
            {
                "schema": E0D23_SCHEMA,
                "records": len(run.records),
                "canonical_sha256": export.canonical_sha256,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
