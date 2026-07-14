"""E0-D-34 four-architecture endogenous-capacity sample runner.

The runner uses the formal E0-B heat series and the legacy mapped VRE bridge.
It is a controlled public-cost sensitivity, not a project-specific Yangling
TAC result.  A two-stage no-storage reference first identifies the minimum
curtailment and then the fuel-minimizing annual PCC delivery at that service.
Both services are imposed unchanged on all four architectures.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from time import perf_counter

from tes_bess_boundary.capacity_planning import (
    BESSPlanningBounds,
    BESSPlanningSpec,
    TESPlanningBounds,
    TESPlanningSpec,
)
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
    PCC_CAPACITY_MW,
    PV_CAPACITY_MW,
    WIND_CAPACITY_MW,
    build_e0d17_tes_spec,
    load_e0d17_inputs,
)
from tes_bess_boundary.economics import AnnualHorizonSpec, ProjectFinance
from tes_bess_boundary.formal_bess_costs import (
    build_resolved_rahman_bess_join_contract,
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
    solve_endogenous_capacity,
)
from tes_bess_boundary.price_basis import load_price_basis_snapshot
from tes_bess_boundary.public_tes_costs import build_public_tes_cost_portfolio
from tes_bess_boundary.solver import create_highs_solver


SCHEMA_ID = "tes_bess_boundary.e0d34_endogenous_capacity_sample.v1"
SERVICE_TOLERANCE_MWH = 1e-3


def _window(rows: tuple, start: datetime, hours: int) -> tuple:
    by_timestamp = {row.timestamp: index for index, row in enumerate(rows)}
    if start not in by_timestamp:
        raise ValueError("sample start is absent from the annual input")
    offset = by_timestamp[start]
    selected = rows[offset : offset + hours]
    if len(selected) != hours:
        raise ValueError("sample window extends beyond the annual input")
    return selected


def _planning_inputs(price_basis_path: Path):
    snapshot = load_price_basis_snapshot(price_basis_path)
    fixed_tes = build_e0d17_tes_spec()
    template = replace(
        fixed_tes.physics,
        salt_mass_t=1.0,
        ht_tank_capacity_t=1.0,
        mt_tank_capacity_t=1.0,
        lt_tank_capacity_t=1.0,
    )
    salt_upper = fixed_tes.physics.salt_mass_t * 4.0
    tes = TESPlanningSpec(
        physics_template=template,
        bounds=TESPlanningBounds(
            salt_mass_upper_t=salt_upper,
            ht_tank_capacity_upper_t=salt_upper,
            mt_tank_capacity_upper_t=salt_upper,
            lt_tank_capacity_upper_t=salt_upper,
            electric_charge_input_upper_mw=300.0,
            steam_to_ht_input_upper_mw=300.0,
            steam_to_mt_input_upper_mw=300.0,
            electric_output_upper_mw=300.0,
            heat_output_upper_mw=300.0,
        ),
        initial_inventory_fractions=(0.0, 0.0, 1.0),
        minimum_service_duration_hours=2.0,
        maximum_service_duration_hours=24.0,
        cyclic=True,
    )
    bess = BESSPlanningSpec(
        bounds=BESSPlanningBounds(
            energy_capacity_upper_mwh=2_400.0,
            charge_power_upper_mw=100.0,
            discharge_power_upper_mw=100.0,
        ),
        soc_min=0.10,
        soc_max=0.90,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        initial_soc_fraction=0.50,
        hourly_loss=0.0,
        minimum_discharge_duration_hours=2.0,
        maximum_discharge_duration_hours=24.0,
        cyclic=True,
    )
    bess_economics = (
        build_resolved_rahman_bess_join_contract().build_planning_economics(
            finance=ProjectFinance(project_years=20, real_discount_rate=0.10),
            conversion=snapshot.to_conversion("USD", 2019),
            reference_annual_ac_efc=365.0,
            ac_deliverable_fraction=0.95 * (0.90 - 0.10),
        )
    )
    tes_costs = build_public_tes_cost_portfolio(
        "aggregate_storage",
        "base",
        acknowledge_author_assumptions=True,
        price_basis_snapshot=snapshot,
    )
    return bess, bess_economics, tes, fixed_tes.loss_auxiliary, tes_costs


def _case(
    architecture: Architecture,
    rows: tuple,
    *,
    objective: ValidationObjectiveSpec,
    service: AnnualCurtailmentServiceSpec | None,
    pcc_service: AnnualPCCExportServiceSpec | None,
    planning_inputs: tuple,
) -> EndogenousCapacityCase:
    bess, bess_economics, tes, loss_auxiliary, tes_costs = planning_inputs
    includes_bess = architecture in (Architecture.BESS, Architecture.HYBRID)
    includes_tes = architecture in (Architecture.TES, Architecture.HYBRID)
    weights = (8_784.0 / len(rows),) * len(rows)
    return EndogenousCapacityCase(
        architecture=architecture,
        timeseries=E0CTimeSeries(
            heat_demand_mw=tuple(row.heat_demand_mw for row in rows),
            wind_available_mw=tuple(WIND_CAPACITY_MW * row.wind_cf for row in rows),
            pv_available_mw=tuple(PV_CAPACITY_MW * row.pv_cf for row in rows),
            ambient_temperature_c=tuple(
                row.ambient_temperature_c for row in rows
            ),
        ),
        chp_units=yangling_chp_specs(
            low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE
        ),
        chp_initial_online=(1, 1),
        chp_terminal_online=(1, 1),
        pcc_export_capacity_mw=PCC_CAPACITY_MW,
        horizon=AnnualHorizonSpec(weights),
        bess=bess if includes_bess else None,
        bess_economics=bess_economics if includes_bess else None,
        tes=tes if includes_tes else None,
        tes_cost_portfolio=tes_costs if includes_tes else None,
        tes_loss_auxiliary=loss_auxiliary if includes_tes else None,
        objective=objective,
        curtailment_service=service,
        pcc_export_service=pcc_service,
        chp_fuel_segment_formulation=FuelSegmentFormulation.LOGARITHMIC,
        chp_transition_formulation=(
            CommitmentTransitionFormulation.CONTINUOUS_ENVELOPE
        ),
    )


def _result_payload(result, runtime_seconds: float) -> dict:
    payload = asdict(result)
    payload["architecture"] = result.architecture.value
    payload["runtime_seconds"] = runtime_seconds
    return payload


def run_sample(args: argparse.Namespace) -> dict:
    rows = load_e0d17_inputs(args.heat_path, args.vre_path)
    selected = _window(rows, datetime.fromisoformat(args.start), args.hours)
    planning_inputs = _planning_inputs(args.price_basis_path)
    solver = create_highs_solver(
        threads=args.solver_threads,
        random_seed=0,
        mip_rel_gap=args.mip_rel_gap,
    )
    explicit_curtailment = args.curtailment_ceiling_mwh
    explicit_pcc_export = args.pcc_export_target_mwh
    if (explicit_curtailment is None) != (explicit_pcc_export is None):
        raise ValueError(
            "curtailment ceiling and PCC export target must be supplied together"
        )
    if explicit_curtailment is None:
        service_case = _case(
            Architecture.NO_STORAGE,
            selected,
            objective=ValidationObjectiveSpec(
                coal_price_cny_per_tce=0.0,
                curtailment_penalty_cny_per_mwh=1.0,
            ),
            service=None,
            pcc_service=None,
            planning_inputs=planning_inputs,
        )
        started = perf_counter()
        service_result = solve_endogenous_capacity(service_case, solver=solver)
        service_runtime = perf_counter() - started
        service_ceiling = (
            service_result.weighted_curtailment_mwh + SERVICE_TOLERANCE_MWH
        )
        curtailment_service = AnnualCurtailmentServiceSpec(
            service_id=f"e0d34_no_storage_min_curtailment_{args.hours}h",
            maximum_curtailment_mwh=service_ceiling,
        )
        reference_case = _case(
            Architecture.NO_STORAGE,
            selected,
            objective=ValidationObjectiveSpec(
                coal_price_cny_per_tce=COAL_PRICE_CNY_PER_TCE,
                curtailment_penalty_cny_per_mwh=0.0,
            ),
            service=curtailment_service,
            pcc_service=None,
            planning_inputs=planning_inputs,
        )
        started = perf_counter()
        reference_result = solve_endogenous_capacity(reference_case, solver=solver)
        reference_runtime = perf_counter() - started
        pcc_export_target = reference_result.weighted_pcc_export_mwh
    else:
        service_result = None
        service_runtime = None
        reference_result = None
        reference_runtime = None
        service_ceiling = explicit_curtailment
        pcc_export_target = explicit_pcc_export
    if not math.isfinite(service_ceiling) or service_ceiling < 0.0:
        raise ValueError("curtailment ceiling must be finite and non-negative")
    if not math.isfinite(pcc_export_target) or pcc_export_target < 0.0:
        raise ValueError("PCC export target must be finite and non-negative")

    requested = (
        tuple(Architecture)
        if args.architecture == "all"
        else (Architecture(args.architecture),)
    )
    service = AnnualCurtailmentServiceSpec(
        service_id=f"e0d34_no_storage_min_curtailment_{args.hours}h",
        maximum_curtailment_mwh=service_ceiling,
    )
    pcc_service = AnnualPCCExportServiceSpec(
        service_id=f"e0d34_no_storage_economic_pcc_{args.hours}h",
        target_export_mwh=pcc_export_target,
    )
    results = []
    for architecture in requested:
        case = _case(
            architecture,
            selected,
            objective=ValidationObjectiveSpec(
                coal_price_cny_per_tce=COAL_PRICE_CNY_PER_TCE,
                curtailment_penalty_cny_per_mwh=0.0,
            ),
            service=service,
            pcc_service=pcc_service,
            planning_inputs=planning_inputs,
        )
        started = perf_counter()
        result = solve_endogenous_capacity(case, solver=solver)
        results.append(_result_payload(result, perf_counter() - started))

    return {
        "schema_id": SCHEMA_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "claim_scope": "controlled_public_cost_sensitivity_not_formal_project_tac",
        "formal_project_tac_ready": False,
        "data_scope": "formal_2024_heat_plus_legacy_2019_vre_shapes",
        "formal_heat_sha256": FORMAL_HEAT_SHA256,
        "legacy_vre_sha256": LEGACY_VRE_SHA256,
        "start": args.start,
        "hours": args.hours,
        "annual_hours": 8_784.0,
        "curtailment_service_ceiling_mwh": service_ceiling,
        "pcc_export_service_target_mwh": pcc_export_target,
        "service_search_runtime_seconds": service_runtime,
        "pcc_reference_search_runtime_seconds": reference_runtime,
        "solver": {
            "name": "appsi_highs",
            "threads": args.solver_threads,
            "random_seed": 0,
            "mip_rel_gap": args.mip_rel_gap,
        },
        "author_engineering_bounds": {
            "bess_energy_upper_mwh": 2_400.0,
            "bess_common_pcs_source_domain_mw": [5.0, 100.0],
            "tes_salt_upper_multiple_of_1200mwh_slice": 4.0,
            "tes_port_upper_mw": 300.0,
            "service_duration_hours": [2.0, 24.0],
        },
        "chp_formulation": {
            "fuel_segments": FuelSegmentFormulation.LOGARITHMIC.value,
            "commitment_transitions": (
                CommitmentTransitionFormulation.CONTINUOUS_ENVELOPE.value
            ),
        },
        "service_search": (
            None
            if service_result is None
            else _result_payload(service_result, service_runtime or 0.0)
        ),
        "pcc_reference_search": (
            None
            if reference_result is None
            else _result_payload(reference_result, reference_runtime or 0.0)
        ),
        "architectures": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heat-path", type=Path, required=True)
    parser.add_argument("--vre-path", type=Path, required=True)
    parser.add_argument("--price-basis-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", default="2024-01-01T00:00:00")
    parser.add_argument("--hours", type=int, choices=(24, 336), required=True)
    parser.add_argument(
        "--architecture",
        choices=("all", *(architecture.value for architecture in Architecture)),
        default="all",
    )
    parser.add_argument("--curtailment-ceiling-mwh", type=float)
    parser.add_argument("--pcc-export-target-mwh", type=float)
    parser.add_argument("--solver-threads", type=int, default=1)
    parser.add_argument("--mip-rel-gap", type=float, default=0.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = run_sample(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
