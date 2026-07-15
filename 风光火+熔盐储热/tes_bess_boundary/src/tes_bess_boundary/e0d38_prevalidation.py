"""E0-D-38 representative-period to full-year prevalidation runner.

The module implements the result-before contract frozen in
``e0_d38_three_state_representative_full_year_prevalidation_contract.md``.
It produces controlled public-cost proxy results only; it cannot certify a
Yangling project TAC or a project technology winner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from tes_bess_boundary.components.chp import (
    CommitmentTransitionFormulation,
    FuelSegmentFormulation,
    LowLoadFuelRule,
    yangling_chp_specs,
)
from tes_bess_boundary.e0d17_exploration import (
    COAL_PRICE_CNY_PER_TCE,
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
    PV_CAPACITY_MW,
    WIND_CAPACITY_MW,
    load_e0d17_inputs,
)
from tes_bess_boundary.e0d34_endogenous_capacity_sample import _planning_inputs
from tes_bess_boundary.e0d37_block_horizon import (
    D36_PERIODS_SHA256,
    load_e0d37_block_horizon,
)
from tes_bess_boundary.economics import (
    AnnualDispatchBlock,
    BlockAnnualHorizonSpec,
)
from tes_bess_boundary.model import (
    AnnualCurtailmentServiceSpec,
    AnnualPCCExportServiceSpec,
    Architecture,
    E0CTimeSeries,
    ValidationObjectiveSpec,
)
from tes_bess_boundary.planning_model import (
    EndogenousCapacityCase,
    EndogenousCapacityResult,
    EndogenousCapacitySnapshot,
    build_endogenous_capacity_model,
    fix_endogenous_capacity_snapshot,
    solve_endogenous_capacity,
)
from tes_bess_boundary.solver import create_highs_solver


SERVICE_SCHEMA_ID = "tes_bess_boundary.e0d38_service_contract.v1"
CASE_SCHEMA_ID = "tes_bess_boundary.e0d38_case_result.v1"
BUILD_SCHEMA_ID = "tes_bess_boundary.e0d38_build_audit.v1"
SERVICE_TOLERANCE_MWH = 1e-3
CURTAILMENT_FRACTION = 0.10
FORMAL_MIP_REL_GAP = 0.001
FULL_YEAR_HOURS = 8_784


@dataclass(frozen=True)
class E0D38StateSpec:
    """One preregistered physical and storage-duration state."""

    state_id: str
    physical_service_key: str
    heat_scale: float
    pcc_export_capacity_mw: float
    storage_duration_hours: float | None

    def __post_init__(self) -> None:
        if not self.state_id.strip() or not self.physical_service_key.strip():
            raise ValueError("D38 state identifiers must be non-empty")
        for value, name in (
            (self.heat_scale, "heat_scale"),
            (self.pcc_export_capacity_mw, "pcc_export_capacity_mw"),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if self.storage_duration_hours is not None and (
            not math.isfinite(self.storage_duration_hours)
            or self.storage_duration_hours <= 0.0
        ):
            raise ValueError("storage duration must be finite and positive")


HIGH_HEAT_SCALE = 1.824264742834285
STATES = {
    "baseline": E0D38StateSpec(
        state_id="baseline",
        physical_service_key="baseline_heat_pcc700",
        heat_scale=1.0,
        pcc_export_capacity_mw=700.0,
        storage_duration_hours=None,
    ),
    "high_heat_tight_pcc": E0D38StateSpec(
        state_id="high_heat_tight_pcc",
        physical_service_key="high_heat_pcc490",
        heat_scale=HIGH_HEAT_SCALE,
        pcc_export_capacity_mw=490.0,
        storage_duration_hours=None,
    ),
    "long_duration_24h": E0D38StateSpec(
        state_id="long_duration_24h",
        physical_service_key="baseline_heat_pcc700",
        heat_scale=1.0,
        pcc_export_capacity_mw=700.0,
        storage_duration_hours=24.0,
    ),
}


@dataclass(frozen=True)
class E0D38HorizonInput:
    """Validated time series and the exact annual scoring/state boundary."""

    horizon_id: str
    timeseries: E0CTimeSeries
    horizon: BlockAnnualHorizonSpec
    renewable_available_mwh: float
    source_sha256: str


def state_spec(state_id: str) -> E0D38StateSpec:
    """Return one immutable preregistered state."""

    try:
        return STATES[state_id]
    except KeyError as exc:
        raise ValueError(f"unknown D38 state: {state_id}") from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(directory: Path) -> str:
    digest = hashlib.sha256()
    files = tuple(sorted(path for path in directory.rglob("*") if path.is_file()))
    if not files:
        raise ValueError(f"hash input directory is empty: {directory}")
    for path in files:
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _weighted_renewable_available_mwh(
    timeseries: E0CTimeSeries,
    horizon: BlockAnnualHorizonSpec,
) -> float:
    return timeseries.dt_hours * sum(
        float(weight)
        * (
            timeseries.wind_available_mw[period]
            + timeseries.pv_available_mw[period]
        )
        for period, weight in enumerate(horizon.period_weights)
    )


def load_full_year_input(
    heat_path: str | Path,
    vre_path: str | Path,
    state: E0D38StateSpec,
) -> E0D38HorizonInput:
    """Load the hash-locked actual 8784 h series as one cyclic block."""

    rows = load_e0d17_inputs(heat_path, vre_path)
    timeseries = E0CTimeSeries(
        heat_demand_mw=tuple(state.heat_scale * row.heat_demand_mw for row in rows),
        wind_available_mw=tuple(WIND_CAPACITY_MW * row.wind_cf for row in rows),
        pv_available_mw=tuple(PV_CAPACITY_MW * row.pv_cf for row in rows),
        ambient_temperature_c=tuple(row.ambient_temperature_c for row in rows),
    )
    horizon = BlockAnnualHorizonSpec(
        period_weights=(1.0,) * FULL_YEAR_HOURS,
        dispatch_blocks=(
            AnnualDispatchBlock("full_year_2024", tuple(range(FULL_YEAR_HOURS))),
        ),
    )
    horizon.validate_time_grid(
        period_count=timeseries.period_count,
        dt_hours=timeseries.dt_hours,
    )
    return E0D38HorizonInput(
        horizon_id="actual_8784h_single_cyclic_block",
        timeseries=timeseries,
        horizon=horizon,
        renewable_available_mwh=_weighted_renewable_available_mwh(
            timeseries,
            horizon,
        ),
        source_sha256=hashlib.sha256(
            (FORMAL_HEAT_SHA256 + LEGACY_VRE_SHA256).encode("ascii")
        ).hexdigest(),
    )


def load_representative_input(
    periods_path: str | Path,
    state: E0D38StateSpec,
) -> E0D38HorizonInput:
    """Load D36 through the strict D37 adapter and apply only heat scaling."""

    representative = load_e0d37_block_horizon(periods_path)
    timeseries = replace(
        representative.timeseries,
        heat_demand_mw=tuple(
            state.heat_scale * value
            for value in representative.timeseries.heat_demand_mw
        ),
    )
    return E0D38HorizonInput(
        horizon_id="d36_six_weeks_plus_year_end_tail_d37_block_cyclic",
        timeseries=timeseries,
        horizon=representative.horizon,
        renewable_available_mwh=_weighted_renewable_available_mwh(
            timeseries,
            representative.horizon,
        ),
        source_sha256=representative.source_sha256,
    )


def planning_inputs_for_state(
    price_basis_path: str | Path,
    state: E0D38StateSpec,
) -> tuple[Any, ...]:
    """Build the D34 public-cost inputs with the preregistered duration policy."""

    bess, bess_economics, tes, loss_auxiliary, tes_costs = _planning_inputs(
        Path(price_basis_path)
    )
    if state.storage_duration_hours is not None:
        duration = state.storage_duration_hours
        bess = replace(
            bess,
            minimum_discharge_duration_hours=duration,
            maximum_discharge_duration_hours=duration,
        )
        tes = replace(
            tes,
            minimum_service_duration_hours=duration,
            maximum_service_duration_hours=duration,
        )
    return bess, bess_economics, tes, loss_auxiliary, tes_costs


def build_d38_case(
    *,
    state: E0D38StateSpec,
    architecture: Architecture,
    horizon_input: E0D38HorizonInput,
    planning_inputs: tuple[Any, ...],
    objective: ValidationObjectiveSpec,
    curtailment_service: AnnualCurtailmentServiceSpec | None,
    pcc_export_service: AnnualPCCExportServiceSpec | None,
) -> EndogenousCapacityCase:
    """Build one preregistered D38 architecture/horizon case."""

    bess, bess_economics, tes, loss_auxiliary, tes_costs = planning_inputs
    includes_bess = architecture in (Architecture.BESS, Architecture.HYBRID)
    includes_tes = architecture in (Architecture.TES, Architecture.HYBRID)
    return EndogenousCapacityCase(
        architecture=architecture,
        timeseries=horizon_input.timeseries,
        chp_units=yangling_chp_specs(
            low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE
        ),
        chp_initial_online=(1, 1),
        chp_terminal_online=(1, 1),
        pcc_export_capacity_mw=state.pcc_export_capacity_mw,
        horizon=horizon_input.horizon,
        bess=bess if includes_bess else None,
        bess_economics=bess_economics if includes_bess else None,
        tes=tes if includes_tes else None,
        tes_cost_portfolio=tes_costs if includes_tes else None,
        tes_loss_auxiliary=loss_auxiliary if includes_tes else None,
        objective=objective,
        curtailment_service=curtailment_service,
        pcc_export_service=pcc_export_service,
        chp_fuel_segment_formulation=FuelSegmentFormulation.LOGARITHMIC,
        chp_transition_formulation=(
            CommitmentTransitionFormulation.CONTINUOUS_ENVELOPE
        ),
    )


def _result_payload(result: EndogenousCapacityResult, runtime_seconds: float) -> dict:
    payload = asdict(result)
    payload["architecture"] = result.architecture.value
    payload["runtime_seconds"] = runtime_seconds
    return payload


def _snapshot_payload(snapshot: EndogenousCapacitySnapshot) -> dict:
    payload = asdict(snapshot)
    payload["architecture"] = snapshot.architecture.value
    return payload


def _snapshot_from_result_file(path: Path) -> EndogenousCapacitySnapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_snapshot = payload.get("capacity_snapshot")
    if not isinstance(raw_snapshot, dict):
        raise ValueError("capacity result does not contain a capacity_snapshot")
    values = dict(raw_snapshot)
    values["architecture"] = Architecture(values["architecture"])
    return EndogenousCapacitySnapshot(**values)


def _code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    names = (
        "e0d38_prevalidation.py",
        "planning_model.py",
        "capacity_planning.py",
        "model.py",
        "e0d37_block_horizon.py",
    )
    return {name: _sha256(package / name) for name in names}


def _common_provenance(args: argparse.Namespace) -> dict:
    return {
        "formal_heat_sha256": FORMAL_HEAT_SHA256,
        "legacy_vre_sha256": LEGACY_VRE_SHA256,
        "d36_periods_sha256": D36_PERIODS_SHA256,
        "actual_heat_file_sha256": _sha256(args.heat_path),
        "actual_vre_file_sha256": _sha256(args.vre_path),
        "representative_periods_file_sha256": _sha256(args.periods_path),
        "price_basis_tree_sha256": _tree_sha256(args.price_basis_path),
        "code_sha256": _code_hashes(),
    }


def _solver_from_args(args: argparse.Namespace) -> object:
    solver = create_highs_solver(
        threads=args.solver_threads,
        random_seed=0,
        mip_rel_gap=args.mip_rel_gap,
    )
    if args.time_limit_seconds is not None:
        solver.options["time_limit"] = args.time_limit_seconds
    return solver


def _state_payload(state: E0D38StateSpec) -> dict:
    return asdict(state)


def run_service_reference(args: argparse.Namespace) -> dict:
    """Run the actual-year two-stage no-storage same-PCC service search."""

    state = state_spec(args.state)
    if state.state_id == "long_duration_24h":
        raise ValueError("long_duration_24h must reuse the baseline service contract")
    horizon_input = load_full_year_input(args.heat_path, args.vre_path, state)
    planning_inputs = planning_inputs_for_state(args.price_basis_path, state)
    solver = _solver_from_args(args)
    base_payload = {
        "schema_id": SERVICE_SCHEMA_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "claim_scope": "temporal_aggregation_prevalidation_not_formal_project_tac",
        "formal_project_tac_ready": False,
        "state": _state_payload(state),
        "physical_service_key": state.physical_service_key,
        "actual_renewable_available_mwh": horizon_input.renewable_available_mwh,
        "epsilon_curtailment_fraction": CURTAILMENT_FRACTION,
        "epsilon_curtailment_ceiling_mwh": (
            CURTAILMENT_FRACTION * horizon_input.renewable_available_mwh
        ),
        "minimum_curtailment_search_formulation": {
            "fuel_segment_code": "continuous_exact_zero_fuel_objective_projection",
            "physical_commitment_and_ramping": "unchanged",
        },
        "solver": {
            "name": "appsi_highs",
            "threads": args.solver_threads,
            "random_seed": 0,
            "mip_rel_gap": args.mip_rel_gap,
            "time_limit_seconds": args.time_limit_seconds,
        },
        "provenance": _common_provenance(args),
    }
    min_curtailment_case = build_d38_case(
        state=state,
        architecture=Architecture.NO_STORAGE,
        horizon_input=horizon_input,
        planning_inputs=planning_inputs,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=0.0,
            curtailment_penalty_cny_per_mwh=1.0,
        ),
        curtailment_service=None,
        pcc_export_service=None,
    )
    started = perf_counter()
    try:
        min_curtailment = solve_endogenous_capacity(
            min_curtailment_case,
            solver=solver,
            maximum_accepted_relative_gap=args.mip_rel_gap,
            relax_zero_cost_fuel_segments=True,
        )
    except Exception as error:  # noqa: BLE001 - retain the formal failure artifact
        return {
            **base_payload,
            "status": _failure_status(error),
            "failed_stage": "minimum_curtailment_search",
            "runtime_seconds": perf_counter() - started,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
    min_curtailment_runtime = perf_counter() - started
    natural_curtailment_ceiling = (
        min_curtailment.weighted_curtailment_mwh + SERVICE_TOLERANCE_MWH
    )
    economic_reference_case = build_d38_case(
        state=state,
        architecture=Architecture.NO_STORAGE,
        horizon_input=horizon_input,
        planning_inputs=planning_inputs,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=COAL_PRICE_CNY_PER_TCE,
            curtailment_penalty_cny_per_mwh=0.0,
        ),
        curtailment_service=AnnualCurtailmentServiceSpec(
            service_id=f"e0d38_{state.physical_service_key}_natural_min_curtailment",
            maximum_curtailment_mwh=natural_curtailment_ceiling,
        ),
        pcc_export_service=None,
    )
    started = perf_counter()
    try:
        economic_reference = solve_endogenous_capacity(
            economic_reference_case,
            solver=solver,
            maximum_accepted_relative_gap=args.mip_rel_gap,
        )
    except Exception as error:  # noqa: BLE001 - retain the formal failure artifact
        return {
            **base_payload,
            "status": _failure_status(error),
            "failed_stage": "economic_pcc_reference_search",
            "runtime_seconds": perf_counter() - started,
            "minimum_curtailment_search": _result_payload(
                min_curtailment,
                min_curtailment_runtime,
            ),
            "natural_minimum_curtailment_mwh": (
                min_curtailment.weighted_curtailment_mwh
            ),
            "natural_reference_curtailment_ceiling_mwh": (
                natural_curtailment_ceiling
            ),
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
    economic_reference_runtime = perf_counter() - started
    return {
        **base_payload,
        "status": "complete",
        "natural_minimum_curtailment_mwh": (
            min_curtailment.weighted_curtailment_mwh
        ),
        "natural_reference_curtailment_ceiling_mwh": natural_curtailment_ceiling,
        "pcc_export_target_mwh": economic_reference.weighted_pcc_export_mwh,
        "minimum_curtailment_search": _result_payload(
            min_curtailment,
            min_curtailment_runtime,
        ),
        "economic_pcc_reference_search": _result_payload(
            economic_reference,
            economic_reference_runtime,
        ),
    }


def _load_service_contract(
    path: Path,
    state: E0D38StateSpec,
) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_id") != SERVICE_SCHEMA_ID:
        raise ValueError("D38 service contract schema mismatch")
    if payload.get("status") != "complete":
        raise ValueError("D38 service contract is incomplete")
    if payload.get("physical_service_key") != state.physical_service_key:
        raise ValueError("D38 service contract physical state mismatch")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("D38 service contract lacks provenance")
    expected_hashes = {
        "formal_heat_sha256": FORMAL_HEAT_SHA256,
        "legacy_vre_sha256": LEGACY_VRE_SHA256,
        "d36_periods_sha256": D36_PERIODS_SHA256,
    }
    for key, expected in expected_hashes.items():
        if provenance.get(key) != expected:
            raise ValueError(f"D38 service contract {key} mismatch")
    for key in ("epsilon_curtailment_ceiling_mwh", "pcc_export_target_mwh"):
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"D38 service contract has invalid {key}")
        if not math.isfinite(float(value)) or value < 0.0:
            raise ValueError(f"D38 service contract has invalid {key}")
    return payload


def _service_specs(service: dict, state: E0D38StateSpec) -> tuple[Any, Any]:
    return (
        AnnualCurtailmentServiceSpec(
            service_id=f"e0d38_{state.physical_service_key}_epsilon10_actual",
            maximum_curtailment_mwh=service["epsilon_curtailment_ceiling_mwh"],
        ),
        AnnualPCCExportServiceSpec(
            service_id=f"e0d38_{state.physical_service_key}_actual_no_storage_pcc",
            target_export_mwh=service["pcc_export_target_mwh"],
        ),
    )


def _case_horizon_input(
    args: argparse.Namespace,
    state: E0D38StateSpec,
) -> E0D38HorizonInput:
    if args.phase == "representative_planning":
        return load_representative_input(args.periods_path, state)
    return load_full_year_input(args.heat_path, args.vre_path, state)


def _capacity_for_phase(
    args: argparse.Namespace,
    architecture: Architecture,
) -> EndogenousCapacitySnapshot | None:
    if args.phase != "full_year_fixed" or architecture is Architecture.NO_STORAGE:
        if args.capacity_result is not None:
            raise ValueError("capacity-result is only valid for a storage fixed replay")
        return None
    if args.capacity_result is None:
        raise ValueError("storage full_year_fixed requires --capacity-result")
    snapshot = _snapshot_from_result_file(args.capacity_result)
    if snapshot.architecture is not architecture:
        raise ValueError("capacity result architecture mismatch")
    return snapshot


def _model_size(model: object) -> dict[str, int]:
    from pyomo.environ import Binary, Constraint, Var

    variables = tuple(model.component_data_objects(Var, active=True))
    return {
        "variable_count": len(variables),
        "binary_variable_count": sum(
            1 for variable in variables if variable.domain is Binary
        ),
        "constraint_count": sum(
            1 for _ in model.component_data_objects(Constraint, active=True)
        ),
    }


def _case_base_payload(
    args: argparse.Namespace,
    *,
    state: E0D38StateSpec,
    architecture: Architecture,
    horizon_input: E0D38HorizonInput,
    service: dict,
) -> dict:
    return {
        "schema_id": CASE_SCHEMA_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "claim_scope": "temporal_aggregation_prevalidation_not_formal_project_tac",
        "formal_project_tac_ready": False,
        "state": _state_payload(state),
        "phase": args.phase,
        "architecture": architecture.value,
        "horizon_id": horizon_input.horizon_id,
        "model_period_count": horizon_input.timeseries.period_count,
        "weighted_annual_hours": horizon_input.horizon.weighted_hours(
            dt_hours=horizon_input.timeseries.dt_hours
        ),
        "horizon_renewable_available_mwh": (
            horizon_input.renewable_available_mwh
        ),
        "actual_renewable_available_mwh": service[
            "actual_renewable_available_mwh"
        ],
        "epsilon_curtailment_ceiling_mwh": service[
            "epsilon_curtailment_ceiling_mwh"
        ],
        "pcc_export_target_mwh": service["pcc_export_target_mwh"],
        "service_contract_sha256": _sha256(args.service_file),
        "solver": {
            "name": "appsi_highs",
            "threads": args.solver_threads,
            "random_seed": 0,
            "mip_rel_gap": args.mip_rel_gap,
            "time_limit_seconds": args.time_limit_seconds,
        },
        "provenance": _common_provenance(args),
    }


def build_case_audit(args: argparse.Namespace) -> dict:
    """Build, but do not solve, one canonical case for resource sizing."""

    state = state_spec(args.state)
    architecture = Architecture(args.architecture)
    service = _load_service_contract(args.service_file, state)
    horizon_input = _case_horizon_input(args, state)
    planning_inputs = planning_inputs_for_state(args.price_basis_path, state)
    curtailment_service, pcc_service = _service_specs(service, state)
    case = build_d38_case(
        state=state,
        architecture=architecture,
        horizon_input=horizon_input,
        planning_inputs=planning_inputs,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=COAL_PRICE_CNY_PER_TCE,
            curtailment_penalty_cny_per_mwh=0.0,
        ),
        curtailment_service=curtailment_service,
        pcc_export_service=pcc_service,
    )
    snapshot = _capacity_for_phase(args, architecture)
    started = perf_counter()
    model = build_endogenous_capacity_model(case)
    if snapshot is not None:
        fix_endogenous_capacity_snapshot(model, case, snapshot)
    build_runtime = perf_counter() - started
    payload = _case_base_payload(
        args,
        state=state,
        architecture=architecture,
        horizon_input=horizon_input,
        service=service,
    )
    payload.update(
        {
            "schema_id": BUILD_SCHEMA_ID,
            "status": "build_complete_no_solve",
            "build_runtime_seconds": build_runtime,
            "model_size": _model_size(model),
            "fixed_capacity": (
                None if snapshot is None else _snapshot_payload(snapshot)
            ),
        }
    )
    return payload


def _failure_status(error: Exception) -> str:
    message = str(error).lower()
    if "infeasible" in message or "feasible solution was not found" in message:
        return "infeasible"
    if "relative_gap" in message or "accepted gap" in message:
        return "bounded_incomplete"
    return "solve_failed"


def run_case(args: argparse.Namespace) -> dict:
    """Solve one restartable architecture/state/horizon D38 task."""

    state = state_spec(args.state)
    architecture = Architecture(args.architecture)
    service = _load_service_contract(args.service_file, state)
    horizon_input = _case_horizon_input(args, state)
    planning_inputs = planning_inputs_for_state(args.price_basis_path, state)
    curtailment_service, pcc_service = _service_specs(service, state)
    case = build_d38_case(
        state=state,
        architecture=architecture,
        horizon_input=horizon_input,
        planning_inputs=planning_inputs,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=COAL_PRICE_CNY_PER_TCE,
            curtailment_penalty_cny_per_mwh=0.0,
        ),
        curtailment_service=curtailment_service,
        pcc_export_service=pcc_service,
    )
    snapshot = _capacity_for_phase(args, architecture)
    payload = _case_base_payload(
        args,
        state=state,
        architecture=architecture,
        horizon_input=horizon_input,
        service=service,
    )
    solver = _solver_from_args(args)
    started = perf_counter()
    try:
        result = solve_endogenous_capacity(
            case,
            solver=solver,
            fixed_capacity=snapshot,
            maximum_accepted_relative_gap=args.mip_rel_gap,
        )
    except Exception as error:  # noqa: BLE001 - the artifact must retain solver failure
        payload.update(
            {
                "status": _failure_status(error),
                "runtime_seconds": perf_counter() - started,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "fixed_capacity": (
                    None if snapshot is None else _snapshot_payload(snapshot)
                ),
            }
        )
        return payload
    runtime = perf_counter() - started
    result_payload = _result_payload(result, runtime)
    pcc_residual = result.weighted_pcc_export_mwh - service["pcc_export_target_mwh"]
    curtailment_slack = (
        service["epsilon_curtailment_ceiling_mwh"]
        - result.weighted_curtailment_mwh
    )
    result_snapshot = EndogenousCapacitySnapshot.from_result(result)
    payload.update(
        {
            "status": "complete",
            "runtime_seconds": runtime,
            "result": result_payload,
            "capacity_snapshot": _snapshot_payload(result_snapshot),
            "service_audit": {
                "pcc_export_residual_mwh": pcc_residual,
                "curtailment_ceiling_slack_mwh": curtailment_slack,
                "curtailment_rate_on_horizon_availability": (
                    result.weighted_curtailment_mwh
                    / horizon_input.renewable_available_mwh
                ),
                "curtailment_rate_on_actual_availability": (
                    result.weighted_curtailment_mwh
                    / service["actual_renewable_available_mwh"]
                ),
            },
            "fixed_capacity": (
                None if snapshot is None else _snapshot_payload(snapshot)
            ),
        }
    )
    return payload


def _add_common_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--heat-path", type=Path, required=True)
    parser.add_argument("--vre-path", type=Path, required=True)
    parser.add_argument("--periods-path", type=Path, required=True)
    parser.add_argument("--price-basis-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solver-threads", type=int, default=1)
    parser.add_argument("--mip-rel-gap", type=float, default=FORMAL_MIP_REL_GAP)
    parser.add_argument("--time-limit-seconds", type=float)


def _add_case_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", choices=tuple(STATES), required=True)
    parser.add_argument(
        "--architecture",
        choices=tuple(architecture.value for architecture in Architecture),
        required=True,
    )
    parser.add_argument(
        "--phase",
        choices=(
            "representative_planning",
            "full_year_fixed",
            "full_year_reoptimization",
        ),
        required=True,
    )
    parser.add_argument("--service-file", type=Path, required=True)
    parser.add_argument("--capacity-result", type=Path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    reference = subparsers.add_parser("reference")
    _add_common_inputs(reference)
    reference.add_argument(
        "--state",
        choices=("baseline", "high_heat_tight_pcc"),
        required=True,
    )
    case = subparsers.add_parser("case")
    _add_common_inputs(case)
    _add_case_arguments(case)
    build = subparsers.add_parser("build")
    _add_common_inputs(build)
    _add_case_arguments(build)
    return parser


def _validate_solver_arguments(args: argparse.Namespace) -> None:
    if args.solver_threads < 1:
        raise ValueError("solver threads must be at least one")
    if (
        not math.isfinite(args.mip_rel_gap)
        or args.mip_rel_gap < 0.0
        or args.mip_rel_gap > FORMAL_MIP_REL_GAP
    ):
        raise ValueError("D38 mip-rel-gap must lie in [0, 0.001]")
    if args.time_limit_seconds is not None and (
        not math.isfinite(args.time_limit_seconds) or args.time_limit_seconds <= 0.0
    ):
        raise ValueError("time limit must be finite and positive")


def _write_payload(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    args = build_parser().parse_args()
    _validate_solver_arguments(args)
    if args.command == "reference":
        payload = run_service_reference(args)
    elif args.command == "build":
        payload = build_case_audit(args)
    else:
        payload = run_case(args)
    _write_payload(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
