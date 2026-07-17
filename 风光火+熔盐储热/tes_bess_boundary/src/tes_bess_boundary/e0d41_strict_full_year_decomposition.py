"""E0-D-41 strict full-year relaxation and binary-coverage audits.

Gate A never invokes a solver.  It proves that the two lower-bound models are
genuine relaxations of the locked D40 full-year MILP and that a candidate
binary trajectory can fix every discrete variable before a full-year repair.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

from tes_bess_boundary.e0d40_full_year_compute_gate import (
    CLAIM_SCOPE,
    FORMAL_PROJECT_TAC_READY,
    FULL_YEAR_HOURS,
    _available_memory_gib,
    _capacity_bound_audit,
    _linearity_audit,
    _peak_rss_gib,
    _sha256,
    _state_boundary_audit,
    _write_json,
)
from tes_bess_boundary.e0d40_gate_b_solver import (
    FORMAL_ARCHITECTURES,
    GATE_A_MANIFEST_SHA256,
    SERVICE_SHA256,
    _build_gate_b_model,
)
from tes_bess_boundary.model import Architecture


ARCHITECTURE_SCHEMA_ID = "tes_bess_boundary.e0d41_gate_a_architecture.v1"
GATE_A_SCHEMA_ID = "tes_bess_boundary.e0d41_gate_a_manifest.v1"
ARCHITECTURE_FILE_TEMPLATE = "gate_a_{architecture}.json"
ARCHITECTURE_EXECUTION_TEMPLATE = "gate_a_{architecture}_execution.json"
GATE_A_MANIFEST_NAME = "gate_a_manifest.json"
GATE_A_EXECUTION_NAME = "gate_a_execution.json"

TOPOLOGY_BINARY_COMPONENTS = frozenset(
    {
        "bess.installed",
        "tes.installed",
        "tes.port_installed",
    }
)


class RelaxationMode(str, Enum):
    """The two D41 lower-bound relaxations."""

    R0 = "r0_all_continuous"
    R1 = "r1_topology_integer"


@dataclass(frozen=True)
class BinaryInventory:
    """Complete, disjoint classification of an unrelaxed model's binaries."""

    all_names: tuple[str, ...]
    topology_names: tuple[str, ...]
    operational_names: tuple[str, ...]
    component_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        all_set = set(self.all_names)
        topology_set = set(self.topology_names)
        operational_set = set(self.operational_names)
        if len(all_set) != len(self.all_names):
            raise ValueError("binary inventory contains duplicate variable names")
        if topology_set & operational_set:
            raise ValueError("topology and operational binaries overlap")
        if topology_set | operational_set != all_set:
            raise ValueError("binary inventory classification is incomplete")

    @property
    def all_names_sha256(self) -> str:
        return _name_list_sha256(self.all_names)

    @property
    def topology_names_sha256(self) -> str:
        return _name_list_sha256(self.topology_names)

    @property
    def operational_names_sha256(self) -> str:
        return _name_list_sha256(self.operational_names)

    def to_audit(self) -> dict[str, Any]:
        return {
            "all_binary_variable_count": len(self.all_names),
            "topology_binary_variable_count": len(self.topology_names),
            "operational_binary_variable_count": len(self.operational_names),
            "classification_complete": (
                len(self.all_names)
                == len(self.topology_names) + len(self.operational_names)
            ),
            "all_binary_names_sha256": self.all_names_sha256,
            "topology_binary_names_sha256": self.topology_names_sha256,
            "operational_binary_names_sha256": self.operational_names_sha256,
            "component_counts": dict(self.component_counts),
            "topology_component_allowlist": sorted(TOPOLOGY_BINARY_COMPONENTS),
        }


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _name_list_sha256(names: tuple[str, ...]) -> str:
    body = "".join(f"{name}\n" for name in names).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _variable_map(model: object) -> dict[str, object]:
    from pyomo.environ import Var

    variables = list(
        model.component_data_objects(Var, active=True, descend_into=True)
    )
    mapping = {variable.name: variable for variable in variables}
    if len(mapping) != len(variables):
        raise ValueError("active model contains duplicate variable names")
    return mapping


def collect_binary_inventory(model: object) -> BinaryInventory:
    """Classify every active binary before any D41 relaxation is applied."""

    variables = _variable_map(model)
    binaries = sorted(
        (variable for variable in variables.values() if variable.is_binary()),
        key=lambda variable: variable.name,
    )
    all_names = tuple(variable.name for variable in binaries)
    topology_names = tuple(
        variable.name
        for variable in binaries
        if variable.parent_component().name in TOPOLOGY_BINARY_COMPONENTS
    )
    topology_set = set(topology_names)
    operational_names = tuple(
        name for name in all_names if name not in topology_set
    )
    component_counts = tuple(
        sorted(
            Counter(
                variable.parent_component().name for variable in binaries
            ).items()
        )
    )
    return BinaryInventory(
        all_names=all_names,
        topology_names=topology_names,
        operational_names=operational_names,
        component_counts=component_counts,
    )


def _require_exact_binary_inventory(
    model: object,
    inventory: BinaryInventory,
) -> dict[str, object]:
    variables = _variable_map(model)
    missing = sorted(set(inventory.all_names) - set(variables))
    active_binaries = {
        name for name, variable in variables.items() if variable.is_binary()
    }
    extra = sorted(active_binaries - set(inventory.all_names))
    not_binary = sorted(set(inventory.all_names) - active_binaries)
    if missing or extra or not_binary:
        raise ValueError(
            "model no longer matches the locked binary inventory: "
            f"missing={missing[:3]}, extra={extra[:3]}, "
            f"not_binary={not_binary[:3]}"
        )
    return variables


def restore_binary_domains(model: object, inventory: BinaryInventory) -> None:
    """Restore a previously relaxed model to its locked binary domains."""

    from pyomo.environ import Binary

    variables = _variable_map(model)
    missing = sorted(set(inventory.all_names) - set(variables))
    if missing:
        raise ValueError(f"cannot restore missing binary variables: {missing[:3]}")
    for name in inventory.all_names:
        variables[name].domain = Binary
    _require_exact_binary_inventory(model, inventory)


def apply_relaxation(
    model: object,
    inventory: BinaryInventory,
    mode: RelaxationMode,
) -> dict[str, Any]:
    """Apply R0 or R1 without deleting a variable or a model constraint."""

    from pyomo.environ import UnitInterval

    if not isinstance(mode, RelaxationMode):
        raise ValueError("mode must be selected with RelaxationMode")
    variables = _require_exact_binary_inventory(model, inventory)
    names_to_relax = (
        inventory.all_names
        if mode is RelaxationMode.R0
        else inventory.operational_names
    )
    bounds_before = {
        name: (variables[name].lb, variables[name].ub) for name in names_to_relax
    }
    for name in names_to_relax:
        variables[name].domain = UnitInterval
    bounds_preserved = all(
        (variables[name].lb, variables[name].ub) == bounds_before[name]
        for name in names_to_relax
    )
    remaining = tuple(
        sorted(
            name for name, variable in variables.items() if variable.is_binary()
        )
    )
    expected_remaining = (
        () if mode is RelaxationMode.R0 else inventory.topology_names
    )
    passed = (
        bounds_preserved
        and remaining == expected_remaining
        and len(names_to_relax) + len(remaining) == len(inventory.all_names)
    )
    return {
        "mode": mode.value,
        "relaxed_binary_variable_count": len(names_to_relax),
        "remaining_binary_variable_count": len(remaining),
        "remaining_binary_names_sha256": _name_list_sha256(remaining),
        "expected_remaining_binary_names_sha256": _name_list_sha256(
            expected_remaining
        ),
        "variable_count_unchanged": len(variables) == len(_variable_map(model)),
        "binary_bounds_preserved": bounds_preserved,
        "classification_complete": (
            len(names_to_relax) + len(remaining) == len(inventory.all_names)
        ),
        "passed": passed,
    }


def extract_binary_snapshot(
    model: object,
    inventory: BinaryInventory | None = None,
    *,
    tolerance: float = 1e-7,
) -> dict[str, int]:
    """Extract a complete exact discrete trajectory from a solved candidate."""

    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("binary snapshot tolerance must be finite and non-negative")
    locked = inventory or collect_binary_inventory(model)
    variables = _require_exact_binary_inventory(model, locked)
    snapshot: dict[str, int] = {}
    for name in locked.all_names:
        raw = variables[name].value
        if raw is None or not math.isfinite(float(raw)):
            raise ValueError(f"binary candidate value is not finite: {name}")
        rounded = int(round(float(raw)))
        if rounded not in (0, 1) or abs(float(raw) - rounded) > tolerance:
            raise ValueError(f"binary candidate value is fractional: {name}={raw}")
        snapshot[name] = rounded
    return snapshot


def fix_binary_snapshot(
    model: object,
    inventory: BinaryInventory,
    snapshot: Mapping[str, int | float],
    *,
    tolerance: float = 1e-7,
) -> dict[str, Any]:
    """Fix every locked binary and reject missing, extra, or fractional values."""

    variables = _require_exact_binary_inventory(model, inventory)
    expected = set(inventory.all_names)
    supplied = set(snapshot)
    missing = sorted(expected - supplied)
    extra = sorted(supplied - expected)
    if missing or extra:
        raise ValueError(
            "binary snapshot keys do not match the original MILP: "
            f"missing={missing[:3]}, extra={extra[:3]}"
        )
    for name in inventory.all_names:
        raw = snapshot[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"binary snapshot value is not numeric: {name}")
        if not math.isfinite(float(raw)):
            raise ValueError(f"binary snapshot value is not finite: {name}")
        rounded = int(round(float(raw)))
        if rounded not in (0, 1) or abs(float(raw) - rounded) > tolerance:
            raise ValueError(f"binary snapshot value is fractional: {name}={raw}")
        variables[name].fix(rounded)
    unfixed = tuple(
        sorted(
            name
            for name in inventory.all_names
            if not bool(variables[name].fixed)
        )
    )
    fixed_values = tuple(
        f"{name}={int(round(float(variables[name].value)))}"
        for name in inventory.all_names
    )
    return {
        "original_binary_variable_count": len(inventory.all_names),
        "fixed_binary_variable_count": len(inventory.all_names) - len(unfixed),
        "unfixed_binary_variable_count": len(unfixed),
        "unfixed_binary_names_sha256": _name_list_sha256(unfixed),
        "fixed_binary_snapshot_sha256": _name_list_sha256(fixed_values),
        "passed": len(unfixed) == 0,
    }


def _code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    return {
        "e0d41_strict_full_year_decomposition.py": _sha256(
            package / "e0d41_strict_full_year_decomposition.py"
        ),
        "e0d40_gate_b_solver.py": _sha256(package / "e0d40_gate_b_solver.py"),
        "e0d40_full_year_compute_gate.py": _sha256(
            package / "e0d40_full_year_compute_gate.py"
        ),
        "planning_model.py": _sha256(package / "planning_model.py"),
    }


def build_gate_a_architecture_audit(
    architecture: Architecture,
    service_path: Path,
    gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    """Build one locked 8784 h model and audit both D41 relaxations."""

    from pyomo.environ import value

    if architecture not in FORMAL_ARCHITECTURES:
        raise ValueError("D41 Gate A requires BESS, TES, or Hybrid")
    case, model, model_size = _build_gate_b_model(
        architecture,
        service_path,
        gate_a_manifest_path,
        heat_path,
        vre_path,
        price_basis_path,
    )
    inventory = collect_binary_inventory(model)
    original_variable_names = tuple(sorted(_variable_map(model)))

    r0_audit = apply_relaxation(model, inventory, RelaxationMode.R0)
    r0_linearity = _linearity_audit(model)
    restore_binary_domains(model, inventory)
    r1_audit = apply_relaxation(model, inventory, RelaxationMode.R1)
    r1_linearity = _linearity_audit(model)
    restore_binary_domains(model, inventory)

    zero_snapshot = {name: 0 for name in inventory.all_names}
    fixing_audit = fix_binary_snapshot(model, inventory, zero_snapshot)
    variable_names_after = tuple(sorted(_variable_map(model)))
    capacity_audit = _capacity_bound_audit(model, architecture)
    state_audit = _state_boundary_audit(model, architecture)
    weighted_hours = float(value(model.annual_weighted_hours))
    service_audit = {
        "curtailment_constraint_active": bool(
            model.annual_curtailment_service.active
        ),
        "pcc_export_constraint_active": bool(
            model.annual_pcc_export_service.active
        ),
        "weighted_annual_hours": weighted_hours,
        "single_full_year_dispatch_block": (
            len(case.horizon.dispatch_blocks) == 1
        ),
        "representative_period_input_used": False,
    }
    expected_binary_count = model_size["active_binary_variable_count"]
    passed = all(
        (
            len(inventory.all_names) == expected_binary_count,
            original_variable_names == variable_names_after,
            inventory.to_audit()["classification_complete"],
            r0_audit["passed"],
            r1_audit["passed"],
            r0_linearity["nonlinear_component_count"] == 0,
            r1_linearity["nonlinear_component_count"] == 0,
            fixing_audit["passed"],
            capacity_audit["passed"],
            state_audit["passed"],
            math.isclose(weighted_hours, FULL_YEAR_HOURS, abs_tol=1e-9),
            service_audit["curtailment_constraint_active"],
            service_audit["pcc_export_constraint_active"],
            service_audit["single_full_year_dispatch_block"],
        )
    )
    return {
        "schema_id": ARCHITECTURE_SCHEMA_ID,
        "status": "gate_a_passed" if passed else "gate_a_failed",
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "solver_invoked": False,
        "candidate_only": False,
        "architecture": architecture.value,
        "service_contract_sha256": _sha256(service_path),
        "d40_gate_a_manifest_sha256": _sha256(gate_a_manifest_path),
        "model_size": model_size,
        "binary_inventory": inventory.to_audit(),
        "r0_relaxation": r0_audit,
        "r1_relaxation": r1_audit,
        "r0_linearity": r0_linearity,
        "r1_linearity": r1_linearity,
        "synthetic_complete_fixing_audit": fixing_audit,
        "active_variable_names_unchanged": (
            original_variable_names == variable_names_after
        ),
        "active_variable_names_sha256": _name_list_sha256(
            original_variable_names
        ),
        "capacity_bound_audit": capacity_audit,
        "state_boundary_audit": state_audit,
        "service_audit": service_audit,
        "provenance": {"code_sha256": _code_hashes()},
        "audit": {"passed": passed},
    }


def write_gate_a_architecture_audit(
    architecture: Architecture,
    service_path: Path,
    gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Write the canonical audit and a noncanonical execution sidecar."""

    output_dir.mkdir(parents=True, exist_ok=True)
    before_memory = _available_memory_gib()
    started = perf_counter()
    payload = build_gate_a_architecture_audit(
        architecture,
        service_path,
        gate_a_manifest_path,
        heat_path,
        vre_path,
        price_basis_path,
    )
    runtime = perf_counter() - started
    filename = ARCHITECTURE_FILE_TEMPLATE.format(
        architecture=architecture.value
    )
    payload_bytes = _canonical_json_bytes(payload)
    (output_dir / filename).write_bytes(payload_bytes)
    execution = {
        "schema_id": f"{ARCHITECTURE_SCHEMA_ID}.execution",
        "architecture": architecture.value,
        "runtime_seconds": runtime,
        "peak_process_rss_gib": _peak_rss_gib(),
        "available_memory_before_gib": before_memory,
        "available_memory_after_gib": _available_memory_gib(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "manifest_sha256": hashlib.sha256(payload_bytes).hexdigest(),
    }
    _write_json(
        output_dir
        / ARCHITECTURE_EXECUTION_TEMPLATE.format(
            architecture=architecture.value
        ),
        execution,
    )
    if payload["audit"]["passed"] is not True:
        raise RuntimeError(f"D41 Gate A {architecture.value} audit failed")
    return payload


def compile_gate_a_manifest(audit_dir: Path) -> dict[str, Any]:
    """Compile the three clean-process architecture audits."""

    audits: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for architecture in FORMAL_ARCHITECTURES:
        name = architecture.value
        path = audit_dir / ARCHITECTURE_FILE_TEMPLATE.format(architecture=name)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_id") != ARCHITECTURE_SCHEMA_ID:
            raise ValueError(f"D41 Gate A {name} schema mismatch")
        if payload.get("architecture") != name:
            raise ValueError(f"D41 Gate A {name} architecture mismatch")
        if payload.get("service_contract_sha256") != SERVICE_SHA256:
            raise ValueError(f"D41 Gate A {name} service hash mismatch")
        if payload.get("d40_gate_a_manifest_sha256") != GATE_A_MANIFEST_SHA256:
            raise ValueError(f"D41 Gate A {name} D40 manifest hash mismatch")
        if payload.get("solver_invoked") is not False:
            raise ValueError(f"D41 Gate A {name} invoked a solver")
        if payload.get("audit", {}).get("passed") is not True:
            raise ValueError(f"D41 Gate A {name} audit failed")
        if payload.get("r0_relaxation", {}).get("passed") is not True:
            raise ValueError(f"D41 Gate A {name} R0 audit failed")
        if payload.get("r1_relaxation", {}).get("passed") is not True:
            raise ValueError(f"D41 Gate A {name} R1 audit failed")
        if (
            payload.get("synthetic_complete_fixing_audit", {}).get("passed")
            is not True
        ):
            raise ValueError(f"D41 Gate A {name} fixing audit failed")
        audits[name] = payload
        hashes[name] = _sha256(path)
    return {
        "schema_id": GATE_A_SCHEMA_ID,
        "status": "gate_a_passed",
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "solver_invoked": False,
        "representative_period_input_used": False,
        "service_contract_sha256": SERVICE_SHA256,
        "d40_gate_a_manifest_sha256": GATE_A_MANIFEST_SHA256,
        "architecture_audit_sha256": hashes,
        "model_size": {
            name: payload["model_size"] for name, payload in audits.items()
        },
        "binary_inventory": {
            name: payload["binary_inventory"]
            for name, payload in audits.items()
        },
        "relaxation_containment": {
            "r0_contains_original_milp": True,
            "r1_contains_original_milp": True,
            "candidate_blocks_provide_formal_bound": False,
            "full_year_repair_required_for_upper_bound": True,
        },
        "provenance": {"code_sha256": _code_hashes()},
        "audit": {"passed": True},
    }


def write_gate_a_manifest(audit_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Write the canonical D41 Gate A manifest and execution references."""

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = compile_gate_a_manifest(audit_dir)
    payload_bytes = _canonical_json_bytes(payload)
    (output_dir / GATE_A_MANIFEST_NAME).write_bytes(payload_bytes)
    executions: dict[str, dict[str, Any]] = {}
    for architecture in FORMAL_ARCHITECTURES:
        name = architecture.value
        path = audit_dir / ARCHITECTURE_EXECUTION_TEMPLATE.format(
            architecture=name
        )
        sidecar = json.loads(path.read_text(encoding="utf-8"))
        expected_manifest = payload["architecture_audit_sha256"][name]
        if sidecar.get("manifest_sha256") != expected_manifest:
            raise ValueError(f"D41 Gate A {name} execution hash mismatch")
        executions[name] = sidecar
    execution_payload = {
        "schema_id": f"{GATE_A_SCHEMA_ID}.execution",
        "architecture_execution": executions,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "manifest_sha256": hashlib.sha256(payload_bytes).hexdigest(),
    }
    _write_json(output_dir / GATE_A_EXECUTION_NAME, execution_payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    audit = commands.add_parser("audit-architecture")
    audit.add_argument(
        "--architecture",
        choices=[item.value for item in FORMAL_ARCHITECTURES],
        required=True,
    )
    audit.add_argument("--service-path", type=Path, required=True)
    audit.add_argument("--gate-a-manifest-path", type=Path, required=True)
    audit.add_argument("--heat-path", type=Path, required=True)
    audit.add_argument("--vre-path", type=Path, required=True)
    audit.add_argument("--price-basis-path", type=Path, required=True)
    audit.add_argument("--output-dir", type=Path, required=True)

    compile_command = commands.add_parser("compile-gate-a")
    compile_command.add_argument("--audit-dir", type=Path, required=True)
    compile_command.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "audit-architecture":
        write_gate_a_architecture_audit(
            Architecture(args.architecture),
            args.service_path,
            args.gate_a_manifest_path,
            args.heat_path,
            args.vre_path,
            args.price_basis_path,
            args.output_dir,
        )
        return
    if args.command == "compile-gate-a":
        write_gate_a_manifest(args.audit_dir, args.output_dir)
        return
    raise AssertionError(f"unhandled command {args.command}")


if __name__ == "__main__":
    main()
