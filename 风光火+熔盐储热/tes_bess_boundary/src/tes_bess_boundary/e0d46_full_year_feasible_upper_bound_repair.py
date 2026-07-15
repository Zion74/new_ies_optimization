"""E0-D-46 deterministic seed and fixed-binary upper-bound repair.

The formal workflow is deliberately split into independently auditable stages:

1. fix the preregistered engineering capacity anchors and solve the R0 LP;
2. convert the finite R0 point into one deterministic, legal MIP start;
3. capture and interrupt at the first complete HiGHS MIP incumbent;
4. rebuild the original MILP, fix every original binary, and solve Repair A;
5. optionally release only continuous capacity variables for Repair B.

This module does not turn a relaxation bound or an unaudited incumbent into an
upper bound.  Only :func:`audit_repaired_solution` can grant the numerical
``audited_feasible_upper_bound_cny`` field used by D46.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from decimal import Decimal, ROUND_CEILING, localcontext
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

from tes_bess_boundary.e0d40_full_year_compute_gate import (
    EPSILON_CURTAILMENT_CEILING_MWH,
    FULL_YEAR_HOURS,
    PCC_EXPORT_TARGET_MWH,
    _linearity_audit,
)
from tes_bess_boundary.e0d40_gate_b_solver import (
    FORMAL_ARCHITECTURES,
    _build_gate_b_model,
)
from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
    BinaryInventory,
    RelaxationMode,
    apply_relaxation,
    collect_binary_inventory,
    extract_binary_snapshot,
    fix_binary_snapshot,
)
from tes_bess_boundary.model import Architecture
from tes_bess_boundary.solver import create_highs_solver


RESULT_SCHEMA_ID = "tes_bess_boundary.e0d46_feasible_upper_bound.v1"
SEED_SCHEMA_ID = "tes_bess_boundary.e0d46_deterministic_seed.v1"
REPAIR_SCHEMA_ID = "tes_bess_boundary.e0d46_fixed_binary_repair.v1"
CLAIM_SCOPE = "controlled_public_cost_sensitivity_not_formal_project_tac"
FORMAL_PROJECT_TAC_READY = False
TECHNICAL_RANKING_PERMITTED = False

D41_GATE_A_MANIFEST_SHA256 = (
    "50240e7ae557afa5633b29904585f1c1297a527343e467ce76d7766ce0177937"
)
D47_FORMAL_MANIFEST_SHA256 = (
    "8b74c4044854d18d5dffa6c2759bfe747455631e0347293d6a89c16d35276101"
)
D47_FORMAL_EXECUTION_SHA256 = (
    "ed978c3607f080456576e35dede75c57e017150514e24160462a62566bf9c330"
)
D41_BESS_R1_GUIDE_SHA256 = (
    "2d03ab0ae229583bbf46e3ebdd84ab0924627d7ac20e2af68dad42ff11de4614"
)

FORMAL_THREADS = 12
FORMAL_RANDOM_SEED = 0
SOLVER_FEASIBILITY_TOLERANCE = 1e-8
INDEPENDENT_ABSOLUTE_TOLERANCE = 1e-7
SERVICE_EXPORT_TOLERANCE_MW = 1e-8
SERVICE_CURTAILMENT_TOLERANCE_MWH = 1e-6
OBJECTIVE_ABSOLUTE_TOLERANCE_CNY = 0.01
OBJECTIVE_RELATIVE_TOLERANCE = 1e-10
MODE_ZERO_TOLERANCE = 1e-9
UPPER_BOUND_DECIMAL_PLACES = 10

GUIDE_SOFT_TIME_LIMIT_SECONDS = 900.0
GUIDE_HARD_WALL_SECONDS = 1_020.0
CANDIDATE_SOFT_TIME_LIMIT_SECONDS = 3_600.0
CANDIDATE_HARD_WALL_SECONDS = 3_720.0
REPAIR_A_HARD_WALL_SECONDS = 1_500.0
REPAIR_B_HARD_WALL_SECONDS = 1_500.0
ARCHITECTURE_HARD_WALL_SECONDS = 7_200.0
BATCH_HARD_WALL_SECONDS = 21_600.0

BESS_ENERGY_ANCHOR_MWH = 2_400.0
BESS_POWER_ANCHOR_MW = 100.0
TES_TANK_ANCHOR_T = 55_654.86255374656
TES_PORT_ANCHOR_MW = 300.0

EXPECTED_MODEL_SIZE = {
    Architecture.BESS: {
        "active_variable_count": 597_318,
        "active_constraint_count": 527_053,
        "active_binary_variable_count": 79_057,
        "nonlinear_component_count": 0,
        "nonlinear_components": [],
    },
    Architecture.TES: {
        "active_variable_count": 650_052,
        "active_constraint_count": 606_163,
        "active_binary_variable_count": 87_840,
        "nonlinear_component_count": 0,
        "nonlinear_components": [],
    },
    Architecture.HYBRID: {
        "active_variable_count": 685_194,
        "active_constraint_count": 667_662,
        "active_binary_variable_count": 96_625,
        "nonlinear_component_count": 0,
        "nonlinear_components": [],
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(directory: Path) -> str:
    if not directory.is_dir():
        raise ValueError(f"D46 expected a directory: {directory}")
    digest = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _name_list_sha256(names: tuple[str, ...]) -> str:
    body = "".join(f"{name}\n" for name in names).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _load_locked_d41_gate_a(path: Path) -> dict[str, Any]:
    if _sha256(path) != D41_GATE_A_MANIFEST_SHA256:
        raise ValueError("D46 D41 Gate A manifest hash mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_id") != (
        "tes_bess_boundary.e0d41_gate_a_manifest.v1"
    ):
        raise ValueError("D46 D41 Gate A schema mismatch")
    if payload.get("status") != "gate_a_passed":
        raise ValueError("D46 requires a passed D41 Gate A")
    if payload.get("solver_invoked") is not False:
        raise ValueError("D46 D41 Gate A unexpectedly invoked a solver")
    if payload.get("audit", {}).get("passed") is not True:
        raise ValueError("D46 D41 Gate A audit is not passed")
    return payload


def _inventory_lock_audit(
    inventory: BinaryInventory,
    architecture: Architecture,
    gate_a: Mapping[str, Any],
) -> dict[str, Any]:
    actual = inventory.to_audit()
    expected = gate_a["binary_inventory"][architecture.value]
    keys = (
        "all_binary_variable_count",
        "topology_binary_variable_count",
        "operational_binary_variable_count",
        "classification_complete",
        "all_binary_names_sha256",
        "topology_binary_names_sha256",
        "operational_binary_names_sha256",
        "component_counts",
        "topology_component_allowlist",
    )
    mismatches = {
        key: {"expected": expected.get(key), "actual": actual.get(key)}
        for key in keys
        if actual.get(key) != expected.get(key)
    }
    return {
        "expected": expected,
        "actual": actual,
        "mismatches": mismatches,
        "passed": not mismatches,
    }


def _variable_map(model: object) -> dict[str, object]:
    from pyomo.environ import Var

    variables = list(
        model.component_data_objects(Var, active=True, descend_into=True)
    )
    mapping = {variable.name: variable for variable in variables}
    if len(mapping) != len(variables):
        raise ValueError("D46 model contains duplicate active variable names")
    return mapping


def _finite_value(component: object, name: str) -> float:
    from pyomo.environ import value

    raw = value(component, exception=False)
    if raw is None or not math.isfinite(float(raw)):
        raise ValueError(f"D46 value is not finite: {name}")
    return float(raw)


def _set_and_fix(variable: object, value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"D46 anchor is not finite: {name}")
    lower = variable.lb
    upper = variable.ub
    if lower is not None and value < float(lower) - 1e-9:
        raise ValueError(f"D46 anchor is below the model lower bound: {name}")
    if upper is not None and value > float(upper) + 1e-9:
        raise ValueError(f"D46 anchor is above the model upper bound: {name}")
    variable.fix(value)


def _continuous_capacity_variables(
    model: object,
    architecture: Architecture,
) -> dict[str, object]:
    variables: dict[str, object] = {}
    if architecture in (Architecture.BESS, Architecture.HYBRID):
        variables.update(
            {
                model.bess.energy_capacity_mwh.name: (
                    model.bess.energy_capacity_mwh
                ),
                model.bess.charge_power_capacity_mw.name: (
                    model.bess.charge_power_capacity_mw
                ),
                model.bess.discharge_power_capacity_mw.name: (
                    model.bess.discharge_power_capacity_mw
                ),
                model.bess.pcs_power_capacity_mw.name: (
                    model.bess.pcs_power_capacity_mw
                ),
            }
        )
    if architecture in (Architecture.TES, Architecture.HYBRID):
        for field in (
            "ht_tank_capacity_t",
            "mt_tank_capacity_t",
            "lt_tank_capacity_t",
            "electric_charge_input_capacity_mw",
            "steam_to_ht_input_capacity_mw",
            "steam_to_mt_input_capacity_mw",
            "electric_output_capacity_mw",
            "heat_output_capacity_mw",
        ):
            variable = getattr(model.tes, field)
            variables[variable.name] = variable
    return variables


def fix_engineering_capacity_anchor(
    model: object,
    architecture: Architecture,
) -> dict[str, Any]:
    """Fix only the preregistered external design capacities at their anchors."""

    if architecture not in FORMAL_ARCHITECTURES:
        raise ValueError("D46 capacity anchor requires BESS, TES, or Hybrid")
    expected: dict[str, float] = {}
    if architecture in (Architecture.BESS, Architecture.HYBRID):
        expected.update(
            {
                model.bess.energy_capacity_mwh.name: BESS_ENERGY_ANCHOR_MWH,
                model.bess.charge_power_capacity_mw.name: BESS_POWER_ANCHOR_MW,
                model.bess.discharge_power_capacity_mw.name: (
                    BESS_POWER_ANCHOR_MW
                ),
                model.bess.pcs_power_capacity_mw.name: BESS_POWER_ANCHOR_MW,
                model.bess.installed.name: 1.0,
            }
        )
    if architecture in (Architecture.TES, Architecture.HYBRID):
        for field in (
            "ht_tank_capacity_t",
            "mt_tank_capacity_t",
            "lt_tank_capacity_t",
        ):
            expected[getattr(model.tes, field).name] = TES_TANK_ANCHOR_T
        for field in (
            "electric_charge_input_capacity_mw",
            "steam_to_ht_input_capacity_mw",
            "steam_to_mt_input_capacity_mw",
            "electric_output_capacity_mw",
            "heat_output_capacity_mw",
        ):
            expected[getattr(model.tes, field).name] = TES_PORT_ANCHOR_MW

    variables = _variable_map(model)
    missing = sorted(set(expected) - set(variables))
    if missing:
        raise ValueError(f"D46 capacity anchor variables are missing: {missing}")
    for name, anchor in expected.items():
        _set_and_fix(variables[name], anchor, name)
    actual = {
        name: _finite_value(variables[name], name) for name in sorted(expected)
    }
    fixed = {name: bool(variables[name].fixed) for name in sorted(expected)}
    passed = all(
        fixed[name]
        and math.isclose(actual[name], expected[name], rel_tol=0.0, abs_tol=1e-9)
        for name in expected
    )
    return {
        "architecture": architecture.value,
        "anchor_values": {name: expected[name] for name in sorted(expected)},
        "actual_values": actual,
        "fixed": fixed,
        "external_design_variable_count": len(expected),
        "salt_mass_and_service_mass_left_free": (
            architecture in (Architecture.TES, Architecture.HYBRID)
            and not model.tes.salt_mass_t.fixed
            and not model.tes.ht_service_salt_mass_t.fixed
            and not model.tes.mt_service_salt_mass_t.fixed
        ),
        "passed": passed,
    }


def release_continuous_capacity_variables(
    model: object,
    architecture: Architecture,
) -> dict[str, Any]:
    """Release only continuous external capacities for optional Repair B."""

    capacities = _continuous_capacity_variables(model, architecture)
    for variable in capacities.values():
        variable.unfix()
    still_fixed = tuple(
        sorted(name for name, variable in capacities.items() if variable.fixed)
    )
    return {
        "released_capacity_variable_count": len(capacities) - len(still_fixed),
        "still_fixed_capacity_variable_count": len(still_fixed),
        "still_fixed_capacity_names_sha256": _name_list_sha256(still_fixed),
        "passed": len(still_fixed) == 0,
    }


def _binary_choice(
    positive_flow: float,
    negative_flow: float,
    *,
    zero_tolerance: float,
) -> int:
    if not all(math.isfinite(item) for item in (positive_flow, negative_flow)):
        raise ValueError("D46 mode seed received a non-finite flow")
    if max(abs(positive_flow), abs(negative_flow)) <= zero_tolerance:
        return 0
    return int(positive_flow > negative_flow)


def derive_binary_seed(
    model: object,
    inventory: BinaryInventory,
    *,
    zero_tolerance: float = MODE_ZERO_TOLERANCE,
) -> dict[str, int]:
    """Map one finite R0 point to the frozen complete legal binary seed."""

    if not math.isfinite(zero_tolerance) or zero_tolerance < 0.0:
        raise ValueError("D46 zero tolerance must be finite and non-negative")
    expected = set(inventory.all_names)
    seed: dict[str, int] = {}

    if hasattr(model, "bess") and hasattr(model.bess, "installed"):
        seed[model.bess.installed.name] = 1

    for unit_index in model.unit_index:
        block = model.chp[unit_index]
        for period in model.periods:
            online_value = _finite_value(
                block.online[period], block.online[period].name
            )
            online = int(online_value >= 0.5)
            seed[block.online[period].name] = online
            segment_values = tuple(
                (
                    int(segment),
                    _finite_value(
                        block.fuel_segment_active[period, segment],
                        block.fuel_segment_active[period, segment].name,
                    ),
                )
                for segment in block.fuel_segment_index
            )
            selected_segment = (
                0
                if online == 0
                else min(
                    segment
                    for segment, segment_value in segment_values
                    if segment_value
                    == max(value for _, value in segment_values)
                )
            )
            for bit in block.fuel_code_bit_index:
                seed[block.fuel_code_bit[period, bit].name] = (
                    selected_segment >> int(bit)
                ) & 1

    if hasattr(model, "bess"):
        for period in model.periods:
            charge = _finite_value(
                model.bess.charge_ac_mw[period],
                model.bess.charge_ac_mw[period].name,
            )
            discharge = _finite_value(
                model.bess.discharge_ac_mw[period],
                model.bess.discharge_ac_mw[period].name,
            )
            seed[model.bess.charge_mode[period].name] = _binary_choice(
                charge,
                discharge,
                zero_tolerance=zero_tolerance,
            )

    if hasattr(model, "tes"):
        for period in model.periods:
            receiving = _finite_value(
                model.tes.electric_lt_to_ht[period],
                model.tes.electric_lt_to_ht[period].name,
            ) + _finite_value(
                model.tes.steam_lt_to_ht[period],
                model.tes.steam_lt_to_ht[period].name,
            )
            sending = _finite_value(
                model.tes.power_ht_to_mt[period],
                model.tes.power_ht_to_mt[period].name,
            )
            seed[model.tes.ht_receiving_mode[period].name] = _binary_choice(
                receiving,
                sending,
                zero_tolerance=zero_tolerance,
            )
            direct_charge = _finite_value(
                model.tes.steam_lt_to_mt[period],
                model.tes.steam_lt_to_mt[period].name,
            )
            heat_discharge = _finite_value(
                model.tes.heat_mt_to_lt[period],
                model.tes.heat_mt_to_lt[period].name,
            )
            seed[model.tes.mt_direct_charge_mode[period].name] = _binary_choice(
                direct_charge,
                heat_discharge,
                zero_tolerance=zero_tolerance,
            )

    missing = sorted(expected - set(seed))
    extra = sorted(set(seed) - expected)
    if missing or extra:
        raise ValueError(
            "D46 deterministic rules do not cover the locked binary inventory: "
            f"missing={missing[:3]}, extra={extra[:3]}"
        )
    if any(value not in (0, 1) for value in seed.values()):
        raise AssertionError("D46 deterministic binary seed is not exact")
    return {name: seed[name] for name in inventory.all_names}


def derive_complete_seed(
    model: object,
    inventory: BinaryInventory,
) -> tuple[dict[str, float], dict[str, int]]:
    """Return finite values for every active column plus the legal binaries."""

    variables = _variable_map(model)
    values = {
        name: _finite_value(variable, name)
        for name, variable in sorted(variables.items())
    }
    binary_seed = derive_binary_seed(model, inventory)
    values.update({name: float(value) for name, value in binary_seed.items()})
    return values, binary_seed


def write_seed_csv_gz(
    output_path: Path,
    values: Mapping[str, float],
    binary_snapshot: Mapping[str, int],
) -> dict[str, Any]:
    """Write a byte-deterministic complete seed with an embedded class label."""

    names = tuple(sorted(values))
    if len(names) != len(values):
        raise ValueError("D46 seed contains duplicate variable names")
    unknown_binary = sorted(set(binary_snapshot) - set(values))
    if unknown_binary:
        raise ValueError(f"D46 binary seed contains unknown names: {unknown_binary}")
    for name in names:
        raw = values[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"D46 seed value is not numeric: {name}")
        if not math.isfinite(float(raw)):
            raise ValueError(f"D46 seed value is not finite: {name}")
    for name, raw in binary_snapshot.items():
        if raw not in (0, 1) or float(values[name]) != float(raw):
            raise ValueError(f"D46 binary seed is not exact: {name}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as raw_stream:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_stream,
            mtime=0,
        ) as compressed:
            with io.TextIOWrapper(
                compressed, encoding="utf-8", newline=""
            ) as text_stream:
                writer = csv.writer(text_stream, lineterminator="\n")
                writer.writerow(("variable_name", "value", "variable_class"))
                for name in names:
                    writer.writerow(
                        (
                            name,
                            format(float(values[name]), ".17g"),
                            (
                                "original_binary"
                                if name in binary_snapshot
                                else "continuous"
                            ),
                        )
                    )
    binary_names = tuple(sorted(binary_snapshot))
    return {
        "schema_id": SEED_SCHEMA_ID,
        "file_name": output_path.name,
        "file_sha256": _sha256(output_path),
        "variable_row_count": len(names),
        "variable_names_sha256": _name_list_sha256(names),
        "binary_variable_count": len(binary_names),
        "binary_names_sha256": _name_list_sha256(binary_names),
        "all_values_finite": True,
        "candidate_only": True,
        "formal_upper_bound_eligible": False,
    }


def read_seed_csv_gz(
    path: Path,
    *,
    expected_variable_names: tuple[str, ...] | None = None,
    expected_binary_names: tuple[str, ...] | None = None,
) -> tuple[dict[str, float], dict[str, int]]:
    """Read and strictly validate a deterministic D46 seed artifact."""

    values: dict[str, float] = {}
    binaries: dict[str, int] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != [
            "variable_name",
            "value",
            "variable_class",
        ]:
            raise ValueError("D46 seed header mismatch")
        previous: str | None = None
        for row in reader:
            name = row["variable_name"]
            if not name or name in values:
                raise ValueError("D46 seed has a missing or duplicate variable name")
            if previous is not None and name <= previous:
                raise ValueError("D46 seed rows are not strictly sorted")
            previous = name
            try:
                number = float(row["value"])
            except (TypeError, ValueError) as error:
                raise ValueError(f"D46 seed value is invalid: {name}") from error
            if not math.isfinite(number):
                raise ValueError(f"D46 seed value is not finite: {name}")
            variable_class = row["variable_class"]
            if variable_class not in {"original_binary", "continuous"}:
                raise ValueError(f"D46 seed class is invalid: {name}")
            values[name] = number
            if variable_class == "original_binary":
                rounded = int(round(number))
                if rounded not in (0, 1) or number != float(rounded):
                    raise ValueError(f"D46 seed binary is fractional: {name}")
                binaries[name] = rounded

    names = tuple(values)
    binary_names = tuple(binaries)
    if expected_variable_names is not None and names != tuple(
        sorted(expected_variable_names)
    ):
        raise ValueError("D46 seed variable names do not match the model")
    if expected_binary_names is not None and binary_names != tuple(
        sorted(expected_binary_names)
    ):
        raise ValueError("D46 seed binary names do not match the locked inventory")
    return values, binaries


def convert_d41_bess_guide_to_seed(
    model: object,
    inventory: BinaryInventory,
    guide_path: Path,
) -> tuple[dict[str, float], dict[str, int]]:
    """Convert the one locked D41 BESS R1 guide into D46 legal seed values."""

    if _sha256(guide_path) != D41_BESS_R1_GUIDE_SHA256:
        raise ValueError("D46 D41 BESS guide hash mismatch")
    values: dict[str, float] = {}
    with gzip.open(guide_path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != [
            "variable_name",
            "value",
            "variable_class",
        ]:
            raise ValueError("D46 D41 BESS guide header mismatch")
        previous: str | None = None
        for row in reader:
            name = row["variable_name"]
            if not name or name in values:
                raise ValueError("D46 D41 guide has a duplicate variable name")
            if previous is not None and name <= previous:
                raise ValueError("D46 D41 guide rows are not strictly sorted")
            previous = name
            if row["variable_class"] not in {
                "topology_binary",
                "operational_binary",
                "continuous",
            }:
                raise ValueError(f"D46 D41 guide class is invalid: {name}")
            try:
                number = float(row["value"])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"D46 D41 guide value is invalid: {name}"
                ) from error
            if not math.isfinite(number):
                raise ValueError(f"D46 D41 guide value is not finite: {name}")
            values[name] = number

    variables = _variable_map(model)
    if tuple(values) != tuple(sorted(variables)):
        raise ValueError("D46 D41 guide variable names do not match the model")
    for name, number in values.items():
        variables[name].set_value(number, skip_validation=True)
    binary_seed = derive_binary_seed(model, inventory)
    values.update({name: float(value) for name, value in binary_seed.items()})
    return values, binary_seed


def apply_complete_seed(
    model: object,
    inventory: BinaryInventory,
    values: Mapping[str, float],
    binary_snapshot: Mapping[str, int],
) -> dict[str, Any]:
    """Apply a complete finite MIP start and reject any identity mismatch."""

    variables = _variable_map(model)
    expected_names = set(variables)
    supplied_names = set(values)
    missing = sorted(expected_names - supplied_names)
    extra = sorted(supplied_names - expected_names)
    if missing or extra:
        raise ValueError(
            "D46 seed variables do not match the rebuilt model: "
            f"missing={missing[:3]}, extra={extra[:3]}"
        )
    expected_binary = set(inventory.all_names)
    if set(binary_snapshot) != expected_binary:
        raise ValueError("D46 seed binary names do not match the locked inventory")
    for name in sorted(values):
        raw = values[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"D46 seed value is not numeric: {name}")
        number = float(raw)
        if not math.isfinite(number):
            raise ValueError(f"D46 seed value is not finite: {name}")
        variables[name].set_value(number, skip_validation=True)
    for name in inventory.all_names:
        raw = binary_snapshot[name]
        if raw not in (0, 1) or float(values[name]) != float(raw):
            raise ValueError(f"D46 seed binary is invalid: {name}")
    return {
        "variable_count": len(variables),
        "binary_variable_count": len(inventory.all_names),
        "variable_names_sha256": _name_list_sha256(tuple(sorted(variables))),
        "binary_names_sha256": _name_list_sha256(inventory.all_names),
        "all_values_finite": True,
        "passed": True,
    }


def capture_first_incumbent(
    model: object,
    *,
    time_limit_seconds: float,
    threads: int = FORMAL_THREADS,
    stop_on_explicit_seed_rejection: bool = False,
) -> dict[str, Any]:
    """Warm-start HiGHS, copy its first complete MIP solution, and interrupt."""

    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0.0:
        raise ValueError("D46 candidate time limit must be finite and positive")
    import highspy

    solver = create_highs_solver(
        threads=threads,
        random_seed=FORMAL_RANDOM_SEED,
        mip_rel_gap=0.0,
    )
    solver.options["time_limit"] = time_limit_seconds
    solver.options["primal_feasibility_tolerance"] = (
        SOLVER_FEASIBILITY_TOLERANCE
    )
    solver.options["dual_feasibility_tolerance"] = (
        SOLVER_FEASIBILITY_TOLERANCE
    )
    solver.options["mip_feasibility_tolerance"] = (
        SOLVER_FEASIBILITY_TOLERANCE
    )
    solver.config.warmstart = True
    solver.set_instance(model)

    captured: dict[str, Any] = {}
    seed_diagnostic = {
        "user_solution_lp_attempt_seen": False,
        "explicit_infeasibility_seen": False,
    }

    def _callback(event: object) -> None:
        if captured:
            return
        raw = tuple(float(item) for item in event.data_out.mip_solution)
        primal_bound = float(event.data_out.mip_primal_bound)
        if len(raw) != len(solver._pyomo_var_to_solver_var_map):
            return
        if not all(math.isfinite(item) for item in raw):
            return
        captured["column_values"] = raw
        captured["reported_primal_bound"] = (
            primal_bound if math.isfinite(primal_bound) else None
        )
        event.interrupt()

    def _logging_callback(event: object) -> None:
        message = str(event.message)
        if (
            "user-supplied values of discrete variables" in message
            or "Assessing feasibility of MIP" in message
        ):
            seed_diagnostic["user_solution_lp_attempt_seen"] = True
        if seed_diagnostic["user_solution_lp_attempt_seen"] and (
            "Problem status detected on presolve: Infeasible" in message
            or "Model status        : Infeasible" in message
        ):
            seed_diagnostic["explicit_infeasibility_seen"] = True
            if stop_on_explicit_seed_rejection and not captured:
                event.interrupt()

    def _interrupt_callback(event: object) -> None:
        if (
            stop_on_explicit_seed_rejection
            and seed_diagnostic["explicit_infeasibility_seen"]
            and not captured
        ):
            event.interrupt()

    solver._solver_model.cbMipSolution.subscribe(_callback)
    solver._solver_model.cbLogging.subscribe(_logging_callback)
    solver._solver_model.cbMipInterrupt.subscribe(_interrupt_callback)
    started = perf_counter()
    highspy.Highs.resetGlobalScheduler(True)
    try:
        results = solver.solve(
            model,
            tee=True,
            load_solutions=False,
            warmstart=True,
        )
    finally:
        highspy.Highs.resetGlobalScheduler(True)
    runtime = perf_counter() - started
    if not captured:
        return {
            "status": (
                "seed_explicitly_rejected"
                if seed_diagnostic["explicit_infeasibility_seen"]
                else "no_candidate_incumbent"
            ),
            "incumbent_captured": False,
            "seed_explicitly_rejected": seed_diagnostic[
                "explicit_infeasibility_seen"
            ],
            "seed_diagnostic": seed_diagnostic,
            "runtime_seconds": runtime,
            "termination_condition": str(
                results.solver.termination_condition
            ).lower(),
        }

    index_to_variable = {
        column: solver._vars[variable_id][0]
        for variable_id, column in solver._pyomo_var_to_solver_var_map.items()
    }
    if set(index_to_variable) != set(range(len(captured["column_values"]))):
        raise ValueError("D46 HiGHS/Pyomo column map is incomplete")
    values: dict[str, float] = {}
    for column, number in enumerate(captured["column_values"]):
        variable = index_to_variable[column]
        variable.set_value(number, skip_validation=True)
        values[variable.name] = number
    return {
        "status": "candidate_incumbent_captured",
        "incumbent_captured": True,
        "seed_explicitly_rejected": False,
        "seed_diagnostic": seed_diagnostic,
        "runtime_seconds": runtime,
        "termination_condition": str(
            results.solver.termination_condition
        ).lower(),
        "reported_primal_bound_cny": captured["reported_primal_bound"],
        "variable_values": {name: values[name] for name in sorted(values)},
        "variable_count": len(values),
        "variable_names_sha256": _name_list_sha256(tuple(sorted(values))),
    }


def solve_continuous_guide(
    model: object,
    inventory: BinaryInventory,
    *,
    seed_output_path: Path,
    time_limit_seconds: float = GUIDE_SOFT_TIME_LIMIT_SECONDS,
    threads: int = FORMAL_THREADS,
) -> dict[str, Any]:
    """Solve an already-relaxed R0 model and persist a candidate-only seed."""

    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0.0:
        raise ValueError("D46 guide time limit must be finite and positive")
    import highspy

    solver = create_highs_solver(
        threads=threads,
        random_seed=FORMAL_RANDOM_SEED,
        mip_rel_gap=0.0,
    )
    solver.options["time_limit"] = time_limit_seconds
    solver.options["primal_feasibility_tolerance"] = (
        SOLVER_FEASIBILITY_TOLERANCE
    )
    solver.options["dual_feasibility_tolerance"] = (
        SOLVER_FEASIBILITY_TOLERANCE
    )
    started = perf_counter()
    highspy.Highs.resetGlobalScheduler(True)
    try:
        results = solver.solve(model, tee=True, load_solutions=False)
        try:
            solver.load_vars()
            solution_loaded = True
        except Exception:  # noqa: BLE001 - canonical no-guide path
            solution_loaded = False
    finally:
        highspy.Highs.resetGlobalScheduler(True)
    runtime = perf_counter() - started
    termination = str(results.solver.termination_condition).lower()
    if not solution_loaded:
        return {
            "status": "no_continuous_guide",
            "solution_loaded": False,
            "termination_condition": termination,
            "runtime_seconds": runtime,
            "formal_upper_bound_eligible": False,
        }

    primal = _solver_primal_audit(solver)
    feasibility = _bound_and_constraint_audit(model)
    service = _service_audit(model)
    guide_eligible = all(
        (primal["passed"], feasibility["passed"], service["passed"])
    )
    seed = None
    if guide_eligible:
        values, binaries = derive_complete_seed(model, inventory)
        seed = write_seed_csv_gz(seed_output_path, values, binaries)
    return {
        "status": (
            "continuous_guide_recovered"
            if guide_eligible
            else "no_continuous_guide"
        ),
        "solution_loaded": solution_loaded,
        "termination_condition": termination,
        "runtime_seconds": runtime,
        "solver_primal_audit": primal,
        "independent_feasibility_audit": feasibility,
        "service_audit": service,
        "seed_artifact": seed,
        "r0_objective_is_upper_bound": False,
        "formal_upper_bound_eligible": False,
    }


def build_candidate_from_seed(
    model: object,
    inventory: BinaryInventory,
    *,
    seed_path: Path,
    candidate_output_path: Path,
    time_limit_seconds: float = CANDIDATE_SOFT_TIME_LIMIT_SECONDS,
    threads: int = FORMAL_THREADS,
    stop_on_explicit_seed_rejection: bool = False,
) -> dict[str, Any]:
    """Submit one complete start and archive only the first complete incumbent."""

    variable_names = tuple(sorted(_variable_map(model)))
    values, binary_seed = read_seed_csv_gz(
        seed_path,
        expected_variable_names=variable_names,
        expected_binary_names=inventory.all_names,
    )
    seed_audit = apply_complete_seed(
        model,
        inventory,
        values,
        binary_seed,
    )
    callback = capture_first_incumbent(
        model,
        time_limit_seconds=time_limit_seconds,
        threads=threads,
        stop_on_explicit_seed_rejection=stop_on_explicit_seed_rejection,
    )
    if callback["incumbent_captured"] is not True:
        return {
            **callback,
            "status": callback["status"],
            "seed_application_audit": seed_audit,
            "candidate_artifact": None,
            "formal_upper_bound_eligible": False,
        }

    incumbent_values = callback.pop("variable_values")
    snapshot = extract_binary_snapshot(model, inventory, tolerance=1e-7)
    artifact = write_seed_csv_gz(
        candidate_output_path,
        incumbent_values,
        snapshot,
    )
    feasibility = _bound_and_constraint_audit(model)
    return {
        **callback,
        "status": "candidate_incumbent_captured",
        "seed_application_audit": seed_audit,
        "binary_snapshot_variable_count": len(snapshot),
        "binary_snapshot_names_sha256": _name_list_sha256(
            tuple(sorted(snapshot))
        ),
        "candidate_artifact": artifact,
        "candidate_independent_feasibility_audit": feasibility,
        "candidate_requires_fixed_binary_repair": True,
        "formal_upper_bound_eligible": False,
    }


def _bound_and_constraint_audit(model: object) -> dict[str, Any]:
    from pyomo.environ import Constraint, Var, value

    variable_count = 0
    nonfinite_variable_count = 0
    max_bound_violation = 0.0
    worst_variable: str | None = None
    for variable in model.component_data_objects(
        Var, active=True, descend_into=True
    ):
        variable_count += 1
        raw = value(variable, exception=False)
        if raw is None or not math.isfinite(float(raw)):
            nonfinite_variable_count += 1
            continue
        number = float(raw)
        violation = 0.0
        if variable.lb is not None:
            violation = max(violation, float(variable.lb) - number)
        if variable.ub is not None:
            violation = max(violation, number - float(variable.ub))
        if violation > max_bound_violation:
            max_bound_violation = violation
            worst_variable = variable.name

    constraint_count = 0
    nonfinite_constraint_count = 0
    max_constraint_violation = 0.0
    worst_constraint: str | None = None
    for constraint in model.component_data_objects(
        Constraint, active=True, descend_into=True
    ):
        constraint_count += 1
        try:
            body = float(value(constraint.body))
            lower = (
                None
                if constraint.lower is None
                else float(value(constraint.lower))
            )
            upper = (
                None
                if constraint.upper is None
                else float(value(constraint.upper))
            )
        except (TypeError, ValueError):
            nonfinite_constraint_count += 1
            continue
        if not all(
            math.isfinite(item)
            for item in (body, lower, upper)
            if item is not None
        ):
            nonfinite_constraint_count += 1
            continue
        violation = 0.0
        if lower is not None:
            violation = max(violation, lower - body)
        if upper is not None:
            violation = max(violation, body - upper)
        if violation > max_constraint_violation:
            max_constraint_violation = violation
            worst_constraint = constraint.name

    passed = all(
        (
            nonfinite_variable_count == 0,
            nonfinite_constraint_count == 0,
            max_bound_violation <= INDEPENDENT_ABSOLUTE_TOLERANCE,
            max_constraint_violation <= INDEPENDENT_ABSOLUTE_TOLERANCE,
        )
    )
    return {
        "evaluated_variable_count": variable_count,
        "nonfinite_variable_count": nonfinite_variable_count,
        "max_variable_bound_violation": max_bound_violation,
        "worst_variable": worst_variable,
        "evaluated_constraint_count": constraint_count,
        "nonfinite_constraint_count": nonfinite_constraint_count,
        "max_constraint_violation": max_constraint_violation,
        "worst_constraint": worst_constraint,
        "absolute_tolerance": INDEPENDENT_ABSOLUTE_TOLERANCE,
        "passed": passed,
    }


def _constraint_group_audits(
    model: object,
    architecture: Architecture,
) -> dict[str, Any]:
    from pyomo.environ import Constraint, value

    groups = {
        "pcc_and_heat_balances": (
            "planning_pcc_balance",
            "planning_heat_allocation",
            "planning_heat_balance",
        ),
        "chp_transition_and_ramp": (
            ".commitment_transition",
            ".ramp_up",
            ".ramp_down",
        ),
        "storage_cycles": (
            "bess.cyclic_energy",
            "tes.cyclic_ht",
            "tes.cyclic_mt",
            "tes.cyclic_lt",
        ),
        "storage_mutual_exclusion": (
            "bess.charge_mode_limit",
            "bess.discharge_mode_limit",
            "tes.ht_receiving_limit",
            "tes.ht_sending_limit",
            "tes.mt_direct_charge_limit",
            "tes.mt_heat_discharge_limit",
        ),
        "capacity_linkage_and_duration": (
            "capacity_limit",
            "uses_common_pcs",
            "requires_installation",
            "minimum_duration",
            "maximum_duration",
            "minimum_power_duration",
            "maximum_power_duration",
            "minimum_heat_duration",
            "maximum_heat_duration",
            "service_mass_limit",
            "service_charge_reachability",
            "service_discharge_reachability",
        ),
        "bess_throughput": ("planning_bess_ac_throughput_limit",),
    }
    constraints = tuple(
        model.component_data_objects(
            Constraint,
            active=True,
            descend_into=True,
        )
    )
    result: dict[str, Any] = {}
    includes_bess = architecture in (Architecture.BESS, Architecture.HYBRID)
    for group_name, tokens in groups.items():
        selected = tuple(
            constraint
            for constraint in constraints
            if any(token in constraint.name for token in tokens)
        )
        required = group_name != "bess_throughput" or includes_bess
        nonfinite = 0
        worst = 0.0
        worst_name: str | None = None
        for constraint in selected:
            try:
                body = float(value(constraint.body))
                lower = (
                    None
                    if constraint.lower is None
                    else float(value(constraint.lower))
                )
                upper = (
                    None
                    if constraint.upper is None
                    else float(value(constraint.upper))
                )
            except (TypeError, ValueError):
                nonfinite += 1
                continue
            if not all(
                math.isfinite(item)
                for item in (body, lower, upper)
                if item is not None
            ):
                nonfinite += 1
                continue
            violation = 0.0
            if lower is not None:
                violation = max(violation, lower - body)
            if upper is not None:
                violation = max(violation, body - upper)
            if violation > worst:
                worst = violation
                worst_name = constraint.name
        passed = (
            (not required or len(selected) > 0)
            and nonfinite == 0
            and worst <= INDEPENDENT_ABSOLUTE_TOLERANCE
        )
        result[group_name] = {
            "required": required,
            "evaluated_constraint_count": len(selected),
            "nonfinite_constraint_count": nonfinite,
            "max_absolute_violation": worst,
            "worst_constraint": worst_name,
            "tolerance": INDEPENDENT_ABSOLUTE_TOLERANCE,
            "passed": passed,
        }
    return {
        "groups": result,
        "passed": all(item["passed"] for item in result.values()),
    }


def _fixed_binary_audit(
    model: object,
    inventory: BinaryInventory,
) -> dict[str, Any]:
    variables = _variable_map(model)
    invalid: list[str] = []
    unfixed: list[str] = []
    for name in inventory.all_names:
        variable = variables[name]
        if not variable.fixed:
            unfixed.append(name)
        raw = _finite_value(variable, name)
        if raw not in (0.0, 1.0):
            invalid.append(name)
    return {
        "binary_variable_count": len(inventory.all_names),
        "binary_names_sha256": _name_list_sha256(inventory.all_names),
        "unfixed_binary_count": len(unfixed),
        "unfixed_binary_names_sha256": _name_list_sha256(tuple(unfixed)),
        "invalid_binary_count": len(invalid),
        "invalid_binary_names_sha256": _name_list_sha256(tuple(invalid)),
        "passed": not unfixed and not invalid,
    }


def _capacity_policy_audit(
    model: object,
    architecture: Architecture,
    *,
    repair: str,
) -> dict[str, Any]:
    if repair not in {"A", "B"}:
        raise ValueError("D46 capacity audit repair must be A or B")
    capacities = _continuous_capacity_variables(model, architecture)
    values = {
        name: _finite_value(variable, name)
        for name, variable in sorted(capacities.items())
    }
    expected: dict[str, float] = {}
    if architecture in (Architecture.BESS, Architecture.HYBRID):
        expected.update(
            {
                model.bess.energy_capacity_mwh.name: BESS_ENERGY_ANCHOR_MWH,
                model.bess.charge_power_capacity_mw.name: BESS_POWER_ANCHOR_MW,
                model.bess.discharge_power_capacity_mw.name: (
                    BESS_POWER_ANCHOR_MW
                ),
                model.bess.pcs_power_capacity_mw.name: BESS_POWER_ANCHOR_MW,
            }
        )
    if architecture in (Architecture.TES, Architecture.HYBRID):
        for field in (
            "ht_tank_capacity_t",
            "mt_tank_capacity_t",
            "lt_tank_capacity_t",
        ):
            expected[getattr(model.tes, field).name] = TES_TANK_ANCHOR_T
        for field in (
            "electric_charge_input_capacity_mw",
            "steam_to_ht_input_capacity_mw",
            "steam_to_mt_input_capacity_mw",
            "electric_output_capacity_mw",
            "heat_output_capacity_mw",
        ):
            expected[getattr(model.tes, field).name] = TES_PORT_ANCHOR_MW
    anchors_match = all(
        math.isclose(values[name], anchor, rel_tol=0.0, abs_tol=1e-9)
        for name, anchor in expected.items()
    )
    fixed_names = tuple(
        sorted(name for name, variable in capacities.items() if variable.fixed)
    )
    continuous_policy_passed = (
        anchors_match and len(fixed_names) == len(capacities)
        if repair == "A"
        else len(fixed_names) == 0
    )
    additional: dict[str, float] = {}
    if architecture in (Architecture.TES, Architecture.HYBRID):
        for field in (
            "salt_mass_t",
            "ht_service_salt_mass_t",
            "mt_service_salt_mass_t",
        ):
            variable = getattr(model.tes, field)
            additional[variable.name] = _finite_value(variable, variable.name)
    bess_installation_policy_passed = True
    bess_installation_value: float | None = None
    if architecture in (Architecture.BESS, Architecture.HYBRID):
        bess_installation_value = _finite_value(
            model.bess.installed,
            model.bess.installed.name,
        )
        bess_installation_policy_passed = (
            model.bess.installed.fixed and bess_installation_value == 1.0
        )
    return {
        "repair": repair,
        "continuous_capacity_values": values,
        "additional_tes_mass_values": additional,
        "anchor_values": {name: expected[name] for name in sorted(expected)},
        "anchors_match": anchors_match,
        "fixed_continuous_capacity_count": len(fixed_names),
        "fixed_continuous_capacity_names_sha256": _name_list_sha256(
            fixed_names
        ),
        "repair_a_requires_fixed_anchors": repair == "A",
        "repair_b_requires_released_continuous_capacities": repair == "B",
        "bess_installation_value": bess_installation_value,
        "bess_installation_fixed_at_anchor": bess_installation_policy_passed,
        "passed": (
            continuous_policy_passed and bess_installation_policy_passed
        ),
    }


def _service_audit(model: object) -> dict[str, Any]:
    annual_export = _finite_value(
        model.annual_pcc_export_mwh, "annual PCC export"
    )
    annual_curtailment = _finite_value(
        model.annual_curtailment_mwh, "annual curtailment"
    )
    export_residual_mwh = annual_export - PCC_EXPORT_TARGET_MWH
    export_residual_mw = export_residual_mwh / FULL_YEAR_HOURS
    curtailment_violation = max(
        0.0, annual_curtailment - EPSILON_CURTAILMENT_CEILING_MWH
    )
    passed = all(
        (
            abs(export_residual_mw) <= SERVICE_EXPORT_TOLERANCE_MW,
            curtailment_violation <= SERVICE_CURTAILMENT_TOLERANCE_MWH,
        )
    )
    return {
        "annual_pcc_export_mwh": annual_export,
        "pcc_export_target_mwh": PCC_EXPORT_TARGET_MWH,
        "pcc_export_residual_mwh": export_residual_mwh,
        "pcc_export_average_power_residual_mw": export_residual_mw,
        "pcc_export_tolerance_mw": SERVICE_EXPORT_TOLERANCE_MW,
        "annual_curtailment_mwh": annual_curtailment,
        "curtailment_ceiling_mwh": EPSILON_CURTAILMENT_CEILING_MWH,
        "curtailment_ceiling_violation_mwh": curtailment_violation,
        "curtailment_tolerance_mwh": SERVICE_CURTAILMENT_TOLERANCE_MWH,
        "passed": passed,
    }


def _objective_audit(model: object) -> dict[str, Any]:
    total = _finite_value(model.planning_total_cost_cny, "total cost")
    components = {
        "annual_operating_cost_cny": _finite_value(
            model.annual_operating_cost_cny, "annual operating cost"
        ),
        "annual_storage_capacity_cost_cny": _finite_value(
            model.planning_storage_capacity_cost_cny,
            "annual storage capacity cost",
        ),
        "annual_bess_cycle_cost_cny": _finite_value(
            model.planning_bess_cycle_cost_cny, "annual BESS cycle cost"
        ),
        "annual_bess_variable_om_cost_cny": _finite_value(
            model.planning_bess_variable_om_cost_cny,
            "annual BESS variable O&M cost",
        ),
    }
    recomposed = sum(components.values())
    difference = total - recomposed
    tolerance = max(
        OBJECTIVE_ABSOLUTE_TOLERANCE_CNY,
        OBJECTIVE_RELATIVE_TOLERANCE * abs(total),
    )
    return {
        "model_objective_cny": total,
        "components": components,
        "recomposed_objective_cny": recomposed,
        "recomposition_difference_cny": difference,
        "tolerance_cny": tolerance,
        "passed": abs(difference) <= tolerance,
    }


def _solver_primal_audit(solver: object) -> dict[str, Any]:
    info = solver._solver_model.getInfo()
    count = int(info.num_primal_infeasibilities)
    maximum = float(info.max_primal_infeasibility)
    objective = float(solver._solver_model.getObjectiveValue())
    passed = (
        count == 0
        and math.isfinite(maximum)
        and maximum <= SOLVER_FEASIBILITY_TOLERANCE
        and math.isfinite(objective)
    )
    return {
        "num_primal_infeasibilities": count,
        "max_primal_infeasibility": maximum,
        "highs_objective_value_cny": objective,
        "tolerance": SOLVER_FEASIBILITY_TOLERANCE,
        "passed": passed,
    }


def _ceil_upper_bound(objective: float) -> str:
    with localcontext() as context:
        context.prec = 50
        quantum = Decimal(1).scaleb(-UPPER_BOUND_DECIMAL_PLACES)
        return format(
            Decimal.from_float(objective).quantize(
                quantum,
                rounding=ROUND_CEILING,
            ),
            "f",
        )


def audit_repaired_solution(
    model: object,
    inventory: BinaryInventory,
    *,
    solver_primal_audit: Mapping[str, Any],
    architecture: Architecture,
    repair: str,
    require_named_constraint_groups: bool = False,
) -> dict[str, Any]:
    """Independently audit one fixed-binary LP before granting an upper bound."""

    bounds_constraints = _bound_and_constraint_audit(model)
    binary = _fixed_binary_audit(model, inventory)
    capacity = _capacity_policy_audit(
        model,
        architecture,
        repair=repair,
    )
    named_groups = _constraint_group_audits(model, architecture)
    service = _service_audit(model)
    objective = _objective_audit(model)
    highs_objective = solver_primal_audit.get("highs_objective_value_cny")
    objective_tolerance = float(objective["tolerance_cny"])
    objective_difference = (
        None
        if not isinstance(highs_objective, (int, float))
        or not math.isfinite(float(highs_objective))
        else objective["model_objective_cny"] - float(highs_objective)
    )
    objective["highs_objective_value_cny"] = highs_objective
    objective["model_minus_highs_objective_cny"] = objective_difference
    objective["solver_objective_match"] = (
        objective_difference is not None
        and abs(objective_difference) <= objective_tolerance
    )
    objective["passed"] = (
        objective["passed"] and objective["solver_objective_match"]
    )
    solver_passed = solver_primal_audit.get("passed") is True
    passed = all(
        (
            solver_passed,
            bounds_constraints["passed"],
            binary["passed"],
            capacity["passed"],
            (
                named_groups["passed"]
                if require_named_constraint_groups
                else True
            ),
            service["passed"],
            objective["passed"],
        )
    )
    return {
        "solver_primal": dict(solver_primal_audit),
        "bounds_and_constraints": bounds_constraints,
        "fixed_binaries": binary,
        "capacity_policy": capacity,
        "named_constraint_groups": named_groups,
        "named_constraint_groups_required": require_named_constraint_groups,
        "service": service,
        "objective": objective,
        "engineering_numerical_feasibility_only": True,
        "rational_exact_feasibility_certificate": False,
        "audited_feasible_upper_bound_cny": (
            _ceil_upper_bound(objective["model_objective_cny"])
            if passed
            else None
        ),
        "passed": passed,
    }


def solve_fixed_binary_repair(
    model: object,
    inventory: BinaryInventory,
    snapshot: Mapping[str, int | float],
    *,
    time_limit_seconds: float,
    release_capacities: bool = False,
    architecture: Architecture,
    threads: int = FORMAL_THREADS,
    require_named_constraint_groups: bool = False,
) -> dict[str, Any]:
    """Solve and audit Repair A or B on a rebuilt original MILP."""

    fixing = fix_binary_snapshot(model, inventory, snapshot, tolerance=0.0)
    release = None
    if release_capacities:
        release = release_continuous_capacity_variables(model, architecture)
    solver = create_highs_solver(
        threads=threads,
        random_seed=FORMAL_RANDOM_SEED,
        mip_rel_gap=0.0,
    )
    solver.options["time_limit"] = time_limit_seconds
    solver.options["primal_feasibility_tolerance"] = (
        SOLVER_FEASIBILITY_TOLERANCE
    )
    solver.options["dual_feasibility_tolerance"] = (
        SOLVER_FEASIBILITY_TOLERANCE
    )
    solver.options["mip_feasibility_tolerance"] = (
        SOLVER_FEASIBILITY_TOLERANCE
    )
    started = perf_counter()
    results = solver.solve(model, tee=True, load_solutions=False)
    runtime = perf_counter() - started
    termination = str(results.solver.termination_condition).lower()
    try:
        solver.load_vars()
        solution_loaded = True
    except Exception:  # noqa: BLE001 - preserve a failed repair as evidence
        solution_loaded = False
    audit = None
    if solution_loaded:
        audit = audit_repaired_solution(
            model,
            inventory,
            solver_primal_audit=_solver_primal_audit(solver),
            architecture=architecture,
            repair="B" if release_capacities else "A",
            require_named_constraint_groups=require_named_constraint_groups,
        )
    success = bool(audit is not None and audit["passed"] is True)
    return {
        "schema_id": REPAIR_SCHEMA_ID,
        "status": (
            "audited_feasible_upper_bound_recovered"
            if success
            else "fixed_binary_repair_failed"
        ),
        "repair": "B" if release_capacities else "A",
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "termination_condition": termination,
        "runtime_seconds": runtime,
        "solution_loaded": solution_loaded,
        "binary_fixing_audit": fixing,
        "capacity_release_audit": release,
        "solution_audit": audit,
    }


def select_preferred_repair(
    repair_a: Mapping[str, Any],
    repair_b: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Keep Repair A unless a fully audited Repair B is no more expensive."""

    audit_a = repair_a.get("solution_audit")
    if not isinstance(audit_a, Mapping) or audit_a.get("passed") is not True:
        raise ValueError("D46 cannot select without a successful Repair A")
    selected = repair_a
    reason = "repair_a_is_the_required_success_path"
    if repair_b is not None:
        audit_b = repair_b.get("solution_audit")
        if isinstance(audit_b, Mapping) and audit_b.get("passed") is True:
            objective_a = float(audit_a["objective"]["model_objective_cny"])
            objective_b = float(audit_b["objective"]["model_objective_cny"])
            tolerance = max(
                OBJECTIVE_ABSOLUTE_TOLERANCE_CNY,
                OBJECTIVE_RELATIVE_TOLERANCE * abs(objective_a),
            )
            if objective_b <= objective_a + tolerance:
                selected = repair_b
                reason = "repair_b_audited_and_not_more_expensive"
            else:
                reason = "repair_b_is_more_expensive_than_repair_a"
        else:
            reason = "repair_b_failed_without_revoking_repair_a"
    return {
        "selected_repair": selected.get("repair"),
        "selection_reason": reason,
        "selected_audited_feasible_upper_bound_cny": selected[
            "solution_audit"
        ]["audited_feasible_upper_bound_cny"],
        "selected_result": dict(selected),
        "repair_a_preserved_on_repair_b_failure": True,
        "passed": True,
    }


def build_formal_stage_model(
    *,
    architecture: Architecture,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    relaxation: RelaxationMode | None = None,
) -> tuple[object, object, BinaryInventory, dict[str, Any]]:
    """Rebuild one locked formal model and apply only preregistered changes."""

    d41_gate_a = _load_locked_d41_gate_a(d41_gate_a_manifest_path)
    case, model, model_size = _build_gate_b_model(
        architecture,
        service_path,
        d40_gate_a_manifest_path,
        heat_path,
        vre_path,
        price_basis_path,
    )
    if model_size != EXPECTED_MODEL_SIZE[architecture]:
        raise ValueError("D46 formal model size does not match the frozen contract")
    inventory = collect_binary_inventory(model)
    inventory_audit = _inventory_lock_audit(
        inventory,
        architecture,
        d41_gate_a,
    )
    if inventory_audit["passed"] is not True:
        raise ValueError("D46 binary inventory differs from locked D41 Gate A")
    capacity_audit = fix_engineering_capacity_anchor(model, architecture)
    relaxation_audit = None
    if relaxation is not None:
        relaxation_audit = apply_relaxation(model, inventory, relaxation)
    post_size = _linearity_audit(model)
    return case, model, inventory, {
        "model_size": model_size,
        "post_change_model_size": post_size,
        "binary_inventory_audit": inventory_audit,
        "capacity_anchor_audit": capacity_audit,
        "relaxation_audit": relaxation_audit,
    }


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json_bytes(payload))


def _code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    names = (
        "e0d46_full_year_feasible_upper_bound_repair.py",
        "e0d46_monitored_executor.py",
        "e0d41_strict_full_year_decomposition.py",
        "e0d40_gate_b_solver.py",
        "e0d40_full_year_compute_gate.py",
        "planning_model.py",
    )
    return {name: _sha256(package / name) for name in names}


def _formal_base_payload(
    *,
    architecture: Architecture,
    stage: str,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    return {
        "schema_id": RESULT_SCHEMA_ID,
        "architecture": architecture.value,
        "stage": stage,
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "representative_period_input_used": False,
        "service_contract_sha256": _sha256(service_path),
        "d40_gate_a_manifest_sha256": _sha256(d40_gate_a_manifest_path),
        "d41_gate_a_manifest_sha256": _sha256(d41_gate_a_manifest_path),
        "input_sha256": {
            "heat": _sha256(heat_path),
            "vre": _sha256(vre_path),
            "price_basis_tree": _tree_sha256(price_basis_path),
        },
        "provenance": {"code_sha256": _code_hashes()},
    }


def solve_guide_child(
    *,
    architecture: Architecture,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    seed_output_path: Path,
    result_output_path: Path,
    threads: int = FORMAL_THREADS,
    time_limit_seconds: float = GUIDE_SOFT_TIME_LIMIT_SECONDS,
) -> dict[str, Any]:
    """Build and solve one formal R0 guide in an isolated child process."""

    base = _formal_base_payload(
        architecture=architecture,
        stage="guide",
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    try:
        _, model, inventory, build_audit = build_formal_stage_model(
            architecture=architecture,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
            relaxation=RelaxationMode.R0,
        )
        guide = solve_continuous_guide(
            model,
            inventory,
            seed_output_path=seed_output_path,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
        )
        payload = {
            **base,
            "solver_invoked": True,
            "build_audit": build_audit,
            **guide,
        }
    except Exception as error:  # noqa: BLE001 - canonical formal evidence
        payload = {
            **base,
            "status": "no_continuous_guide",
            "solver_invoked": False,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "formal_upper_bound_eligible": False,
        }
    _write_json(result_output_path, payload)
    return payload


def solve_candidate_child(
    *,
    architecture: Architecture,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    seed_path: Path,
    d41_bess_guide_path: Path | None,
    fallback_seed_output_path: Path | None,
    candidate_output_path: Path,
    result_output_path: Path,
    threads: int = FORMAL_THREADS,
    time_limit_seconds: float = CANDIDATE_SOFT_TIME_LIMIT_SECONDS,
) -> dict[str, Any]:
    """Rebuild the original MILP and capture its first complete incumbent."""

    base = _formal_base_payload(
        architecture=architecture,
        stage="candidate",
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    candidate_started = perf_counter()
    try:
        _, model, inventory, build_audit = build_formal_stage_model(
            architecture=architecture,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        )
        candidate = build_candidate_from_seed(
            model,
            inventory,
            seed_path=seed_path,
            candidate_output_path=candidate_output_path,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
            stop_on_explicit_seed_rejection=(
                architecture is Architecture.BESS
                and d41_bess_guide_path is not None
            ),
        )
        fallback_used = False
        primary_candidate = candidate
        fallback_seed = None
        if candidate["status"] == "seed_explicitly_rejected":
            if architecture is not Architecture.BESS:
                raise ValueError("D46 fallback seed is forbidden outside BESS")
            if d41_bess_guide_path is None or fallback_seed_output_path is None:
                raise ValueError("D46 explicit BESS rejection requires locked fallback")
            elapsed = perf_counter() - candidate_started
            remaining = time_limit_seconds - elapsed
            if remaining <= 0.0:
                raise TimeoutError("D46 candidate budget exhausted before fallback")
            _, fallback_model, fallback_inventory, fallback_build_audit = (
                build_formal_stage_model(
                    architecture=architecture,
                    service_path=service_path,
                    d40_gate_a_manifest_path=d40_gate_a_manifest_path,
                    d41_gate_a_manifest_path=d41_gate_a_manifest_path,
                    heat_path=heat_path,
                    vre_path=vre_path,
                    price_basis_path=price_basis_path,
                )
            )
            fallback_values, fallback_binaries = convert_d41_bess_guide_to_seed(
                fallback_model,
                fallback_inventory,
                d41_bess_guide_path,
            )
            fallback_seed = write_seed_csv_gz(
                fallback_seed_output_path,
                fallback_values,
                fallback_binaries,
            )
            candidate = build_candidate_from_seed(
                fallback_model,
                fallback_inventory,
                seed_path=fallback_seed_output_path,
                candidate_output_path=candidate_output_path,
                time_limit_seconds=remaining,
                threads=threads,
                stop_on_explicit_seed_rejection=False,
            )
            build_audit = {
                "primary": build_audit,
                "fallback": fallback_build_audit,
            }
            fallback_used = True
        payload = {
            **base,
            "solver_invoked": True,
            "build_audit": build_audit,
            "primary_candidate_attempt": (
                primary_candidate if fallback_used else None
            ),
            "d41_bess_fallback_seed": fallback_seed,
            "fallback_seed_used": fallback_used,
            **candidate,
        }
    except Exception as error:  # noqa: BLE001 - canonical formal evidence
        payload = {
            **base,
            "status": "no_candidate_incumbent",
            "solver_invoked": False,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "formal_upper_bound_eligible": False,
        }
    _write_json(result_output_path, payload)
    return payload


def solve_repair_child(
    *,
    architecture: Architecture,
    repair: str,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    candidate_path: Path,
    solution_output_path: Path,
    result_output_path: Path,
    threads: int = FORMAL_THREADS,
    time_limit_seconds: float = REPAIR_A_HARD_WALL_SECONDS,
) -> dict[str, Any]:
    """Rebuild, fix the complete incumbent trajectory, and solve Repair A/B."""

    if repair not in {"A", "B"}:
        raise ValueError("D46 repair child requires A or B")
    base = _formal_base_payload(
        architecture=architecture,
        stage=f"repair_{repair.lower()}",
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    try:
        _, model, inventory, build_audit = build_formal_stage_model(
            architecture=architecture,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        )
        variable_names = tuple(sorted(_variable_map(model)))
        _, snapshot = read_seed_csv_gz(
            candidate_path,
            expected_variable_names=variable_names,
            expected_binary_names=inventory.all_names,
        )
        repaired = solve_fixed_binary_repair(
            model,
            inventory,
            snapshot,
            time_limit_seconds=time_limit_seconds,
            release_capacities=repair == "B",
            architecture=architecture,
            threads=threads,
            require_named_constraint_groups=True,
        )
        solution_artifact = None
        if repaired["solution_loaded"]:
            solution_values = {
                name: _finite_value(variable, name)
                for name, variable in sorted(_variable_map(model).items())
            }
            solution_artifact = write_seed_csv_gz(
                solution_output_path,
                solution_values,
                snapshot,
            )
        payload = {
            **base,
            "solver_invoked": True,
            "build_audit": build_audit,
            "candidate_artifact_sha256": _sha256(candidate_path),
            "solution_artifact": solution_artifact,
            **repaired,
        }
    except Exception as error:  # noqa: BLE001 - canonical formal evidence
        payload = {
            **base,
            "status": "fixed_binary_repair_failed",
            "repair": repair,
            "solver_invoked": False,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
    _write_json(result_output_path, payload)
    return payload


def write_gate_a_build_audit(
    *,
    architecture: Architecture,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    result_output_path: Path,
) -> dict[str, Any]:
    """Build the formal 8784 h identity and R0 domains without invoking HiGHS."""

    started = perf_counter()
    _, _, inventory, build_audit = build_formal_stage_model(
        architecture=architecture,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
        relaxation=RelaxationMode.R0,
    )
    passed = all(
        (
            build_audit["binary_inventory_audit"]["passed"],
            build_audit["capacity_anchor_audit"]["passed"],
            build_audit["relaxation_audit"]["passed"],
            build_audit["post_change_model_size"][
                "active_binary_variable_count"
            ]
            == 0,
        )
    )
    payload = {
        **_formal_base_payload(
            architecture=architecture,
            stage="gate_a_build_only",
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        ),
        "status": "gate_a_build_passed" if passed else "gate_a_build_failed",
        "solver_invoked": False,
        "formal_optimization_invoked": False,
        "runtime_seconds": perf_counter() - started,
        "binary_variable_count": len(inventory.all_names),
        "build_audit": build_audit,
        "audit": {"passed": passed},
    }
    _write_json(result_output_path, payload)
    if not passed:
        raise RuntimeError(f"D46 Gate A build audit failed for {architecture.value}")
    return payload


def _add_formal_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--architecture",
        choices=[item.value for item in FORMAL_ARCHITECTURES],
        required=True,
    )
    parser.add_argument("--service-file", type=Path, required=True)
    parser.add_argument("--d40-gate-a-manifest", type=Path, required=True)
    parser.add_argument("--d41-gate-a-manifest", type=Path, required=True)
    parser.add_argument("--heat-path", type=Path, required=True)
    parser.add_argument("--vre-path", type=Path, required=True)
    parser.add_argument("--price-basis-path", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    guide = commands.add_parser("_guide-child")
    _add_formal_inputs(guide)
    guide.add_argument("--seed-output", type=Path, required=True)
    guide.add_argument("--result-output", type=Path, required=True)
    guide.add_argument("--threads", type=int, default=FORMAL_THREADS)
    guide.add_argument(
        "--time-limit-seconds",
        type=float,
        default=GUIDE_SOFT_TIME_LIMIT_SECONDS,
    )

    candidate = commands.add_parser("_candidate-child")
    _add_formal_inputs(candidate)
    candidate.add_argument("--seed-path", type=Path, required=True)
    candidate.add_argument("--d41-bess-guide", type=Path)
    candidate.add_argument("--fallback-seed-output", type=Path)
    candidate.add_argument("--candidate-output", type=Path, required=True)
    candidate.add_argument("--result-output", type=Path, required=True)
    candidate.add_argument("--threads", type=int, default=FORMAL_THREADS)
    candidate.add_argument(
        "--time-limit-seconds",
        type=float,
        default=CANDIDATE_SOFT_TIME_LIMIT_SECONDS,
    )

    repair = commands.add_parser("_repair-child")
    _add_formal_inputs(repair)
    repair.add_argument("--repair", choices=("A", "B"), required=True)
    repair.add_argument("--candidate-path", type=Path, required=True)
    repair.add_argument("--solution-output", type=Path, required=True)
    repair.add_argument("--result-output", type=Path, required=True)
    repair.add_argument("--threads", type=int, default=FORMAL_THREADS)
    repair.add_argument(
        "--time-limit-seconds",
        type=float,
        default=REPAIR_A_HARD_WALL_SECONDS,
    )

    gate_a = commands.add_parser("gate-a-build")
    _add_formal_inputs(gate_a)
    gate_a.add_argument("--result-output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    common = {
        "architecture": Architecture(args.architecture),
        "service_path": args.service_file,
        "d40_gate_a_manifest_path": args.d40_gate_a_manifest,
        "d41_gate_a_manifest_path": args.d41_gate_a_manifest,
        "heat_path": args.heat_path,
        "vre_path": args.vre_path,
        "price_basis_path": args.price_basis_path,
    }
    if args.command == "_guide-child":
        solve_guide_child(
            **common,
            seed_output_path=args.seed_output,
            result_output_path=args.result_output,
            threads=args.threads,
            time_limit_seconds=args.time_limit_seconds,
        )
        return
    if args.command == "_candidate-child":
        solve_candidate_child(
            **common,
            seed_path=args.seed_path,
            d41_bess_guide_path=args.d41_bess_guide,
            fallback_seed_output_path=args.fallback_seed_output,
            candidate_output_path=args.candidate_output,
            result_output_path=args.result_output,
            threads=args.threads,
            time_limit_seconds=args.time_limit_seconds,
        )
        return
    if args.command == "_repair-child":
        solve_repair_child(
            **common,
            repair=args.repair,
            candidate_path=args.candidate_path,
            solution_output_path=args.solution_output,
            result_output_path=args.result_output,
            threads=args.threads,
            time_limit_seconds=args.time_limit_seconds,
        )
        return
    if args.command == "gate-a-build":
        write_gate_a_build_audit(
            **common,
            result_output_path=args.result_output,
        )
        return
    raise AssertionError(f"unhandled D46 command: {args.command}")


if __name__ == "__main__":
    main()
