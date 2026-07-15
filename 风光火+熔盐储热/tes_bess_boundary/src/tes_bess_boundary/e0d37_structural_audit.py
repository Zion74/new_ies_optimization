"""Build-only structural audit for the formal E0-D-37 block horizon.

This command instantiates the 1080-period Hybrid planning model and audits its
linear block-boundary structure.  It deliberately never invokes a solver.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
from time import perf_counter

from tes_bess_boundary.components.chp import (
    CommitmentTransitionFormulation,
    FuelSegmentFormulation,
    LowLoadFuelRule,
    yangling_chp_specs,
)
from tes_bess_boundary.e0d17_exploration import COAL_PRICE_CNY_PER_TCE, PCC_CAPACITY_MW
from tes_bess_boundary.e0d34_endogenous_capacity_sample import _planning_inputs
from tes_bess_boundary.e0d37_block_horizon import load_e0d37_block_horizon
from tes_bess_boundary.model import Architecture, ValidationObjectiveSpec
from tes_bess_boundary.planning_model import (
    EndogenousCapacityCase,
    build_endogenous_capacity_model,
)


SCHEMA_ID = "tes_bess_boundary.e0d37_structural_audit.v1"
MANIFEST_NAME = "manifest.json"
EXECUTION_NAME = "execution.json"


def _canonical_json_bytes(payload: dict) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def build_e0d37_structural_audit(
    periods_csv: Path,
    price_basis_path: Path,
) -> tuple[dict, float]:
    """Instantiate the formal Hybrid boundary and return a deterministic audit."""

    from pyomo.environ import Constraint, Objective, Var, value
    from pyomo.repn import generate_standard_repn

    started = perf_counter()
    loaded = load_e0d37_block_horizon(periods_csv)
    bess, bess_economics, tes, loss_auxiliary, tes_costs = _planning_inputs(
        price_basis_path
    )
    case = EndogenousCapacityCase(
        architecture=Architecture.HYBRID,
        timeseries=loaded.timeseries,
        chp_units=yangling_chp_specs(
            low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE
        ),
        chp_initial_online=(1, 1),
        chp_terminal_online=(1, 1),
        pcc_export_capacity_mw=PCC_CAPACITY_MW,
        horizon=loaded.horizon,
        bess=bess,
        bess_economics=bess_economics,
        tes=tes,
        tes_cost_portfolio=tes_costs,
        tes_loss_auxiliary=loss_auxiliary,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=COAL_PRICE_CNY_PER_TCE,
            curtailment_penalty_cny_per_mwh=0.0,
        ),
        chp_fuel_segment_formulation=FuelSegmentFormulation.LOGARITHMIC,
        chp_transition_formulation=CommitmentTransitionFormulation.BINARY,
    )
    model = build_endogenous_capacity_model(case)

    nonlinear_components: list[str] = []
    for component_type in (Constraint, Objective):
        for item in model.component_data_objects(component_type, active=True):
            expression = item.body if component_type is Constraint else item.expr
            representation = generate_standard_repn(expression)
            if representation.nonlinear_expr is not None or representation.quadratic_vars:
                nonlinear_components.append(item.name)

    chp_transition_counts = tuple(
        len(model.chp[unit].commitment_transition) for unit in model.unit_index
    )
    chp_ramp_up_counts = tuple(
        len(model.chp[unit].normal_ramp_up) for unit in model.unit_index
    )
    chp_ramp_down_counts = tuple(
        len(model.chp[unit].normal_ramp_down) for unit in model.unit_index
    )
    initial_state_constraints_absent = {
        "bess_initial_energy": not hasattr(model.bess, "initial_energy"),
        "tes_initial_ht": not hasattr(model.tes, "initial_ht"),
        "tes_initial_mt": not hasattr(model.tes, "initial_mt"),
        "tes_initial_lt": not hasattr(model.tes, "initial_lt"),
        "chp_terminal_online": all(
            not hasattr(model.chp[unit], "terminal_online")
            for unit in model.unit_index
        ),
    }
    period_count = loaded.timeseries.period_count
    block_count = len(loaded.horizon.dispatch_blocks)
    expected_state_count = period_count + block_count
    passed = all(
        (
            period_count == 1_080,
            block_count == 7,
            len(model.bess.states) == expected_state_count,
            len(model.tes.states) == expected_state_count,
            len(model.bess.cyclic_energy) == block_count,
            len(model.tes.cyclic_ht) == block_count,
            len(model.tes.cyclic_mt) == block_count,
            len(model.tes.cyclic_lt) == block_count,
            all(count == period_count for count in chp_transition_counts),
            all(count == period_count for count in chp_ramp_up_counts),
            all(count == period_count for count in chp_ramp_down_counts),
            all(initial_state_constraints_absent.values()),
            not nonlinear_components,
            sum(weight == 0.0 for weight in loaded.horizon.period_weights) == 24,
            abs(float(value(model.annual_weighted_hours)) - 8_784.0) <= 1e-9,
        )
    )
    runtime_seconds = perf_counter() - started
    manifest = {
        "schema_id": SCHEMA_ID,
        "claim_scope": (
            "build_only_block_boundary_audit_not_d38_not_technology_comparison_"
            "not_formal_project_tac"
        ),
        "formal_project_tac_ready": False,
        "solver_invoked": False,
        "source": {
            "d36_periods_sha256": loaded.source_sha256,
            "period_count": period_count,
            "weighted_scored_hours": float(value(model.annual_weighted_hours)),
            "zero_weight_warmup_periods": sum(
                weight == 0.0 for weight in loaded.horizon.period_weights
            ),
        },
        "block_horizon": {
            "block_ids": list(loaded.block_ids),
            "block_lengths": [
                len(block.periods) for block in loaded.horizon.dispatch_blocks
            ],
            "block_count": block_count,
            "cross_block_state_transfer_allowed": False,
            "shared_capacity_variables": True,
            "independent_block_initial_states": True,
        },
        "state_audit": {
            "expected_state_nodes_per_storage": expected_state_count,
            "bess_state_nodes": len(model.bess.states),
            "tes_state_nodes": len(model.tes.states),
            "bess_cyclic_constraints": len(model.bess.cyclic_energy),
            "tes_cyclic_constraints_per_inventory": {
                "ht": len(model.tes.cyclic_ht),
                "mt": len(model.tes.cyclic_mt),
                "lt": len(model.tes.cyclic_lt),
            },
            "fixed_initial_or_terminal_constraints_absent": (
                initial_state_constraints_absent
            ),
        },
        "chp_audit": {
            "unit_count": len(tuple(model.unit_index)),
            "transition_constraints_per_unit": list(chp_transition_counts),
            "ramp_up_constraints_per_unit": list(chp_ramp_up_counts),
            "ramp_down_constraints_per_unit": list(chp_ramp_down_counts),
            "first_hour_wraps_to_same_block_tail": True,
        },
        "linearity_audit": {
            "active_variable_count": sum(
                1 for _item in model.component_data_objects(Var, active=True)
            ),
            "active_binary_variable_count": sum(
                1
                for item in model.component_data_objects(Var, active=True)
                if item.is_binary()
            ),
            "active_constraint_count": sum(
                1 for _item in model.component_data_objects(Constraint, active=True)
            ),
            "nonlinear_component_count": len(nonlinear_components),
            "nonlinear_components": nonlinear_components,
        },
        "audit": {"passed": passed},
    }
    if not passed:
        raise RuntimeError("E0-D-37 structural audit failed")
    return manifest, runtime_seconds


def write_e0d37_structural_audit(
    periods_csv: Path,
    price_basis_path: Path,
    output_dir: Path,
) -> dict:
    """Write canonical structural evidence and non-canonical execution metadata."""

    manifest, runtime_seconds = build_e0d37_structural_audit(
        periods_csv,
        price_basis_path,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / MANIFEST_NAME
    manifest_payload = _canonical_json_bytes(manifest)
    manifest_path.write_bytes(manifest_payload)
    execution = {
        "schema_id": f"{SCHEMA_ID}.execution",
        "runtime_seconds": runtime_seconds,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
    }
    (output_dir / EXECUTION_NAME).write_bytes(_canonical_json_bytes(execution))
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--periods-csv", type=Path, required=True)
    parser.add_argument("--price-basis-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    write_e0d37_structural_audit(
        args.periods_csv,
        args.price_basis_path,
        args.output_dir,
    )


if __name__ == "__main__":
    main()
