"""Static necessary-condition diagnostic for a failed D38 service reference."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

from tes_bess_boundary.components.chp import LowLoadFuelRule, yangling_chp_specs
from tes_bess_boundary.e0d17_exploration import FORMAL_HEAT_SHA256
from tes_bess_boundary.e0d37_block_horizon import load_e0d37_block_horizon
from tes_bess_boundary.e0d38_prevalidation import state_spec
from tes_bess_boundary.solver import create_highs_solver


SCHEMA_ID = "tes_bess_boundary.e0d38_static_pcc_heat_feasibility.v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_heat(path: Path, heat_scale: float) -> tuple[tuple[datetime, float], ...]:
    if _sha256(path) != FORMAL_HEAT_SHA256:
        raise ValueError("formal E0-B heat input SHA-256 mismatch")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = tuple(csv.DictReader(handle))
    if len(rows) != 8_784:
        raise ValueError("formal heat input must contain 8784 hourly rows")
    loaded: list[tuple[datetime, float]] = []
    for row in rows:
        timestamp = datetime.fromisoformat(row["timestamp"])
        heat = float(row["heat_net_mw"])
        if not math.isfinite(heat):
            raise ValueError("formal heat input contains a non-finite value")
        loaded.append((timestamp, heat_scale * max(0.0, heat)))
    return tuple(loaded)


def _maximum_static_heat_mw(pcc_export_capacity_mw: float) -> dict:
    """Maximize useful heat with all renewables curtailed and no storage."""

    from pyomo.environ import (
        Binary,
        ConcreteModel,
        Constraint,
        Expression,
        NonNegativeReals,
        Objective,
        RangeSet,
        Var,
        maximize,
        value,
    )

    units = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE
    )
    vertices = tuple(unit.unit.feasible_region.vertices for unit in units)
    vertex_count = len(vertices[0])
    if any(len(unit_vertices) != vertex_count for unit_vertices in vertices):
        raise ValueError("static diagnostic requires equal CHP vertex counts")
    model = ConcreteModel()
    model.units = RangeSet(0, len(units) - 1)
    model.vertices = RangeSet(0, vertex_count - 1)
    model.online = Var(model.units, domain=Binary)
    model.weight = Var(model.units, model.vertices, domain=NonNegativeReals)
    model.convexity = Constraint(
        model.units,
        rule=lambda block, unit: sum(
            block.weight[unit, vertex] for vertex in block.vertices
        )
        == block.online[unit],
    )
    model.useful_heat_mw = Expression(
        expr=sum(
            model.weight[unit, vertex] * vertices[unit][vertex].heat_mw
            for unit in model.units
            for vertex in model.vertices
        )
    )
    model.minimum_net_chp_export_mw = Expression(
        expr=sum(
            model.weight[unit, vertex]
            * vertices[unit][vertex].power_gross_mw
            * (1.0 - units[unit].unit.auxiliary_rate)
            for unit in model.units
            for vertex in model.vertices
        )
    )
    model.pcc_limit = Constraint(
        expr=model.minimum_net_chp_export_mw <= pcc_export_capacity_mw
    )
    model.maximum_heat = Objective(expr=model.useful_heat_mw, sense=maximize)
    solver = create_highs_solver(threads=1, random_seed=0, mip_rel_gap=0.0)
    result = solver.solve(model)
    termination = str(result.solver.termination_condition).lower()
    if termination != "optimal":
        raise RuntimeError(f"static heat/PCC diagnostic did not solve: {termination}")
    return {
        "termination_condition": termination,
        "maximum_static_useful_heat_mw": float(value(model.useful_heat_mw)),
        "net_chp_export_at_maximum_heat_mw": float(
            value(model.minimum_net_chp_export_mw)
        ),
        "unit_online": [float(value(model.online[unit])) for unit in model.units],
        "unit_power_gross_mw": [
            sum(
                float(value(model.weight[unit, vertex]))
                * vertices[unit][vertex].power_gross_mw
                for vertex in model.vertices
            )
            for unit in model.units
        ],
        "unit_useful_heat_mw": [
            sum(
                float(value(model.weight[unit, vertex]))
                * vertices[unit][vertex].heat_mw
                for vertex in model.vertices
            )
            for unit in model.units
        ],
    }


def run_diagnostic(args: argparse.Namespace) -> dict:
    state = state_spec(args.state)
    heat = _load_heat(args.heat_path, state.heat_scale)
    static_limit = _maximum_static_heat_mw(state.pcc_export_capacity_mw)
    threshold = static_limit["maximum_static_useful_heat_mw"]
    violations = tuple(
        (hour, timestamp, demand)
        for hour, (timestamp, demand) in enumerate(heat)
        if demand > threshold + args.tolerance_mw
    )
    representative = load_e0d37_block_horizon(args.periods_path)
    representative_hours = frozenset(representative.source_hour_indices)
    violating_hours = frozenset(hour for hour, _timestamp, _demand in violations)
    return {
        "schema_id": SCHEMA_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "claim_scope": "necessary_static_feasibility_diagnostic_not_tac",
        "state": {
            "state_id": state.state_id,
            "heat_scale": state.heat_scale,
            "pcc_export_capacity_mw": state.pcc_export_capacity_mw,
        },
        "static_limit": static_limit,
        "tolerance_mw": args.tolerance_mw,
        "violating_hour_count": len(violations),
        "maximum_scaled_heat_demand_mw": max(demand for _timestamp, demand in heat),
        "violating_week_numbers": sorted(
            {hour // 168 + 1 for hour, _timestamp, _demand in violations}
        ),
        "violating_hours_covered_by_d36_count": len(
            violating_hours & representative_hours
        ),
        "all_violating_hours_covered_by_d36": violating_hours.issubset(
            representative_hours
        ),
        "violations": [
            {
                "source_hour_index": hour,
                "timestamp": timestamp.isoformat(),
                "scaled_heat_demand_mw": demand,
                "excess_heat_mw": demand - threshold,
            }
            for hour, timestamp, demand in violations
        ],
        "interpretation": (
            "Any listed hour is infeasible for no-storage operation even after all "
            "renewables are curtailed, before ramping, minimum-up/down, annual "
            "service, or fuel objectives are imposed."
        ),
        "provenance": {
            "formal_heat_sha256": _sha256(args.heat_path),
            "representative_periods_sha256": _sha256(args.periods_path),
            "code_sha256": _sha256(Path(__file__)),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", choices=("high_heat_tight_pcc",), required=True)
    parser.add_argument("--heat-path", type=Path, required=True)
    parser.add_argument("--periods-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tolerance-mw", type=float, default=1e-7)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not math.isfinite(args.tolerance_mw) or args.tolerance_mw < 0.0:
        raise ValueError("tolerance must be finite and non-negative")
    payload = run_diagnostic(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
