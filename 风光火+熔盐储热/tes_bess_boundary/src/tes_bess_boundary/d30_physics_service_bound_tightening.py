"""Physics- and service-derived PCC bounds for the open global L1 problem.

E0-D-30 constructs a separable per-period relaxation of each D19 architecture.
It retains the CHP table-vertex region, renewable availability, heat balance,
PCC balance, storage port caps, and a conservative TES auxiliary upper bound.
Inter-period inventory, commitment, ramp, cost, and curtailment constraints are
omitted.  The resulting PCC intervals therefore contain the projection of the
full D19 feasible set.  The common annual export identity then propagates
those intervals before exact sign-valid inequalities are added to the D29
joint model.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter
from typing import Sequence

from tes_bess_boundary.alternative_dispatch_envelope import (
    RedistributionDirection,
    _seed_joint_model,
    _solve_d19_selected_model,
    build_joint_redistribution_model,
    load_e0d23_source_rows,
)
from tes_bess_boundary.d26_numerical_certification import (
    KNOWN_WITNESS_TOLERANCE_MWH,
    STRICT_FEASIBILITY_TOLERANCE,
    IntegerScope,
    _build_cases,
    _fix_integer_pattern,
    _strict_solve,
    _window_mip_gap,
)
from tes_bess_boundary.d27_direction_generation import (
    _replace_big_m_with_disaggregated_sign_formulation,
    _seed_joint_from_joint,
)
from tes_bess_boundary.d29_certification_bundle import D29_BUNDLE_SCHEMA
from tes_bess_boundary.d29_export_linked_bound_tightening import (
    D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH,
    add_export_linked_sign_cuts,
)
from tes_bess_boundary.e0d17_exploration import (
    DEFAULT_WINDOWS,
    E0D17WindowSpec,
    _window_rows,
    load_e0d17_inputs,
)
from tes_bess_boundary.model import Architecture, E0CCase, TESFixedSpec
from tes_bess_boundary.solver import create_highs_solver


D30_SCREEN_SCHEMA = "tes_bess_boundary.e0d30_physics_service_bound_screen.v1"
D30_PROBE_SCHEMA = "tes_bess_boundary.e0d30_physics_service_bound_probe.v1"
D30_BOUND_SAFETY_MARGIN_MW = 1e-4


@dataclass(frozen=True)
class PCCReachableBounds:
    """Numerically certified per-period PCC interval from one relaxation."""

    architecture: str
    periods: int
    lower_mw: tuple[float, ...]
    upper_mw: tuple[float, ...]
    minimum_termination: str
    maximum_termination: str
    minimum_runtime_seconds: float
    maximum_runtime_seconds: float
    safety_margin_mw: float
    relaxation_contract: str = (
        "static_period_separable_outer_relaxation_of_full_d19_dispatch"
    )


@dataclass(frozen=True)
class D30BoundAudit:
    """Deterministic summary of interval and sign-width tightening."""

    periods: int
    per_period_cut_count: int
    comparator_mean_width_before_service_mw: float
    comparator_mean_width_after_service_mw: float
    candidate_mean_width_before_service_mw: float
    candidate_mean_width_after_service_mw: float
    mean_positive_sign_width_mw: float
    mean_negative_sign_width_mw: float
    maximum_positive_sign_width_mw: float
    maximum_negative_sign_width_mw: float
    positive_sign_width_reduction_fraction: float
    negative_sign_width_reduction_fraction: float
    pcc_capacity_mw: float
    bound_safety_margin_mw: float
    primary_integer_patterns_reopened: bool = True
    sign_binaries_reopened: bool = True
    feasible_set_changed_for_integer_solutions: bool = False


@dataclass(frozen=True)
class D30BoundScreen:
    """Bounds-only screening artifact produced before any long global solve."""

    schema: str
    window_id: str
    hours: int
    target_export_mwh: float
    comparator_raw: PCCReachableBounds
    candidate_raw: PCCReachableBounds
    comparator_service_lower_mw: tuple[float, ...]
    comparator_service_upper_mw: tuple[float, ...]
    candidate_service_lower_mw: tuple[float, ...]
    candidate_service_upper_mw: tuple[float, ...]
    bound_audit: D30BoundAudit
    actual_price_path_assigned: bool = False
    formal_tac: bool = False
    e1_ready: bool = False


@dataclass(frozen=True)
class D29MaximumReference:
    """Hash-verified strict global interval promoted from D29."""

    window_id: str
    hours: int
    strict_global_lower_bound_mwh: float
    strict_global_upper_bound_mwh: float
    csv_sha256: str
    manifest_sha256: str


@dataclass(frozen=True)
class D30GlobalProbe:
    """One reopened exact-L1 solve with D29 and D30 valid inequalities."""

    schema: str
    window_id: str
    hours: int
    threads: int
    time_limit_seconds: float
    reference_d29_lower_bound_mwh: float
    reference_d29_upper_bound_mwh: float
    reference_d29_csv_sha256: str
    reference_d29_manifest_sha256: str
    selected_face_witness_mwh: float
    selected_face_termination: str
    selected_face_bound_certificate_complete: bool
    known_witness_within_bounds: bool
    bound_audit: D30BoundAudit
    termination: str
    runtime_seconds: float
    primal_bound_mwh: float
    recomputed_redistribution_mwh: float
    witness_reference_excess_mwh: float
    witness_clamped_to_reference: bool
    dual_bound_mwh: float | None
    dual_reference_deficit_mwh: float | None
    dual_clamped_to_reference_lower: bool
    relative_gap: float | None
    bound_certificate_complete: bool
    witness_dominance_passed: bool
    maximum_positive_normalized_constraint_residual: float
    auxiliary_objective_mismatch_mwh: float
    strict_global_lower_bound_mwh: float
    strict_global_upper_bound_mwh: float
    global_upper_bound_improvement_mwh: float
    global_upper_bound_improvement_fraction: float
    global_upper_bound_improved: bool
    exact_global_maximum: bool
    global_dual_is_valid_l1_upper_bound: bool
    actual_price_path_assigned: bool = False
    formal_tac: bool = False
    e1_ready: bool = False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_csv_float(row: dict[str, str], key: str, *, label: str) -> float:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} has no finite {key}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label} has no finite {key}")
    return value


def load_d29_maximum_reference(
    source_dir: str | Path,
    *,
    window_id: str,
) -> D29MaximumReference:
    """Load one hash-verified D29 strict maximum interval."""

    source = Path(source_dir)
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("D30 is missing the D29 manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != D29_BUNDLE_SCHEMA:
        raise ValueError("D30 D29 manifest schema mismatch")
    output = manifest.get("output")
    if not isinstance(output, dict):
        raise ValueError("D30 D29 manifest has no output contract")
    csv_name = output.get("csv")
    expected_hash = output.get("csv_sha256")
    if not isinstance(csv_name, str) or not isinstance(expected_hash, str):
        raise ValueError("D30 D29 output contract is incomplete")
    csv_path = source / csv_name
    if not csv_path.is_file() or _sha256(csv_path) != expected_hash:
        raise ValueError("D30 D29 certificate hash mismatch")
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = tuple(csv.DictReader(handle))
    matches = tuple(row for row in rows if row.get("window_id") == window_id)
    if len(matches) != 1:
        raise ValueError(f"D30 needs exactly one D29 row for {window_id}")
    row = matches[0]
    if row.get("global_dual_is_valid_l1_upper_bound") != "true":
        raise ValueError("D30 D29 reference lacks a valid global L1 upper bound")
    lower = _finite_csv_float(
        row, "strict_global_lower_bound_mwh", label=window_id
    )
    upper = _finite_csv_float(
        row, "strict_global_upper_bound_mwh", label=window_id
    )
    if upper + KNOWN_WITNESS_TOLERANCE_MWH < lower:
        raise ValueError("D30 D29 reference interval is reversed")
    return D29MaximumReference(
        window_id=window_id,
        hours=int(row["hours"]),
        strict_global_lower_bound_mwh=lower,
        strict_global_upper_bound_mwh=upper,
        csv_sha256=expected_hash,
        manifest_sha256=_sha256(manifest_path),
    )


def _finite_bounds(values: Sequence[float], *, label: str) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if not result or any(not math.isfinite(value) for value in result):
        raise ValueError(f"{label} must contain finite values")
    return result


def _tes_auxiliary_upper_bounds(
    tes: TESFixedSpec,
    *,
    dt_hours: float,
    ambient_temperature_c: Sequence[float | None],
) -> tuple[float, ...]:
    """Return conservative period-specific TES auxiliary-power upper bounds."""

    physics = tes.physics
    caps = tes.port_caps
    loss = tes.loss_auxiliary
    if loss is None:
        return (0.0,) * len(tuple(ambient_temperature_c))
    ambient = tuple(ambient_temperature_c)
    inventory_flow_bound = physics.salt_mass_t / dt_hours
    cp = physics.specific_heat_mwh_per_tonne_k
    electric_flow = min(
        inventory_flow_bound,
        caps.electric_charge_input_mw
        * physics.electric_heater_efficiency
        / (cp * (physics.temperature_ht - physics.temperature_lt)),
    )
    steam_ht_flow = min(
        inventory_flow_bound,
        caps.steam_to_ht_reference_input_mw
        * physics.steam_to_ht_efficiency
        / (cp * (physics.temperature_ht - physics.temperature_lt)),
    )
    steam_mt_flow = min(
        inventory_flow_bound,
        caps.steam_to_mt_reference_input_mw
        * physics.steam_to_mt_efficiency
        / (cp * physics.delta_mt_lt),
    )
    power_flow = min(
        inventory_flow_bound,
        caps.electric_output_mw
        / (physics.power_block_efficiency * cp * physics.delta_ht_mt),
    )
    heat_flow = min(
        inventory_flow_bound,
        caps.heat_output_mw
        / (physics.heat_exchanger_efficiency * cp * physics.delta_mt_lt),
    )
    pump_upper = float(
        loss.pump.electric_power_mw(
            electric_lt_to_ht_tph=electric_flow,
            steam_lt_to_ht_tph=steam_ht_flow,
            steam_lt_to_mt_tph=steam_mt_flow,
            power_ht_to_mt_tph=power_flow,
            heat_mt_to_lt_tph=heat_flow,
        )
    )
    result: list[float] = []
    for temperature in ambient:
        resolved_ambient = (
            loss.reference_ambient_temperature_c
            if temperature is None
            else float(temperature)
        )
        raw_ht_upper = loss.ht_loss_flow_coefficient(
            dt_hours=dt_hours,
            state_temperature_c=physics.temperature_ht,
            ambient_temperature_c=resolved_ambient,
        ) * physics.ht_tank_capacity_t
        raw_mt_upper = loss.mt_loss_flow_coefficient(
            dt_hours=dt_hours,
            state_temperature_c=physics.temperature_mt,
            ambient_temperature_c=resolved_ambient,
        ) * physics.mt_tank_capacity_t
        tracing_upper = (
            cp
            * (
                physics.delta_ht_mt
                * loss.ht_loss_compensation_fraction
                * raw_ht_upper
                + physics.delta_mt_lt
                * loss.mt_loss_compensation_fraction
                * raw_mt_upper
            )
            / loss.tracing_heater_efficiency
        )
        result.append(max(0.0, tracing_upper + pump_upper))
    return tuple(result)


def build_static_pcc_relaxation(case: E0CCase, *, maximize_pcc: bool) -> object:
    """Build one separable outer relaxation for all periods of one case."""

    from pyomo.environ import (
        Binary,
        ConcreteModel,
        Constraint,
        Expression,
        NonNegativeReals,
        Objective,
        RangeSet,
        Set,
        Var,
        maximize,
        minimize,
    )

    if case.architecture not in (Architecture.NO_STORAGE, Architecture.TES):
        raise ValueError("D30 supports only the D19 no-storage and TES architectures")
    if case.bess is not None:
        raise ValueError("D30 static relaxation does not admit a BESS block")
    period_count = case.timeseries.period_count
    model = ConcreteModel(name=f"e0d30_{case.architecture.value}_static_pcc")
    model.periods = RangeSet(0, period_count - 1)
    model.units = RangeSet(0, len(case.chp_units) - 1)
    pairs = tuple(
        (unit, vertex)
        for unit, spec in enumerate(case.chp_units)
        for vertex in range(len(spec.feasible_region.vertices))
    )
    model.unit_vertex_pairs = Set(dimen=2, initialize=pairs)
    model.online = Var(model.periods, model.units, domain=Binary)
    model.vertex_weight = Var(
        model.periods,
        model.unit_vertex_pairs,
        domain=NonNegativeReals,
    )
    model.weight_sum = Constraint(
        model.periods,
        model.units,
        rule=lambda block, period, unit: sum(
            block.vertex_weight[period, unit, vertex]
            for vertex in range(
                len(case.chp_units[int(unit)].feasible_region.vertices)
            )
        )
        == block.online[period, unit],
    )
    model.chp_gross_total = Expression(
        model.periods,
        rule=lambda block, period: sum(
            case.chp_units[int(unit)]
            .feasible_region.vertices[int(vertex)]
            .power_gross_mw
            * block.vertex_weight[period, unit, vertex]
            for unit, vertex in pairs
        ),
    )
    model.chp_heat_total = Expression(
        model.periods,
        rule=lambda block, period: sum(
            case.chp_units[int(unit)].feasible_region.vertices[int(vertex)].heat_mw
            * block.vertex_weight[period, unit, vertex]
            for unit, vertex in pairs
        ),
    )
    model.chp_auxiliary_total = Expression(
        model.periods,
        rule=lambda block, period: sum(
            case.chp_units[int(unit)].auxiliary_rate
            * case.chp_units[int(unit)]
            .feasible_region.vertices[int(vertex)]
            .power_gross_mw
            * block.vertex_weight[period, unit, vertex]
            for unit, vertex in pairs
        ),
    )
    model.wind_used = Var(
        model.periods,
        domain=NonNegativeReals,
        bounds=lambda _block, period: (
            0.0,
            case.timeseries.wind_available_mw[int(period)],
        ),
    )
    model.pv_used = Var(
        model.periods,
        domain=NonNegativeReals,
        bounds=lambda _block, period: (
            0.0,
            case.timeseries.pv_available_mw[int(period)],
        ),
    )
    model.pcc_export = Var(
        model.periods,
        bounds=(0.0, case.pcc_export_capacity_mw),
    )
    model.direct_heat = Var(model.periods, domain=NonNegativeReals)

    if case.tes is None:
        electric_charge_cap = 0.0
        steam_ht_cap = 0.0
        steam_mt_cap = 0.0
        electric_output_cap = 0.0
        heat_output_cap = 0.0
        auxiliary_upper = (0.0,) * period_count
    else:
        caps = case.tes.port_caps
        electric_charge_cap = caps.electric_charge_input_mw
        steam_ht_cap = caps.steam_to_ht_reference_input_mw
        steam_mt_cap = caps.steam_to_mt_reference_input_mw
        electric_output_cap = caps.electric_output_mw
        heat_output_cap = caps.heat_output_mw
        ambient = case.timeseries.ambient_temperature_c
        auxiliary_upper = _tes_auxiliary_upper_bounds(
            case.tes,
            dt_hours=case.timeseries.dt_hours,
            ambient_temperature_c=(
                (None,) * period_count if ambient is None else ambient
            ),
        )
    model.tes_electric_charge = Var(
        model.periods, bounds=(0.0, electric_charge_cap)
    )
    model.tes_steam_to_ht = Var(model.periods, bounds=(0.0, steam_ht_cap))
    model.tes_steam_to_mt = Var(model.periods, bounds=(0.0, steam_mt_cap))
    model.tes_electric_output = Var(
        model.periods, bounds=(0.0, electric_output_cap)
    )
    model.tes_heat_output = Var(model.periods, bounds=(0.0, heat_output_cap))
    model.tes_auxiliary = Var(
        model.periods,
        bounds=lambda _block, period: (0.0, auxiliary_upper[int(period)]),
    )
    model.heat_allocation = Constraint(
        model.periods,
        rule=lambda block, period: (
            block.chp_heat_total[period]
            == block.direct_heat[period]
            + block.tes_steam_to_ht[period]
            + block.tes_steam_to_mt[period]
        ),
    )
    model.heat_balance = Constraint(
        model.periods,
        rule=lambda block, period: (
            block.direct_heat[period] + block.tes_heat_output[period]
            == case.timeseries.heat_demand_mw[int(period)]
        ),
    )
    model.pcc_balance = Constraint(
        model.periods,
        rule=lambda block, period: (
            block.pcc_export[period]
            + block.tes_electric_charge[period]
            + block.chp_auxiliary_total[period]
            + block.tes_auxiliary[period]
            == block.chp_gross_total[period]
            + block.wind_used[period]
            + block.pv_used[period]
            + block.tes_electric_output[period]
        ),
    )
    model.static_pcc_objective = Objective(
        expr=sum(model.pcc_export[period] for period in model.periods),
        sense=maximize if maximize_pcc else minimize,
    )
    return model


def solve_static_pcc_bounds(
    case: E0CCase,
    *,
    threads: int = 1,
    safety_margin_mw: float = D30_BOUND_SAFETY_MARGIN_MW,
) -> PCCReachableBounds:
    """Solve the separable minimum and maximum PCC relaxations with HiGHS."""

    import highspy
    from pyomo.environ import value

    if not math.isfinite(safety_margin_mw) or safety_margin_mw < 0.0:
        raise ValueError("D30 safety margin must be finite and non-negative")
    models = (
        build_static_pcc_relaxation(case, maximize_pcc=False),
        build_static_pcc_relaxation(case, maximize_pcc=True),
    )
    solutions: list[tuple[str, float, tuple[float, ...]]] = []
    try:
        for model in models:
            solver = create_highs_solver(threads=threads, mip_rel_gap=0.0)
            started = perf_counter()
            results = solver.solve(model, tee=False)
            runtime = perf_counter() - started
            termination = str(results.solver.termination_condition).lower()
            if termination != "optimal":
                raise RuntimeError(
                    f"D30 static PCC relaxation did not solve optimally: {termination}"
                )
            values = tuple(
                float(value(model.pcc_export[period])) for period in model.periods
            )
            solutions.append((termination, runtime, values))
    finally:
        # The D19 reproduction that follows a global D30 screen is locked to
        # one thread. Release the process-wide scheduler initialized here.
        highspy.Highs.resetGlobalScheduler(True)
    lower = tuple(
        max(0.0, value - safety_margin_mw) for value in solutions[0][2]
    )
    upper = tuple(
        min(case.pcc_export_capacity_mw, value + safety_margin_mw)
        for value in solutions[1][2]
    )
    if any(lo > hi for lo, hi in zip(lower, upper, strict=True)):
        raise RuntimeError("D30 static PCC relaxation returned a reversed interval")
    return PCCReachableBounds(
        architecture=case.architecture.value,
        periods=case.timeseries.period_count,
        lower_mw=lower,
        upper_mw=upper,
        minimum_termination=solutions[0][0],
        maximum_termination=solutions[1][0],
        minimum_runtime_seconds=solutions[0][1],
        maximum_runtime_seconds=solutions[1][1],
        safety_margin_mw=safety_margin_mw,
    )


def tighten_bounds_with_annual_service(
    lower_mw: Sequence[float],
    upper_mw: Sequence[float],
    *,
    annual_weights: Sequence[float],
    dt_hours: float,
    target_export_mwh: float,
    safety_margin_mw: float = D30_BOUND_SAFETY_MARGIN_MW,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Propagate one exact weighted annual-energy equality through box bounds."""

    lower = list(_finite_bounds(lower_mw, label="D30 lower bounds"))
    upper = list(_finite_bounds(upper_mw, label="D30 upper bounds"))
    original_lower = tuple(lower)
    original_upper = tuple(upper)
    weights = _finite_bounds(annual_weights, label="D30 annual weights")
    if len(lower) != len(upper) or len(lower) != len(weights):
        raise ValueError("D30 bounds and annual weights must have equal length")
    if any(lo < 0.0 or lo > hi for lo, hi in zip(lower, upper, strict=True)):
        raise ValueError("D30 received an invalid PCC interval")
    if any(weight <= 0.0 for weight in weights):
        raise ValueError("D30 annual weights must be positive")
    if not math.isfinite(dt_hours) or dt_hours <= 0.0:
        raise ValueError("D30 dt_hours must be finite and positive")
    if not math.isfinite(target_export_mwh) or target_export_mwh < 0.0:
        raise ValueError("D30 target export must be finite and non-negative")
    coefficients = tuple(dt_hours * weight for weight in weights)
    minimum_energy = math.fsum(
        coefficient * value for coefficient, value in zip(coefficients, lower)
    )
    maximum_energy = math.fsum(
        coefficient * value for coefficient, value in zip(coefficients, upper)
    )
    energy_tolerance = max(1e-6, safety_margin_mw * math.fsum(coefficients))
    if target_export_mwh < minimum_energy - energy_tolerance or (
        target_export_mwh > maximum_energy + energy_tolerance
    ):
        raise ValueError("D30 annual export target lies outside the static envelope")

    for _iteration in range(len(lower) + 1):
        changed = False
        total_lower = math.fsum(
            coefficient * value for coefficient, value in zip(coefficients, lower)
        )
        total_upper = math.fsum(
            coefficient * value for coefficient, value in zip(coefficients, upper)
        )
        new_lower = lower.copy()
        new_upper = upper.copy()
        for index, coefficient in enumerate(coefficients):
            implied_lower = (
                target_export_mwh - (total_upper - coefficient * upper[index])
            ) / coefficient
            implied_upper = (
                target_export_mwh - (total_lower - coefficient * lower[index])
            ) / coefficient
            candidate_lower = max(lower[index], implied_lower)
            candidate_upper = min(upper[index], implied_upper)
            if candidate_lower > candidate_upper + safety_margin_mw:
                raise ValueError("D30 service propagation reversed a PCC interval")
            if candidate_lower > lower[index] + 1e-12:
                new_lower[index] = candidate_lower
                changed = True
            if candidate_upper < upper[index] - 1e-12:
                new_upper[index] = candidate_upper
                changed = True
        lower, upper = new_lower, new_upper
        if not changed:
            break
    else:  # pragma: no cover - defensive convergence guard
        raise RuntimeError("D30 service-bound propagation did not converge")

    # Numerical protection may relax an implied service bound, but must never
    # widen the already protected static outer envelope.
    protected_lower = tuple(
        max(original_lower[index], value - safety_margin_mw)
        for index, value in enumerate(lower)
    )
    protected_upper = tuple(
        min(original_upper[index], value + safety_margin_mw)
        for index, value in enumerate(upper)
    )
    return protected_lower, protected_upper


def summarize_bound_tightening(
    comparator_raw: PCCReachableBounds,
    candidate_raw: PCCReachableBounds,
    *,
    comparator_service_lower_mw: Sequence[float],
    comparator_service_upper_mw: Sequence[float],
    candidate_service_lower_mw: Sequence[float],
    candidate_service_upper_mw: Sequence[float],
    pcc_capacity_mw: float,
) -> D30BoundAudit:
    """Summarize the exact D30 sign widths implied by two PCC envelopes."""

    c_lo = _finite_bounds(comparator_service_lower_mw, label="comparator lower")
    c_hi = _finite_bounds(comparator_service_upper_mw, label="comparator upper")
    t_lo = _finite_bounds(candidate_service_lower_mw, label="candidate lower")
    t_hi = _finite_bounds(candidate_service_upper_mw, label="candidate upper")
    count = comparator_raw.periods
    if any(len(values) != count for values in (c_lo, c_hi, t_lo, t_hi)):
        raise ValueError("D30 service bounds do not match the raw horizon")
    positive_width = tuple(
        max(0.0, candidate_upper - comparator_lower)
        for comparator_lower, candidate_upper in zip(c_lo, t_hi, strict=True)
    )
    negative_width = tuple(
        max(0.0, comparator_upper - candidate_lower)
        for comparator_upper, candidate_lower in zip(c_hi, t_lo, strict=True)
    )
    mean_positive = math.fsum(positive_width) / count
    mean_negative = math.fsum(negative_width) / count
    return D30BoundAudit(
        periods=count,
        per_period_cut_count=6 * count,
        comparator_mean_width_before_service_mw=math.fsum(
            hi - lo
            for lo, hi in zip(
                comparator_raw.lower_mw, comparator_raw.upper_mw, strict=True
            )
        )
        / count,
        comparator_mean_width_after_service_mw=math.fsum(
            hi - lo for lo, hi in zip(c_lo, c_hi, strict=True)
        )
        / count,
        candidate_mean_width_before_service_mw=math.fsum(
            hi - lo
            for lo, hi in zip(candidate_raw.lower_mw, candidate_raw.upper_mw, strict=True)
        )
        / count,
        candidate_mean_width_after_service_mw=math.fsum(
            hi - lo for lo, hi in zip(t_lo, t_hi, strict=True)
        )
        / count,
        mean_positive_sign_width_mw=mean_positive,
        mean_negative_sign_width_mw=mean_negative,
        maximum_positive_sign_width_mw=max(positive_width),
        maximum_negative_sign_width_mw=max(negative_width),
        positive_sign_width_reduction_fraction=(
            1.0 - mean_positive / pcc_capacity_mw
        ),
        negative_sign_width_reduction_fraction=(
            1.0 - mean_negative / pcc_capacity_mw
        ),
        pcc_capacity_mw=pcc_capacity_mw,
        bound_safety_margin_mw=D30_BOUND_SAFETY_MARGIN_MW,
    )


def add_physics_service_sign_cuts(
    model: object,
    *,
    comparator_lower_mw: Sequence[float],
    comparator_upper_mw: Sequence[float],
    candidate_lower_mw: Sequence[float],
    candidate_upper_mw: Sequence[float],
) -> None:
    """Install exact interval-aware sign and conditional envelope cuts."""

    from pyomo.environ import Constraint

    periods = tuple(model.redistribution_periods)
    c_lo = _finite_bounds(comparator_lower_mw, label="comparator lower")
    c_hi = _finite_bounds(comparator_upper_mw, label="comparator upper")
    t_lo = _finite_bounds(candidate_lower_mw, label="candidate lower")
    t_hi = _finite_bounds(candidate_upper_mw, label="candidate upper")
    if any(len(values) != len(periods) for values in (c_lo, c_hi, t_lo, t_hi)):
        raise ValueError("D30 sign-cut bounds do not match the joint horizon")
    required = (
        "d27_delta_positive_mw",
        "d27_delta_negative_mw",
        "delta_nonnegative",
        "comparator",
        "candidate",
    )
    if any(not hasattr(model, name) for name in required):
        raise ValueError("D30 cuts require the D27 disaggregated sign model")
    if hasattr(model, "d30_positive_sign_limit"):
        raise ValueError("D30 cuts are already installed")
    positive_width = tuple(
        max(0.0, t_hi[index] - c_lo[index]) for index in range(len(periods))
    )
    negative_width = tuple(
        max(0.0, c_hi[index] - t_lo[index]) for index in range(len(periods))
    )
    for offset, period in enumerate(periods):
        model.comparator.pcc_export[period].setlb(c_lo[offset])
        model.comparator.pcc_export[period].setub(c_hi[offset])
        model.candidate.pcc_export[period].setlb(t_lo[offset])
        model.candidate.pcc_export[period].setub(t_hi[offset])
        model.d27_delta_positive_mw[period].setub(positive_width[offset])
        model.d27_delta_negative_mw[period].setub(negative_width[offset])
        model.absolute_delta_pcc_export_mw[period].setub(
            max(positive_width[offset], negative_width[offset])
        )

    index = {period: offset for offset, period in enumerate(periods)}
    model.d30_positive_sign_limit = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.d27_delta_positive_mw[period]
            <= positive_width[index[period]] * block.delta_nonnegative[period]
        ),
    )
    model.d30_negative_sign_limit = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.d27_delta_negative_mw[period]
            <= negative_width[index[period]] * (1.0 - block.delta_nonnegative[period])
        ),
    )
    model.d30_positive_candidate_envelope = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.d27_delta_positive_mw[period]
            <= block.candidate.pcc_export[period]
            - c_lo[index[period]]
            + max(0.0, c_lo[index[period]] - t_lo[index[period]])
            * (1.0 - block.delta_nonnegative[period])
        ),
    )
    model.d30_positive_comparator_envelope = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.d27_delta_positive_mw[period]
            <= t_hi[index[period]]
            - block.comparator.pcc_export[period]
            + max(0.0, c_hi[index[period]] - t_hi[index[period]])
            * (1.0 - block.delta_nonnegative[period])
        ),
    )
    model.d30_negative_comparator_envelope = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.d27_delta_negative_mw[period]
            <= block.comparator.pcc_export[period]
            - t_lo[index[period]]
            + max(0.0, t_lo[index[period]] - c_lo[index[period]])
            * block.delta_nonnegative[period]
        ),
    )
    model.d30_negative_candidate_envelope = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.d27_delta_negative_mw[period]
            <= c_hi[index[period]]
            - block.candidate.pcc_export[period]
            + max(0.0, t_hi[index[period]] - c_hi[index[period]])
            * block.delta_nonnegative[period]
        ),
    )


def run_bound_screen(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    d19_source_dir: str | Path,
    d22_source_dir: str | Path,
    window: E0D17WindowSpec,
    threads: int,
) -> D30BoundScreen:
    """Run the cheap D30 bounds-only gate for one locked E0 window."""

    d19_rows, _ = load_e0d23_source_rows(d19_source_dir, d22_source_dir)
    if window.window_id not in d19_rows:
        raise ValueError(f"D30 window is absent from D19: {window.window_id}")
    inputs = load_e0d17_inputs(heat_path, vre_path)
    rows = _window_rows(inputs, window)
    comparator, candidate, _comparator_cap, _candidate_cap, service = _build_cases(
        rows, d19_rows[window.window_id]
    )
    comparator_raw = solve_static_pcc_bounds(comparator, threads=threads)
    candidate_raw = solve_static_pcc_bounds(candidate, threads=threads)
    weights = comparator.economics.horizon.period_weights
    comparator_lower, comparator_upper = tighten_bounds_with_annual_service(
        comparator_raw.lower_mw,
        comparator_raw.upper_mw,
        annual_weights=weights,
        dt_hours=comparator.timeseries.dt_hours,
        target_export_mwh=service.target_export_mwh,
    )
    candidate_lower, candidate_upper = tighten_bounds_with_annual_service(
        candidate_raw.lower_mw,
        candidate_raw.upper_mw,
        annual_weights=weights,
        dt_hours=candidate.timeseries.dt_hours,
        target_export_mwh=service.target_export_mwh,
    )
    audit = summarize_bound_tightening(
        comparator_raw,
        candidate_raw,
        comparator_service_lower_mw=comparator_lower,
        comparator_service_upper_mw=comparator_upper,
        candidate_service_lower_mw=candidate_lower,
        candidate_service_upper_mw=candidate_upper,
        pcc_capacity_mw=comparator.pcc_export_capacity_mw,
    )
    return D30BoundScreen(
        schema=D30_SCREEN_SCHEMA,
        window_id=window.window_id,
        hours=window.hours,
        target_export_mwh=service.target_export_mwh,
        comparator_raw=comparator_raw,
        candidate_raw=candidate_raw,
        comparator_service_lower_mw=comparator_lower,
        comparator_service_upper_mw=comparator_upper,
        candidate_service_lower_mw=candidate_lower,
        candidate_service_upper_mw=candidate_upper,
        bound_audit=audit,
    )


def _known_witness_within_screen(
    comparator_model: object,
    candidate_model: object,
    screen: D30BoundScreen,
) -> bool:
    from pyomo.environ import value

    tolerance = 2.0 * D30_BOUND_SAFETY_MARGIN_MW
    for period in comparator_model.periods:
        index = int(period)
        comparator = float(value(comparator_model.pcc_export[period]))
        candidate = float(value(candidate_model.pcc_export[period]))
        if not (
            screen.comparator_service_lower_mw[index] - tolerance
            <= comparator
            <= screen.comparator_service_upper_mw[index] + tolerance
        ):
            return False
        if not (
            screen.candidate_service_lower_mw[index] - tolerance
            <= candidate
            <= screen.candidate_service_upper_mw[index] + tolerance
        ):
            return False
    return True


def run_physics_service_bound_probe(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    d19_source_dir: str | Path,
    d22_source_dir: str | Path,
    d29_source_dir: str | Path,
    window: E0D17WindowSpec,
    time_limit_seconds: float,
    threads: int,
    tee: bool = False,
) -> D30GlobalProbe:
    """Reopen the exact global maximum with D29 plus D30 valid cuts."""

    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0.0:
        raise ValueError("D30 time limit must be finite and positive")
    if type(threads) is not int or threads <= 0:
        raise ValueError("D30 threads must be a positive integer")
    reference = load_d29_maximum_reference(
        d29_source_dir,
        window_id=window.window_id,
    )
    if reference.hours != window.hours:
        raise ValueError("D30 D29 reference horizon mismatch")
    screen = run_bound_screen(
        heat_path,
        vre_path,
        d19_source_dir=d19_source_dir,
        d22_source_dir=d22_source_dir,
        window=window,
        threads=threads,
    )

    d19_rows, _ = load_e0d23_source_rows(d19_source_dir, d22_source_dir)
    inputs = load_e0d17_inputs(heat_path, vre_path)
    rows = _window_rows(inputs, window)
    comparator_case, candidate_case, comparator_cap, candidate_cap, service = (
        _build_cases(rows, d19_rows[window.window_id])
    )
    warm_started = perf_counter()
    comparator_selected = _solve_d19_selected_model(
        comparator_case,
        primary_mip_gap=0.0,
        pcc_service_feasibility_warm_start=False,
    )
    candidate_selected = _solve_d19_selected_model(
        candidate_case,
        primary_mip_gap=_window_mip_gap(window),
        pcc_service_feasibility_warm_start=window.hours > 24,
    )
    warm_runtime = perf_counter() - warm_started
    known_witness_within_bounds = _known_witness_within_screen(
        comparator_selected,
        candidate_selected,
        screen,
    )
    if not known_witness_within_bounds:
        raise RuntimeError("D30 static envelope excludes the D19 selected witness")

    face_model = build_joint_redistribution_model(
        comparator_case,
        candidate_case,
        comparator_admissibility=comparator_cap,
        candidate_admissibility=candidate_cap,
        direction=RedistributionDirection.MAXIMUM,
    )
    _seed_joint_model(face_model, comparator_selected, candidate_selected)
    fixed_count = _fix_integer_pattern(face_model.comparator, comparator_selected)
    fixed_count += _fix_integer_pattern(face_model.candidate, candidate_selected)
    face_result = _strict_solve(
        face_model,
        comparator_case=comparator_case,
        candidate_case=candidate_case,
        comparator_cap=comparator_cap,
        candidate_cap=candidate_cap,
        pcc_service=service,
        window=window,
        scope=IntegerScope.D19_SELECTED_FACE,
        direction=RedistributionDirection.MAXIMUM,
        fixed_primary_integer_count=fixed_count,
        warm_start_runtime_seconds=warm_runtime,
        time_limit_seconds=min(300.0, time_limit_seconds),
        threads=threads,
        tee=tee,
        allow_incumbent_only=True,
    )

    model = build_joint_redistribution_model(
        comparator_case,
        candidate_case,
        comparator_admissibility=comparator_cap,
        candidate_admissibility=candidate_cap,
        direction=RedistributionDirection.MAXIMUM,
    )
    _seed_joint_from_joint(face_model, model)
    _replace_big_m_with_disaggregated_sign_formulation(
        model,
        pcc_capacity_mw=comparator_case.pcc_export_capacity_mw,
    )
    add_export_linked_sign_cuts(
        model,
        pcc_capacity_mw=comparator_case.pcc_export_capacity_mw,
        annual_weights=comparator_case.economics.horizon.period_weights,
        dt_hours=comparator_case.timeseries.dt_hours,
        target_export_mwh=service.target_export_mwh,
    )
    add_physics_service_sign_cuts(
        model,
        comparator_lower_mw=screen.comparator_service_lower_mw,
        comparator_upper_mw=screen.comparator_service_upper_mw,
        candidate_lower_mw=screen.candidate_service_lower_mw,
        candidate_upper_mw=screen.candidate_service_upper_mw,
    )
    result = _strict_solve(
        model,
        comparator_case=comparator_case,
        candidate_case=candidate_case,
        comparator_cap=comparator_cap,
        candidate_cap=candidate_cap,
        pcc_service=service,
        window=window,
        scope=IntegerScope.REOPENED,
        direction=RedistributionDirection.MAXIMUM,
        fixed_primary_integer_count=0,
        warm_start_runtime_seconds=warm_runtime,
        time_limit_seconds=time_limit_seconds,
        threads=threads,
        tee=tee,
        conditional_face_warm_start_mwh=face_result.auxiliary_objective_mwh,
        conditional_face_warm_start_runtime_seconds=face_result.runtime_seconds,
        conditional_face_warm_start_termination="d30_selected_face",
        conditional_face_fixed_primary_integer_count=fixed_count,
        allow_incumbent_only=True,
    )
    if result.maximum_positive_normalized_constraint_residual > STRICT_FEASIBILITY_TOLERANCE:
        raise RuntimeError("D30 global incumbent violates strict feasibility")
    if (
        abs(result.auxiliary_objective_mismatch_mwh)
        > D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH
    ):
        raise RuntimeError(
            "D30 global incumbent failed L1 recomputation: "
            f"{result.auxiliary_objective_mismatch_mwh} MWh/a"
        )

    witness_reference_excess = (
        result.recomputed_redistribution_mwh
        - reference.strict_global_upper_bound_mwh
    )
    if witness_reference_excess > D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH:
        raise RuntimeError(
            "D30 recomputed witness exceeds the D29 strict upper bound beyond "
            "the registered numerical tolerance: "
            f"{witness_reference_excess} MWh/a"
        )
    witness_clamped = witness_reference_excess > 0.0
    promoted_witness = min(
        result.recomputed_redistribution_mwh,
        reference.strict_global_upper_bound_mwh,
    )
    lower = max(
        reference.strict_global_lower_bound_mwh,
        promoted_witness,
    )
    upper = reference.strict_global_upper_bound_mwh
    dual_reference_deficit: float | None = None
    dual_clamped = False
    if result.dual_bound_mwh is not None:
        dual_reference_deficit = (
            reference.strict_global_lower_bound_mwh - result.dual_bound_mwh
        )
        if dual_reference_deficit > D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH:
            raise RuntimeError(
                "D30 global dual falls below the known D29 feasible lower bound "
                "beyond the registered numerical tolerance: "
                f"{dual_reference_deficit} MWh/a"
            )
        dual_clamped = dual_reference_deficit > 0.0
        promoted_dual = max(
            result.dual_bound_mwh,
            reference.strict_global_lower_bound_mwh,
        )
        upper = min(upper, promoted_dual)
    if upper + KNOWN_WITNESS_TOLERANCE_MWH < lower:
        raise RuntimeError("D30 strict interval is numerically reversed")
    improvement = reference.strict_global_upper_bound_mwh - upper
    improvement_fraction = improvement / reference.strict_global_upper_bound_mwh
    exact = upper - lower <= KNOWN_WITNESS_TOLERANCE_MWH
    return D30GlobalProbe(
        schema=D30_PROBE_SCHEMA,
        window_id=window.window_id,
        hours=window.hours,
        threads=threads,
        time_limit_seconds=time_limit_seconds,
        reference_d29_lower_bound_mwh=reference.strict_global_lower_bound_mwh,
        reference_d29_upper_bound_mwh=reference.strict_global_upper_bound_mwh,
        reference_d29_csv_sha256=reference.csv_sha256,
        reference_d29_manifest_sha256=reference.manifest_sha256,
        selected_face_witness_mwh=face_result.auxiliary_objective_mwh,
        selected_face_termination=face_result.termination,
        selected_face_bound_certificate_complete=face_result.bound_certificate_complete,
        known_witness_within_bounds=known_witness_within_bounds,
        bound_audit=screen.bound_audit,
        termination=result.termination,
        runtime_seconds=result.runtime_seconds,
        primal_bound_mwh=result.primal_bound_mwh,
        recomputed_redistribution_mwh=result.recomputed_redistribution_mwh,
        witness_reference_excess_mwh=witness_reference_excess,
        witness_clamped_to_reference=witness_clamped,
        dual_bound_mwh=result.dual_bound_mwh,
        dual_reference_deficit_mwh=dual_reference_deficit,
        dual_clamped_to_reference_lower=dual_clamped,
        relative_gap=result.relative_gap,
        bound_certificate_complete=result.bound_certificate_complete,
        witness_dominance_passed=(
            result.recomputed_redistribution_mwh + KNOWN_WITNESS_TOLERANCE_MWH
            >= face_result.auxiliary_objective_mwh
        ),
        maximum_positive_normalized_constraint_residual=(
            result.maximum_positive_normalized_constraint_residual
        ),
        auxiliary_objective_mismatch_mwh=result.auxiliary_objective_mismatch_mwh,
        strict_global_lower_bound_mwh=lower,
        strict_global_upper_bound_mwh=upper,
        global_upper_bound_improvement_mwh=improvement,
        global_upper_bound_improvement_fraction=improvement_fraction,
        global_upper_bound_improved=improvement > KNOWN_WITNESS_TOLERANCE_MWH,
        exact_global_maximum=exact,
        global_dual_is_valid_l1_upper_bound=result.bound_certificate_complete,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the E0-D-30 PCC-bound screen or reopened global probe."
    )
    parser.add_argument("--heat-path", required=True, type=Path)
    parser.add_argument("--vre-path", required=True, type=Path)
    parser.add_argument("--d19-source-dir", required=True, type=Path)
    parser.add_argument("--d22-source-dir", required=True, type=Path)
    parser.add_argument("--d29-source-dir", type=Path)
    parser.add_argument(
        "--window",
        required=True,
        choices=tuple(window.window_id for window in DEFAULT_WINDOWS),
    )
    parser.add_argument("--threads", type=int, default=28)
    parser.add_argument("--time-limit-seconds", type=float)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    window = next(item for item in DEFAULT_WINDOWS if item.window_id == args.window)
    if (args.d29_source_dir is None) != (args.time_limit_seconds is None):
        parser.error(
            "--d29-source-dir and --time-limit-seconds must be supplied together"
        )
    if args.d29_source_dir is None:
        result = run_bound_screen(
            args.heat_path,
            args.vre_path,
            d19_source_dir=args.d19_source_dir,
            d22_source_dir=args.d22_source_dir,
            window=window,
            threads=args.threads,
        )
    else:
        assert args.time_limit_seconds is not None
        result = run_physics_service_bound_probe(
            args.heat_path,
            args.vre_path,
            d19_source_dir=args.d19_source_dir,
            d22_source_dir=args.d22_source_dir,
            d29_source_dir=args.d29_source_dir,
            window=window,
            time_limit_seconds=args.time_limit_seconds,
            threads=args.threads,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.output.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
