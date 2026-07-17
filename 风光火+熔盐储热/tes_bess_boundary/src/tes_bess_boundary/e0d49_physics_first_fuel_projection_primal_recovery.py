"""E0-D-49 physics-first primal recovery with exact CHP fuel lifting.

The candidate MILP keeps every physical binary and every original constraint.
Only the logarithmic CHP fuel-segment code bits are projected to ``[0, 1]``.
Any candidate must then be lifted deterministically to adjacent fuel segments,
restored to the complete original binary domain, independently audited, and
finally repaired in a clean original-cost model before it can be an upper
bound.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence

from tes_bess_boundary.e0d40_full_year_compute_gate import _linearity_audit
from tes_bess_boundary.e0d40_gate_b_solver import FORMAL_ARCHITECTURES
from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
    BinaryInventory,
    extract_binary_snapshot,
    restore_binary_domains,
)
from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
    CLAIM_SCOPE,
    EXPECTED_MODEL_SIZE,
    FORMAL_PROJECT_TAC_READY,
    TECHNICAL_RANKING_PERMITTED,
    _bound_and_constraint_audit,
    _name_list_sha256,
    _service_audit,
    _sha256,
    _tree_sha256,
    _variable_map,
    apply_complete_seed,
    read_seed_csv_gz,
    write_seed_csv_gz,
)
from tes_bess_boundary.e0d48_hamming_primal_recovery import (
    CANDIDATE_SOFT_TIME_LIMIT_SECONDS,
    D46_GUIDE_SHA256,
    FORMAL_THREADS,
    REPAIR_HARD_WALL_SECONDS,
    build_original_stage_model,
    capture_first_hamming_incumbent,
    constraint_identity,
    highs_option_roundtrip,
    solve_original_cost_repair,
)
from tes_bess_boundary.model import Architecture


RESULT_SCHEMA_ID = "tes_bess_boundary.e0d49_physics_first_recovery.v1"
BUILD_SCHEMA_ID = "tes_bess_boundary.e0d49_gate_a_build.v1"
REPAIR_SCHEMA_ID = "tes_bess_boundary.e0d49_original_cost_repair.v1"

FUEL_LIFT_POWER_TOLERANCE_MW = 1e-9
OFFLINE_POWER_TOLERANCE_MW = 1e-7
BINARY_VALUE_TOLERANCE = 1e-7

EXPECTED_FUEL_CODE_BINARY_COUNT = 52_704
EXPECTED_PHYSICAL_BINARY_COUNT = {
    Architecture.BESS: 26_353,
    Architecture.TES: 35_136,
    Architecture.HYBRID: 43_921,
}
FUEL_CODE_COMPONENT = re.compile(r"^chp\[\d+\]\.fuel_code_bit$")


@dataclass(frozen=True)
class FuelBinaryPartition:
    """Disjoint result-before partition of the original D41 inventory."""

    projected_fuel_code_names: tuple[str, ...]
    physical_binary_names: tuple[str, ...]

    def __post_init__(self) -> None:
        projected = set(self.projected_fuel_code_names)
        physical = set(self.physical_binary_names)
        if len(projected) != len(self.projected_fuel_code_names):
            raise ValueError("D49 projected fuel-code names contain duplicates")
        if len(physical) != len(self.physical_binary_names):
            raise ValueError("D49 physical binary names contain duplicates")
        if projected & physical:
            raise ValueError("D49 binary partitions overlap")

    @property
    def projected_names_sha256(self) -> str:
        return _name_list_sha256(self.projected_fuel_code_names)

    @property
    def physical_names_sha256(self) -> str:
        return _name_list_sha256(self.physical_binary_names)


def partition_fuel_code_binaries(
    model: object,
    inventory: BinaryInventory,
    *,
    architecture: Architecture,
    require_formal_counts: bool,
) -> tuple[FuelBinaryPartition, dict[str, Any]]:
    """Partition only CHP logarithmic code bits from all physical binaries."""

    variables = _variable_map(model)
    missing = sorted(set(inventory.all_names) - set(variables))
    if missing:
        raise ValueError(f"D49 inventory variables are missing: {missing[:3]}")
    projected = tuple(
        name
        for name in inventory.all_names
        if FUEL_CODE_COMPONENT.fullmatch(variables[name].parent_component().name)
    )
    projected_set = set(projected)
    physical = tuple(name for name in inventory.all_names if name not in projected_set)
    partition = FuelBinaryPartition(projected, physical)
    complete = set(projected) | set(physical) == set(inventory.all_names) and not (
        set(projected) & set(physical)
    )
    component_names = tuple(
        sorted({variables[name].parent_component().name for name in projected})
    )
    components_valid = bool(component_names) and all(
        FUEL_CODE_COMPONENT.fullmatch(name) for name in component_names
    )
    formal_counts_passed = (
        len(projected) == EXPECTED_FUEL_CODE_BINARY_COUNT
        and len(physical) == EXPECTED_PHYSICAL_BINARY_COUNT[architecture]
        and len(inventory.all_names)
        == EXPECTED_FUEL_CODE_BINARY_COUNT
        + EXPECTED_PHYSICAL_BINARY_COUNT[architecture]
    )
    passed = (
        complete
        and components_valid
        and (formal_counts_passed if require_formal_counts else True)
    )
    return partition, {
        "architecture": architecture.value,
        "original_binary_count": len(inventory.all_names),
        "original_binary_names_sha256": _name_list_sha256(inventory.all_names),
        "projected_fuel_code_binary_count": len(projected),
        "projected_fuel_code_names_sha256": partition.projected_names_sha256,
        "physical_binary_count": len(physical),
        "physical_binary_names_sha256": partition.physical_names_sha256,
        "projected_component_names": list(component_names),
        "partition_complete_and_disjoint": complete,
        "projected_components_valid": components_valid,
        "formal_counts_required": require_formal_counts,
        "formal_counts_passed": formal_counts_passed,
        "passed": passed,
    }


def fuel_projection_dependency_audit(model: object) -> dict[str, Any]:
    """Prove code bits and fuel flow have only the pre-registered couplings."""

    from pyomo.core.expr.visitor import identify_variables
    from pyomo.environ import Constraint, Objective

    code_variables: dict[int, str] = {}
    flow_variables: dict[int, str] = {}
    allowed_code_constraints: set[str] = set()
    allowed_flow_constraints: set[str] = set()
    for unit in model.unit_index:
        block = model.chp[unit]
        if not hasattr(block, "fuel_code_bit") or not hasattr(block, "fuel_code"):
            raise ValueError("D49 requires logarithmic CHP fuel encoding")
        allowed_code_constraints.add(block.fuel_code.name)
        allowed_flow_constraints.add(block.fuel_flow_definition.name)
        for variable in block.fuel_code_bit.values():
            code_variables[id(variable)] = variable.name
        for variable in block.fuel_tce_per_hour.values():
            flow_variables[id(variable)] = variable.name

    code_occurrences = {name: 0 for name in code_variables.values()}
    flow_occurrences = {name: 0 for name in flow_variables.values()}
    code_variable_ids = set(code_variables)
    flow_variable_ids = set(flow_variables)
    forbidden_code_constraints: list[str] = []
    forbidden_flow_constraints: list[str] = []
    touched_code_constraints: set[str] = set()
    touched_flow_constraints: set[str] = set()
    for constraint in model.component_data_objects(
        Constraint, active=True, descend_into=True
    ):
        variable_ids = {id(item) for item in identify_variables(constraint.body)}
        touched_code = variable_ids & code_variable_ids
        touched_flow = variable_ids & flow_variable_ids
        if touched_code:
            touched_code_constraints.add(constraint.parent_component().name)
            if constraint.parent_component().name not in allowed_code_constraints:
                forbidden_code_constraints.append(constraint.name)
            for variable_id in touched_code:
                code_occurrences[code_variables[variable_id]] += 1
        if touched_flow:
            touched_flow_constraints.add(constraint.parent_component().name)
            if constraint.parent_component().name not in allowed_flow_constraints:
                forbidden_flow_constraints.append(constraint.name)
            for variable_id in touched_flow:
                flow_occurrences[flow_variables[variable_id]] += 1

    objective_code_names: set[str] = set()
    objective_flow_names: set[str] = set()
    active_objectives = tuple(
        model.component_data_objects(Objective, active=True, descend_into=True)
    )
    for objective in active_objectives:
        for variable in identify_variables(objective.expr):
            variable_id = id(variable)
            if variable_id in code_variables:
                objective_code_names.add(code_variables[variable_id])
            if variable_id in flow_variables:
                objective_flow_names.add(flow_variables[variable_id])

    code_bad_occurrence_names = tuple(
        sorted(name for name, count in code_occurrences.items() if count != 1)
    )
    flow_bad_occurrence_names = tuple(
        sorted(name for name, count in flow_occurrences.items() if count != 1)
    )
    passed = all(
        (
            bool(code_variables),
            bool(flow_variables),
            not forbidden_code_constraints,
            not forbidden_flow_constraints,
            not code_bad_occurrence_names,
            not flow_bad_occurrence_names,
            not objective_code_names,
            len(objective_flow_names) == len(flow_variables),
            touched_code_constraints == allowed_code_constraints,
            touched_flow_constraints == allowed_flow_constraints,
            len(active_objectives) == 1,
        )
    )
    return {
        "fuel_code_variable_count": len(code_variables),
        "fuel_flow_variable_count": len(flow_variables),
        "active_objective_count": len(active_objectives),
        "touched_code_constraint_components": sorted(touched_code_constraints),
        "allowed_code_constraint_components": sorted(allowed_code_constraints),
        "touched_flow_constraint_components": sorted(touched_flow_constraints),
        "allowed_flow_constraint_components": sorted(allowed_flow_constraints),
        "forbidden_code_constraint_count": len(forbidden_code_constraints),
        "forbidden_code_constraint_names_sha256": _name_list_sha256(
            tuple(sorted(forbidden_code_constraints))
        ),
        "forbidden_flow_constraint_count": len(forbidden_flow_constraints),
        "forbidden_flow_constraint_names_sha256": _name_list_sha256(
            tuple(sorted(forbidden_flow_constraints))
        ),
        "code_bad_occurrence_count": len(code_bad_occurrence_names),
        "code_bad_occurrence_names_sha256": _name_list_sha256(
            code_bad_occurrence_names
        ),
        "flow_bad_occurrence_count": len(flow_bad_occurrence_names),
        "flow_bad_occurrence_names_sha256": _name_list_sha256(
            flow_bad_occurrence_names
        ),
        "objective_code_variable_count": len(objective_code_names),
        "objective_fuel_flow_variable_count": len(objective_flow_names),
        "fuel_flow_used_only_by_definition_and_original_objective": True,
        "fuel_or_emissions_cap_detected": bool(forbidden_flow_constraints),
        "passed": passed,
    }


def relax_fuel_code_binaries(
    model: object,
    inventory: BinaryInventory,
    partition: FuelBinaryPartition,
) -> dict[str, Any]:
    """Relax exactly the projected code bits and no physical binary."""

    from pyomo.environ import UnitInterval

    variables = _variable_map(model)
    projected = set(partition.projected_fuel_code_names)
    physical = set(partition.physical_binary_names)
    if projected | physical != set(inventory.all_names) or projected & physical:
        raise ValueError("D49 cannot relax an incomplete binary partition")
    for name in partition.projected_fuel_code_names:
        variables[name].domain = UnitInterval
        variables[name].setlb(0.0)
        variables[name].setub(1.0)
    projected_relaxed = all(
        not variables[name].is_binary()
        and float(variables[name].lb) == 0.0
        and float(variables[name].ub) == 1.0
        for name in partition.projected_fuel_code_names
    )
    physical_retained = all(
        variables[name].is_binary() for name in partition.physical_binary_names
    )
    active_binary_names = tuple(
        sorted(name for name, variable in variables.items() if variable.is_binary())
    )
    passed = (
        projected_relaxed and physical_retained and set(active_binary_names) == physical
    )
    return {
        "projected_relaxed_to_unit_interval": projected_relaxed,
        "physical_binaries_retained": physical_retained,
        "active_binary_count_after_projection": len(active_binary_names),
        "active_binary_names_sha256_after_projection": _name_list_sha256(
            active_binary_names
        ),
        "only_registered_fuel_code_bits_projected": True,
        "passed": passed,
    }


def replace_cost_objective_with_physical_hamming(
    model: object,
    partition: FuelBinaryPartition,
    binary_seed: Mapping[str, int],
) -> dict[str, Any]:
    """Use equal-weight Hamming distance over physical binaries only."""

    from pyomo.environ import Objective, minimize, quicksum, value

    if not set(partition.physical_binary_names).issubset(binary_seed):
        raise ValueError("D49 guide does not cover all physical binaries")
    invalid = sorted(
        name
        for name in partition.physical_binary_names
        if binary_seed[name] not in (0, 1)
    )
    if invalid:
        raise ValueError(f"D49 physical Hamming seed is invalid: {invalid[:3]}")
    objectives = tuple(
        model.component_data_objects(Objective, active=True, descend_into=True)
    )
    if len(objectives) != 1:
        raise ValueError("D49 requires exactly one original active objective")
    original = objectives[0]
    original_name = original.name
    original.deactivate()
    variables = _variable_map(model)
    expression = quicksum(
        variables[name] if binary_seed[name] == 0 else 1.0 - variables[name]
        for name in partition.physical_binary_names
    )
    model.d49_physical_hamming_distance = Objective(expr=expression, sense=minimize)
    seed_value = float(value(model.d49_physical_hamming_distance))
    active_after = tuple(
        model.component_data_objects(Objective, active=True, descend_into=True)
    )
    passed = (
        len(active_after) == 1
        and active_after[0] is model.d49_physical_hamming_distance
        and math.isclose(seed_value, 0.0, rel_tol=0.0, abs_tol=1e-12)
    )
    return {
        "original_objective_name": original_name,
        "original_objective_active_after": bool(original.active),
        "hamming_objective_name": model.d49_physical_hamming_distance.name,
        "hamming_physical_binary_term_count": len(partition.physical_binary_names),
        "hamming_physical_binary_names_sha256": partition.physical_names_sha256,
        "projected_fuel_code_binary_term_count": 0,
        "equal_binary_weight": 1.0,
        "auxiliary_variable_count": 0,
        "added_constraint_count": 0,
        "hamming_value_at_seed": seed_value,
        "active_objective_count_after": len(active_after),
        "passed": passed,
    }


def prepare_physics_first_model(
    model: object,
    inventory: BinaryInventory,
    *,
    architecture: Architecture,
    guide_path: Path,
    require_locked_guide_hash: bool = True,
    require_formal_counts: bool = True,
) -> tuple[FuelBinaryPartition, dict[str, int], dict[str, Any]]:
    """Load the frozen guide, prove projection safety, and replace the objective."""

    guide_hash = _sha256(guide_path)
    expected_hash = D46_GUIDE_SHA256[architecture]
    if require_locked_guide_hash and guide_hash != expected_hash:
        raise ValueError("D49 D46 guide hash mismatch")
    variable_names = tuple(sorted(_variable_map(model)))
    values, binary_seed = read_seed_csv_gz(
        guide_path,
        expected_variable_names=variable_names,
        expected_binary_names=inventory.all_names,
    )
    seed_audit = apply_complete_seed(model, inventory, values, binary_seed)
    partition, partition_audit = partition_fuel_code_binaries(
        model,
        inventory,
        architecture=architecture,
        require_formal_counts=require_formal_counts,
    )
    dependency_audit = fuel_projection_dependency_audit(model)
    constraints_before = constraint_identity(model)
    relaxation_audit = relax_fuel_code_binaries(model, inventory, partition)
    objective_audit = replace_cost_objective_with_physical_hamming(
        model,
        partition,
        binary_seed,
    )
    constraints_after = constraint_identity(model)
    constraint_identity_preserved = constraints_before == constraints_after
    passed = all(
        (
            seed_audit["passed"],
            partition_audit["passed"],
            dependency_audit["passed"],
            relaxation_audit["passed"],
            objective_audit["passed"],
            constraint_identity_preserved,
        )
    )
    return (
        partition,
        binary_seed,
        {
            "guide_sha256": guide_hash,
            "expected_guide_sha256": expected_hash,
            "guide_hash_required": require_locked_guide_hash,
            "seed_application_audit": seed_audit,
            "binary_partition_audit": partition_audit,
            "fuel_projection_dependency_audit": dependency_audit,
            "fuel_code_relaxation_audit": relaxation_audit,
            "constraint_identity_before": constraints_before,
            "constraint_identity_after": constraints_after,
            "constraint_identity_preserved": constraint_identity_preserved,
            "objective_replacement_audit": objective_audit,
            "passed": passed,
        },
    )


def deterministic_fuel_lift_point(
    *,
    online: float,
    power_gross_mw: float,
    fuel_knots: Sequence[tuple[float, float]],
    binary_tolerance: float = BINARY_VALUE_TOLERANCE,
    power_tolerance_mw: float = FUEL_LIFT_POWER_TOLERANCE_MW,
) -> dict[str, Any]:
    """Lift one online/power point to the unique pre-registered adjacent segment."""

    if len(fuel_knots) < 2:
        raise ValueError("D49 fuel lift requires at least two knots")
    if not all(math.isfinite(float(item)) for knot in fuel_knots for item in knot):
        raise ValueError("D49 fuel lift knots must be finite")
    rounded_online = int(round(float(online)))
    if (
        rounded_online not in (0, 1)
        or abs(float(online) - rounded_online) > binary_tolerance
    ):
        raise ValueError("D49 online value is not binary")
    power = float(power_gross_mw)
    if not math.isfinite(power):
        raise ValueError("D49 gross power is not finite")
    segment_count = len(fuel_knots) - 1
    if rounded_online == 0:
        if abs(power) > OFFLINE_POWER_TOLERANCE_MW:
            raise ValueError("D49 offline CHP has nonzero gross power")
        return {
            "online": 0,
            "lifted_power_gross_mw": 0.0,
            "allowed_power_clamp_mw": OFFLINE_POWER_TOLERANCE_MW,
            "selected_segment": None,
            "segment_active": (0,) * segment_count,
            "segment_fraction": (0.0,) * segment_count,
            "fuel_code_bits": (0,) * max(1, (segment_count - 1).bit_length()),
            "fuel_tce_per_hour": 0.0,
        }

    lower_power = float(fuel_knots[0][0])
    upper_power = float(fuel_knots[-1][0])
    if power < lower_power - power_tolerance_mw:
        raise ValueError("D49 online gross power lies below the fuel domain")
    if power > upper_power + power_tolerance_mw:
        raise ValueError("D49 online gross power lies above the fuel domain")
    lifted_power = min(max(power, lower_power), upper_power)
    selected = next(
        (
            index
            for index in range(segment_count)
            if lifted_power <= float(fuel_knots[index + 1][0]) + power_tolerance_mw
        ),
        segment_count - 1,
    )
    segment_lower_power, segment_lower_fuel = fuel_knots[selected]
    segment_upper_power, segment_upper_fuel = fuel_knots[selected + 1]
    width = float(segment_upper_power) - float(segment_lower_power)
    if width <= 0.0:
        raise ValueError("D49 fuel knots are not strictly increasing")
    fraction = (lifted_power - float(segment_lower_power)) / width
    if fraction < -power_tolerance_mw or fraction > 1.0 + power_tolerance_mw:
        raise ValueError("D49 lifted fuel fraction lies outside the selected segment")
    fraction = min(max(fraction, 0.0), 1.0)
    active = tuple(int(index == selected) for index in range(segment_count))
    fractions = tuple(
        fraction if index == selected else 0.0 for index in range(segment_count)
    )
    code_bit_count = max(1, (segment_count - 1).bit_length())
    code = tuple((selected >> bit) & 1 for bit in range(code_bit_count))
    fuel = (
        float(segment_lower_fuel)
        + (float(segment_upper_fuel) - float(segment_lower_fuel)) * fraction
    )
    return {
        "online": 1,
        "lifted_power_gross_mw": lifted_power,
        "allowed_power_clamp_mw": power_tolerance_mw,
        "selected_segment": selected,
        "segment_active": active,
        "segment_fraction": fractions,
        "fuel_code_bits": code,
        "fuel_tce_per_hour": fuel,
    }


def static_fuel_lift_spec_audit(chp_units: Sequence[object]) -> dict[str, Any]:
    """Exercise every registered segment and knot without invoking a solver."""

    unit_audits: dict[str, Any] = {}
    passed = True
    for unit_index, spec in enumerate(chp_units):
        knots = tuple(spec.fuel_flow_knots())
        segment_count = len(knots) - 1
        midpoint_checks: list[bool] = []
        for segment in range(segment_count):
            midpoint = 0.5 * (float(knots[segment][0]) + float(knots[segment + 1][0]))
            lifted = deterministic_fuel_lift_point(
                online=1.0,
                power_gross_mw=midpoint,
                fuel_knots=knots,
            )
            midpoint_checks.append(
                lifted["selected_segment"] == segment
                and sum(lifted["segment_active"]) == 1
                and lifted["segment_active"][segment] == 1
            )
        tie_checks: list[bool] = []
        for knot_index in range(1, len(knots) - 1):
            lifted = deterministic_fuel_lift_point(
                online=1.0,
                power_gross_mw=float(knots[knot_index][0]),
                fuel_knots=knots,
            )
            tie_checks.append(
                lifted["selected_segment"] == knot_index - 1
                and lifted["segment_fraction"][knot_index - 1] == 1.0
            )
        minimum = deterministic_fuel_lift_point(
            online=1.0,
            power_gross_mw=float(knots[0][0]),
            fuel_knots=knots,
        )
        maximum = deterministic_fuel_lift_point(
            online=1.0,
            power_gross_mw=float(knots[-1][0]),
            fuel_knots=knots,
        )
        offline = deterministic_fuel_lift_point(
            online=0.0,
            power_gross_mw=0.0,
            fuel_knots=knots,
        )
        unit_passed = (
            all(midpoint_checks)
            and all(tie_checks)
            and all(
                (
                    minimum["selected_segment"] == 0,
                    minimum["segment_fraction"][0] == 0.0,
                    maximum["selected_segment"] == segment_count - 1,
                    maximum["segment_fraction"][segment_count - 1] == 1.0,
                    offline["selected_segment"] is None,
                    offline["fuel_tce_per_hour"] == 0.0,
                )
            )
        )
        unit_audits[str(unit_index)] = {
            "fuel_knot_count": len(knots),
            "fuel_segment_count": segment_count,
            "fuel_knots_sha256": hashlib.sha256(
                json.dumps(knots, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "midpoint_check_count": len(midpoint_checks),
            "internal_knot_tie_check_count": len(tie_checks),
            "offline_check_passed": offline["selected_segment"] is None,
            "minimum_knot_check_passed": minimum["selected_segment"] == 0,
            "maximum_knot_check_passed": (
                maximum["selected_segment"] == segment_count - 1
            ),
            "passed": unit_passed,
        }
        passed = passed and unit_passed
    return {
        "chp_unit_count": len(chp_units),
        "unit_audit": unit_audits,
        "all_registered_segments_and_knots_checked": True,
        "passed": passed and bool(chp_units),
    }


def exact_lift_fuel_encoding(
    model: object, chp_units: Sequence[object]
) -> dict[str, Any]:
    """Apply the deterministic point lift to every CHP unit and period."""

    from pyomo.environ import value

    variables = _variable_map(model)
    fuel_names: set[str] = set()
    power_names: set[str] = set()
    for unit in model.unit_index:
        block = model.chp[unit]
        power_names.update(variable.name for variable in block.power_gross.values())
        for component_name in (
            "fuel_segment_active",
            "fuel_segment_fraction",
            "fuel_code_bit",
            "fuel_tce_per_hour",
        ):
            fuel_names.update(
                variable.name for variable in getattr(block, component_name).values()
            )
    before = {
        name: float(value(variable))
        for name, variable in variables.items()
        if name not in fuel_names
    }

    selected_counts: dict[int, int] = {}
    offline_count = 0
    lifted_point_count = 0
    maximum_clamp_ratio = 0.0
    for unit in model.unit_index:
        unit_index = int(unit)
        block = model.chp[unit]
        knots = tuple(chp_units[unit_index].fuel_flow_knots())
        if len(tuple(block.fuel_segment_index)) != len(knots) - 1:
            raise ValueError("D49 model/spec fuel segment count mismatch")
        for period in model.periods:
            lifted = deterministic_fuel_lift_point(
                online=float(value(block.online[period])),
                power_gross_mw=float(value(block.power_gross[period])),
                fuel_knots=knots,
            )
            original_power = float(value(block.power_gross[period]))
            power_change = abs(lifted["lifted_power_gross_mw"] - original_power)
            allowed_change = float(lifted["allowed_power_clamp_mw"])
            maximum_clamp_ratio = max(
                maximum_clamp_ratio,
                power_change / allowed_change if allowed_change > 0.0 else math.inf,
            )
            block.power_gross[period].set_value(
                lifted["lifted_power_gross_mw"], skip_validation=True
            )
            for segment in block.fuel_segment_index:
                index = int(segment)
                block.fuel_segment_active[period, segment].set_value(
                    lifted["segment_active"][index], skip_validation=True
                )
                block.fuel_segment_fraction[period, segment].set_value(
                    lifted["segment_fraction"][index], skip_validation=True
                )
            for bit in block.fuel_code_bit_index:
                index = int(bit)
                block.fuel_code_bit[period, bit].set_value(
                    lifted["fuel_code_bits"][index], skip_validation=True
                )
            block.fuel_tce_per_hour[period].set_value(
                lifted["fuel_tce_per_hour"], skip_validation=True
            )
            selected = lifted["selected_segment"]
            if selected is None:
                offline_count += 1
            else:
                selected_counts[int(selected)] = (
                    selected_counts.get(int(selected), 0) + 1
                )
            lifted_point_count += 1

    after = {
        name: float(value(variable))
        for name, variable in variables.items()
        if name not in fuel_names
    }
    strict_names = tuple(sorted(set(before) - power_names))
    changed_strict = tuple(name for name in strict_names if after[name] != before[name])
    max_power_change = max(
        (abs(after[name] - before[name]) for name in power_names),
        default=0.0,
    )
    passed = not changed_strict and maximum_clamp_ratio <= 1.0
    return {
        "lifted_chp_point_count": lifted_point_count,
        "offline_chp_point_count": offline_count,
        "selected_segment_counts": {
            str(key): selected_counts[key] for key in sorted(selected_counts)
        },
        "fuel_variable_count_rewritten": len(fuel_names),
        "strict_nonfuel_variable_count": len(strict_names),
        "changed_strict_nonfuel_variable_count": len(changed_strict),
        "changed_strict_nonfuel_names_sha256": _name_list_sha256(changed_strict),
        "gross_power_variable_count": len(power_names),
        "max_gross_power_numerical_clamp_mw": max_power_change,
        "maximum_power_clamp_to_allowed_ratio": maximum_clamp_ratio,
        "online_power_clamp_tolerance_mw": FUEL_LIFT_POWER_TOLERANCE_MW,
        "offline_power_clamp_tolerance_mw": OFFLINE_POWER_TOLERANCE_MW,
        "internal_knot_tie_break": "lowest_adjacent_segment_index",
        "maximum_knot_segment": "last_segment",
        "passed": passed,
    }


def projected_model_size_audit(
    original_size: Mapping[str, Any],
    projected_size: Mapping[str, Any],
    partition: FuelBinaryPartition,
) -> dict[str, Any]:
    """Require an unchanged linear model except for the projected binary count."""

    expected_binary_count = int(original_size["active_binary_variable_count"]) - len(
        partition.projected_fuel_code_names
    )
    passed = all(
        (
            projected_size["active_variable_count"]
            == original_size["active_variable_count"],
            projected_size["active_constraint_count"]
            == original_size["active_constraint_count"],
            projected_size["active_binary_variable_count"] == expected_binary_count,
            projected_size["nonlinear_component_count"] == 0,
        )
    )
    return {
        "original_model_size": dict(original_size),
        "projected_model_size": dict(projected_size),
        "expected_projected_binary_count": expected_binary_count,
        "variable_and_constraint_identity_retained": (
            projected_size["active_variable_count"]
            == original_size["active_variable_count"]
            and projected_size["active_constraint_count"]
            == original_size["active_constraint_count"]
        ),
        "passed": passed,
    }


def solve_physics_first_candidate(
    model: object,
    inventory: BinaryInventory,
    chp_units: Sequence[object],
    *,
    architecture: Architecture,
    guide_path: Path,
    candidate_output_path: Path,
    time_limit_seconds: float = CANDIDATE_SOFT_TIME_LIMIT_SECONDS,
    threads: int = FORMAL_THREADS,
    require_locked_guide_hash: bool = True,
    require_formal_counts: bool = True,
) -> dict[str, Any]:
    """Solve the projected candidate MILP, lift it, and archive only audited data."""

    partition, _, preparation = prepare_physics_first_model(
        model,
        inventory,
        architecture=architecture,
        guide_path=guide_path,
        require_locked_guide_hash=require_locked_guide_hash,
        require_formal_counts=require_formal_counts,
    )
    callback = capture_first_hamming_incumbent(
        model,
        time_limit_seconds=time_limit_seconds,
        threads=threads,
    )
    if callback["incumbent_captured"] is not True:
        status = callback["status"]
        if status == "engineering_mip_infeasible_under_original_bounds":
            status = "engineering_mip_infeasible_under_projection"
        return {
            **callback,
            "status": status,
            "preparation_audit": preparation,
            "candidate_artifact": None,
        }
    callback.pop("variable_values")
    try:
        lift_audit = exact_lift_fuel_encoding(model, chp_units)
        if lift_audit["passed"] is not True:
            raise ValueError("D49 exact fuel lift changed an unregistered variable")
        restore_binary_domains(model, inventory)
        snapshot = extract_binary_snapshot(model, inventory, tolerance=1e-7)
    except Exception as error:  # noqa: BLE001 - canonical failed-lift evidence
        return {
            **callback,
            "status": "candidate_found_but_exact_lift_failed",
            "preparation_audit": preparation,
            "exact_fuel_lift_audit": locals().get("lift_audit"),
            "exact_lift_error_type": type(error).__name__,
            "exact_lift_error_message": str(error),
            "candidate_artifact": None,
            "formal_upper_bound_eligible": False,
        }
    feasibility = _bound_and_constraint_audit(model)
    service = _service_audit(model)
    candidate_passed = feasibility["passed"] and service["passed"]
    artifact = None
    status = "candidate_found_but_exact_lift_failed"
    if candidate_passed:
        values = {
            name: float(variable.value)
            for name, variable in sorted(_variable_map(model).items())
        }
        artifact = write_seed_csv_gz(candidate_output_path, values, snapshot)
        status = "candidate_incumbent_captured_and_exactly_lifted"
    return {
        **callback,
        "status": status,
        "preparation_audit": preparation,
        "exact_fuel_lift_audit": lift_audit,
        "candidate_independent_feasibility_audit": feasibility,
        "candidate_service_audit": service,
        "candidate_audit_passed": candidate_passed,
        "binary_snapshot_variable_count": len(snapshot),
        "binary_snapshot_names_sha256": _name_list_sha256(tuple(sorted(snapshot))),
        "candidate_artifact": artifact,
        "candidate_requires_original_cost_repair": True,
        "formal_upper_bound_eligible": False,
    }


def solve_d49_original_cost_repair(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Reuse the audited D48 clean-model repair under a D49 schema."""

    result = solve_original_cost_repair(*args, **kwargs)
    result["schema_id"] = REPAIR_SCHEMA_ID
    result["candidate_exact_fuel_lift_required"] = True
    return result


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
        "e0d49_physics_first_fuel_projection_primal_recovery.py",
        "e0d49_monitored_executor.py",
        "e0d48_hamming_primal_recovery.py",
        "e0d46_full_year_feasible_upper_bound_repair.py",
        "e0d41_strict_full_year_decomposition.py",
        "e0d40_gate_b_solver.py",
        "e0d40_full_year_compute_gate.py",
        "planning_model.py",
        "components/chp.py",
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


def solve_candidate_child(
    *,
    architecture: Architecture,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    guide_path: Path,
    candidate_output_path: Path,
    result_output_path: Path,
    threads: int = FORMAL_THREADS,
    time_limit_seconds: float = CANDIDATE_SOFT_TIME_LIMIT_SECONDS,
) -> dict[str, Any]:
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
    solver_invoked = False
    try:
        case, model, inventory, build_audit = build_original_stage_model(
            architecture=architecture,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        )
        solver_invoked = True
        candidate = solve_physics_first_candidate(
            model,
            inventory,
            case.chp_units,
            architecture=architecture,
            guide_path=guide_path,
            candidate_output_path=candidate_output_path,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
            require_locked_guide_hash=True,
            require_formal_counts=True,
        )
        payload = {
            **base,
            "solver_invoked": True,
            "build_audit": build_audit,
            **candidate,
        }
    except Exception as error:  # noqa: BLE001 - canonical formal evidence
        payload = {
            **base,
            "status": "no_primal_status_closure",
            "solver_invoked": solver_invoked,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "formal_upper_bound_eligible": False,
        }
    _write_json(result_output_path, payload)
    return payload


def solve_repair_child(
    *,
    architecture: Architecture,
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
    time_limit_seconds: float = REPAIR_HARD_WALL_SECONDS,
) -> dict[str, Any]:
    base = _formal_base_payload(
        architecture=architecture,
        stage="repair",
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    solver_invoked = False
    try:
        _, model, inventory, build_audit = build_original_stage_model(
            architecture=architecture,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        )
        solver_invoked = True
        repair = solve_d49_original_cost_repair(
            model,
            inventory,
            architecture=architecture,
            candidate_path=candidate_path,
            solution_output_path=solution_output_path,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
            require_named_constraint_groups=True,
        )
        payload = {
            **base,
            "solver_invoked": True,
            "build_audit": build_audit,
            **repair,
        }
    except Exception as error:  # noqa: BLE001 - canonical formal evidence
        payload = {
            **base,
            "status": "candidate_found_but_repair_failed",
            "solver_invoked": solver_invoked,
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
    guide_path: Path,
    result_output_path: Path,
) -> dict[str, Any]:
    """Build and project one 8784 h model without invoking formal optimize."""

    started = perf_counter()
    case, model, inventory, build_audit = build_original_stage_model(
        architecture=architecture,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    partition, _, preparation = prepare_physics_first_model(
        model,
        inventory,
        architecture=architecture,
        guide_path=guide_path,
        require_locked_guide_hash=True,
        require_formal_counts=True,
    )
    post_size = _linearity_audit(model)
    size_audit = projected_model_size_audit(
        EXPECTED_MODEL_SIZE[architecture], post_size, partition
    )
    static_lift_audit = static_fuel_lift_spec_audit(case.chp_units)
    option_audit = highs_option_roundtrip()
    passed = all(
        (
            build_audit["binary_inventory_audit"]["passed"],
            build_audit["original_capacity_boundary_audit"]["passed"],
            preparation["passed"],
            size_audit["passed"],
            static_lift_audit["passed"],
            option_audit["passed"],
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
        "schema_id": BUILD_SCHEMA_ID,
        "status": "gate_a_build_passed" if passed else "gate_a_build_failed",
        "solver_invoked": False,
        "formal_optimization_invoked": False,
        "runtime_seconds": perf_counter() - started,
        "build_audit": build_audit,
        "physics_first_preparation_audit": preparation,
        "projected_model_size_audit": size_audit,
        "static_fuel_lift_spec_audit": static_lift_audit,
        "highs_option_roundtrip": option_audit,
        "audit": {"passed": passed},
    }
    _write_json(result_output_path, payload)
    return payload


def _add_formal_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--architecture",
        choices=[item.value for item in FORMAL_ARCHITECTURES],
        required=True,
    )
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--d40-gate-a", type=Path, required=True)
    parser.add_argument("--d41-gate-a", type=Path, required=True)
    parser.add_argument("--heat", type=Path, required=True)
    parser.add_argument("--vre", type=Path, required=True)
    parser.add_argument("--price-basis", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    candidate = subparsers.add_parser("candidate")
    _add_formal_inputs(candidate)
    candidate.add_argument("--guide", type=Path, required=True)
    candidate.add_argument("--candidate-output", type=Path, required=True)
    candidate.add_argument("--result-output", type=Path, required=True)
    candidate.add_argument("--threads", type=int, default=FORMAL_THREADS)
    candidate.add_argument(
        "--time-limit", type=float, default=CANDIDATE_SOFT_TIME_LIMIT_SECONDS
    )
    repair = subparsers.add_parser("repair")
    _add_formal_inputs(repair)
    repair.add_argument("--candidate", type=Path, required=True)
    repair.add_argument("--solution-output", type=Path, required=True)
    repair.add_argument("--result-output", type=Path, required=True)
    repair.add_argument("--threads", type=int, default=FORMAL_THREADS)
    repair.add_argument("--time-limit", type=float, default=REPAIR_HARD_WALL_SECONDS)
    gate_a = subparsers.add_parser("gate-a-build")
    _add_formal_inputs(gate_a)
    gate_a.add_argument("--guide", type=Path, required=True)
    gate_a.add_argument("--result-output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    common = {
        "architecture": Architecture(args.architecture),
        "service_path": args.service,
        "d40_gate_a_manifest_path": args.d40_gate_a,
        "d41_gate_a_manifest_path": args.d41_gate_a,
        "heat_path": args.heat,
        "vre_path": args.vre,
        "price_basis_path": args.price_basis,
    }
    if args.command == "candidate":
        solve_candidate_child(
            **common,
            guide_path=args.guide,
            candidate_output_path=args.candidate_output,
            result_output_path=args.result_output,
            threads=args.threads,
            time_limit_seconds=args.time_limit,
        )
    elif args.command == "repair":
        solve_repair_child(
            **common,
            candidate_path=args.candidate,
            solution_output_path=args.solution_output,
            result_output_path=args.result_output,
            threads=args.threads,
            time_limit_seconds=args.time_limit,
        )
    else:
        write_gate_a_build_audit(
            **common,
            guide_path=args.guide,
            result_output_path=args.result_output,
        )


if __name__ == "__main__":
    main()
