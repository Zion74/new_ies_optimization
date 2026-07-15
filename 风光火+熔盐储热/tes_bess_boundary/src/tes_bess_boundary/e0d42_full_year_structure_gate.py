"""E0-D-42 build-only full-year LP identity and branch-coverage gate.

This module does not optimize a formal case.  Each CLI invocation rebuilds one
locked D40/D41 8784-hour model, applies one D41 relaxation, translates it to a
native ``HighsLp``, runs exactly one explicit HiGHS presolve, and writes the two
LP fingerprints.  The compiler then proves that TES R0/R1 are identical and
that Hybrid R1 is exhausted by the two exact values of ``bess.installed``.
"""

from __future__ import annotations

import argparse
import json
import platform
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from tes_bess_boundary.e0d40_full_year_compute_gate import (
    CLAIM_SCOPE,
    FORMAL_PROJECT_TAC_READY,
    _available_memory_gib,
    _linearity_audit,
    _peak_rss_gib,
    _sha256,
    _tree_sha256,
    _write_json,
)
from tes_bess_boundary.e0d40_gate_b_solver import (
    GATE_A_MANIFEST_SHA256,
    SERVICE_SHA256,
    _build_gate_b_model,
)
from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
    RelaxationMode,
    apply_relaxation,
    collect_binary_inventory,
)
from tes_bess_boundary.e0d42_native_highs_certificate import (
    SUPPORTED_HIGHS_VERSION,
    explicit_presolve,
    translate_pyomo_model,
)
from tes_bess_boundary.model import Architecture


CASE_SCHEMA_ID = "tes_bess_boundary.e0d42_structure_case.v1"
MANIFEST_SCHEMA_ID = "tes_bess_boundary.e0d42_structure_manifest.v1"
EXECUTION_SCHEMA_ID = "tes_bess_boundary.e0d42_structure_execution.v1"
D41_GATE_A_MANIFEST_SHA256 = (
    "50240e7ae557afa5633b29904585f1c1297a527343e467ce76d7766ce0177937"
)
CASE_FILE_TEMPLATE = "structure_{case_key}.json"
MANIFEST_NAME = "structure_manifest.json"
EXECUTION_NAME = "structure_execution.json"
HYBRID_TOPOLOGY_NAME = "bess.installed"


@dataclass(frozen=True)
class StructureCase:
    key: str
    architecture: Architecture
    mode: RelaxationMode
    topology_value: int | None = None


STRUCTURE_CASES = (
    StructureCase("tes_r0", Architecture.TES, RelaxationMode.R0),
    StructureCase("tes_r1", Architecture.TES, RelaxationMode.R1),
    StructureCase("hybrid_r0", Architecture.HYBRID, RelaxationMode.R0),
    StructureCase(
        "hybrid_r1_bess0",
        Architecture.HYBRID,
        RelaxationMode.R1,
        0,
    ),
    StructureCase(
        "hybrid_r1_bess1",
        Architecture.HYBRID,
        RelaxationMode.R1,
        1,
    ),
)
_CASES_BY_KEY = {case.key: case for case in STRUCTURE_CASES}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    names = (
        "e0d42_full_year_structure_gate.py",
        "e0d42_native_highs_certificate.py",
        "e0d41_strict_full_year_decomposition.py",
        "e0d40_gate_b_solver.py",
        "e0d40_full_year_compute_gate.py",
        "planning_model.py",
    )
    return {name: _sha256(package / name) for name in names}


def _presolve_status_eligible(status: str) -> bool:
    return status.endswith(("kReduced", "kNotReduced", "kReducedToEmpty"))


def _input_hashes(
    *,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, str]:
    return {
        "service": _sha256(service_path),
        "d40_gate_a_manifest": _sha256(d40_gate_a_manifest_path),
        "d41_gate_a_manifest": _sha256(d41_gate_a_manifest_path),
        "heat": _sha256(heat_path),
        "vre": _sha256(vre_path),
        "price_basis_tree": _tree_sha256(price_basis_path),
    }


def audit_relaxed_model_lp(
    model: object,
    *,
    mode: RelaxationMode,
    topology_value: int | None,
) -> dict[str, Any]:
    """Audit one already-built model through relaxation, translation and presolve."""

    from pyomo import version as pyomo_version
    from pyomo.environ import UnitInterval

    inventory = collect_binary_inventory(model)
    relaxation = apply_relaxation(model, inventory, mode)
    topology_names = inventory.topology_names

    if mode is RelaxationMode.R0:
        if topology_value is not None:
            raise ValueError("R0 does not accept a topology branch value")
        if relaxation["remaining_binary_variable_count"] != 0:
            raise ValueError("R0 must relax every binary variable")
    elif topology_names:
        if topology_names != (HYBRID_TOPOLOGY_NAME,):
            raise ValueError(
                "D42 only permits the locked Hybrid topology binary "
                f"{HYBRID_TOPOLOGY_NAME}"
            )
        if topology_value not in {0, 1}:
            raise ValueError("Hybrid R1 requires topology_value 0 or 1")
        variable = model.find_component(HYBRID_TOPOLOGY_NAME)
        if variable is None:
            raise ValueError("locked Hybrid topology variable is missing")
        variable.fix(topology_value)
        variable.domain = UnitInterval
    elif topology_value is not None:
        raise ValueError("a topology-free R1 model does not accept a branch value")

    linearity = _linearity_audit(model)
    if linearity["nonlinear_component_count"] != 0:
        raise ValueError("D42 structure case is not linear")
    if linearity["active_binary_variable_count"] != 0:
        raise ValueError("D42 structure case did not become a continuous LP")

    translate_started = perf_counter()
    translation = translate_pyomo_model(model)
    translate_seconds = perf_counter() - translate_started
    if translation.audit["highs_version"] != SUPPORTED_HIGHS_VERSION:
        raise ValueError("D42 HiGHS version differs from the locked version")
    if translation.audit["noncontinuous_column_count"] != 0:
        raise ValueError("translated D42 model contains an integer column")

    presolve_started = perf_counter()
    presolved = explicit_presolve(translation.lp)
    presolve_seconds = perf_counter() - presolve_started
    if presolved.audit["highs_version"] != SUPPORTED_HIGHS_VERSION:
        raise ValueError("D42 presolve used an unsupported HiGHS version")
    if presolved.audit["noncontinuous_column_count"] != 0:
        raise ValueError("presolved D42 model contains an integer column")

    presolve_eligible = _presolve_status_eligible(
        presolved.audit["presolve_status"]
    )
    passed = bool(
        relaxation["passed"]
        and translation.audit["passed"]
        and presolved.audit["passed"]
        and presolve_eligible
    )
    return {
        "binary_inventory": inventory.to_audit(),
        "relaxation": relaxation,
        "topology_branch": {
            "variable_name": (
                HYBRID_TOPOLOGY_NAME if topology_value is not None else None
            ),
            "fixed_value": topology_value,
            "exact_fix_applied_before_domain_relaxation": (
                topology_value is not None
            ),
        },
        "linearity_after_branch_fix": linearity,
        "original_lp": translation.audit,
        "presolved_lp": presolved.audit,
        "software": {
            "python": platform.python_version(),
            "pyomo": pyomo_version.__version__,
            "highs": translation.audit["highs_version"],
        },
        "timing_seconds": {
            "translate": translate_seconds,
            "presolve": presolve_seconds,
        },
        "optimization_invoked": False,
        "presolve_invoked": True,
        "audit": {"passed": passed},
    }


def build_full_year_structure_case(
    case_key: str,
    *,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    """Build and fingerprint one locked formal D42 structure case."""

    if case_key not in _CASES_BY_KEY:
        raise ValueError(f"unknown D42 structure case: {case_key}")
    case_spec = _CASES_BY_KEY[case_key]
    if _sha256(service_path) != SERVICE_SHA256:
        raise ValueError("D42 service contract hash mismatch")
    if _sha256(d40_gate_a_manifest_path) != GATE_A_MANIFEST_SHA256:
        raise ValueError("D42 D40 Gate A manifest hash mismatch")
    if _sha256(d41_gate_a_manifest_path) != D41_GATE_A_MANIFEST_SHA256:
        raise ValueError("D42 D41 Gate A manifest hash mismatch")
    d41_manifest = _load_json(d41_gate_a_manifest_path)
    if d41_manifest.get("audit", {}).get("passed") is not True:
        raise ValueError("D42 requires a passing D41 Gate A manifest")

    build_started = perf_counter()
    _case, model, model_size = _build_gate_b_model(
        case_spec.architecture,
        service_path,
        d40_gate_a_manifest_path,
        heat_path,
        vre_path,
        price_basis_path,
    )
    build_seconds = perf_counter() - build_started
    expected_size = d41_manifest["model_size"][case_spec.architecture.value]
    if model_size != expected_size:
        raise ValueError("D42 model size differs from the locked D41 model")
    current_inventory = collect_binary_inventory(model).to_audit()
    expected_inventory = d41_manifest["binary_inventory"][
        case_spec.architecture.value
    ]
    if current_inventory != expected_inventory:
        raise ValueError("D42 binary inventory differs from the locked D41 model")

    lp_audit = audit_relaxed_model_lp(
        model,
        mode=case_spec.mode,
        topology_value=case_spec.topology_value,
    )
    passed = bool(lp_audit["audit"]["passed"])
    return {
        "schema_id": CASE_SCHEMA_ID,
        "status": "structure_case_passed" if passed else "structure_case_failed",
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "case_key": case_spec.key,
        "architecture": case_spec.architecture.value,
        "relaxation_mode": case_spec.mode.value,
        "topology_value": case_spec.topology_value,
        "model_size": model_size,
        "d41_structure_lock": {
            "model_size_matches": model_size == expected_size,
            "binary_inventory_matches": current_inventory == expected_inventory,
        },
        "lp_identity_audit": lp_audit,
        "input_sha256": _input_hashes(
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        ),
        "provenance": {"code_sha256": _code_hashes()},
        "timing_seconds": {
            "model_build": build_seconds,
            **lp_audit["timing_seconds"],
        },
        "resource": {
            "process_peak_rss_gib": _peak_rss_gib(),
            "available_memory_gib_after": _available_memory_gib(),
        },
        "optimization_invoked": False,
        "presolve_invoked": True,
        "audit": {"passed": passed},
    }


def write_full_year_structure_case(
    case_key: str,
    *,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_full_year_structure_case(
        case_key,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    path = output_dir / CASE_FILE_TEMPLATE.format(case_key=case_key)
    _write_json(path, payload)
    if payload["audit"]["passed"] is not True:
        raise RuntimeError(f"D42 structure case failed: {case_key}")
    return payload


def compile_structure_manifest(audit_dir: Path) -> dict[str, Any]:
    """Compile the five clean-process audits and enforce D42 Gate A locks."""

    payloads: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for case in STRUCTURE_CASES:
        path = audit_dir / CASE_FILE_TEMPLATE.format(case_key=case.key)
        if not path.is_file():
            raise FileNotFoundError(f"missing D42 structure case: {path}")
        payload = _load_json(path)
        if payload.get("schema_id") != CASE_SCHEMA_ID:
            raise ValueError(f"D42 schema mismatch: {case.key}")
        if payload.get("case_key") != case.key:
            raise ValueError(f"D42 case key mismatch: {case.key}")
        if payload.get("architecture") != case.architecture.value:
            raise ValueError(f"D42 architecture mismatch: {case.key}")
        if payload.get("relaxation_mode") != case.mode.value:
            raise ValueError(f"D42 relaxation mode mismatch: {case.key}")
        if payload.get("topology_value") != case.topology_value:
            raise ValueError(f"D42 topology value mismatch: {case.key}")
        if payload.get("audit", {}).get("passed") is not True:
            raise ValueError(f"D42 structure case did not pass: {case.key}")
        if payload.get("optimization_invoked") is not False:
            raise ValueError(f"D42 structure case optimized unexpectedly: {case.key}")
        if payload.get("presolve_invoked") is not True:
            raise ValueError(f"D42 structure case skipped presolve: {case.key}")
        structure_lock = payload.get("d41_structure_lock", {})
        if (
            structure_lock.get("model_size_matches") is not True
            or structure_lock.get("binary_inventory_matches") is not True
        ):
            raise ValueError(f"D42 D41 structure lock failed: {case.key}")
        payloads[case.key] = payload
        hashes[case.key] = _sha256(path)

    input_locks = [payload["input_sha256"] for payload in payloads.values()]
    if any(lock != input_locks[0] for lock in input_locks[1:]):
        raise ValueError("D42 structure cases do not share identical input locks")

    tes_r0 = payloads["tes_r0"]["lp_identity_audit"]
    tes_r1 = payloads["tes_r1"]["lp_identity_audit"]
    tes_original_equal = (
        tes_r0["original_lp"]["lp_sha256"]
        == tes_r1["original_lp"]["lp_sha256"]
    )
    tes_presolved_equal = (
        tes_r0["presolved_lp"]["presolved_lp_sha256"]
        == tes_r1["presolved_lp"]["presolved_lp_sha256"]
    )
    if not tes_original_equal or not tes_presolved_equal:
        raise ValueError("D42 TES R0/R1 LP fingerprints differ")

    hybrid_branches = {
        payloads[key]["lp_identity_audit"]["topology_branch"]["fixed_value"]
        for key in ("hybrid_r1_bess0", "hybrid_r1_bess1")
    }
    hybrid_names = {
        payloads[key]["lp_identity_audit"]["topology_branch"]["variable_name"]
        for key in ("hybrid_r1_bess0", "hybrid_r1_bess1")
    }
    if hybrid_branches != {0, 1} or hybrid_names != {HYBRID_TOPOLOGY_NAME}:
        raise ValueError("D42 Hybrid R1 branch coverage is incomplete")

    continuous = all(
        payload["lp_identity_audit"]["original_lp"][
            "noncontinuous_column_count"
        ]
        == 0
        and payload["lp_identity_audit"]["presolved_lp"][
            "noncontinuous_column_count"
        ]
        == 0
        for payload in payloads.values()
    )
    if not continuous:
        raise ValueError("D42 structure manifest contains a noncontinuous LP")

    return {
        "schema_id": MANIFEST_SCHEMA_ID,
        "status": "gate_a_structure_passed",
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "case_sha256": hashes,
        "input_sha256": input_locks[0],
        "tes_r0_r1_identity": {
            "original_lp_fingerprint_equal": tes_original_equal,
            "presolved_lp_fingerprint_equal": tes_presolved_equal,
            "original_lp_sha256": tes_r0["original_lp"]["lp_sha256"],
            "presolved_lp_sha256": tes_r0["presolved_lp"][
                "presolved_lp_sha256"
            ],
        },
        "hybrid_r1_branch_coverage": {
            "topology_variable": HYBRID_TOPOLOGY_NAME,
            "fixed_values": sorted(hybrid_branches),
            "complete": True,
        },
        "all_native_models_continuous": continuous,
        "optimization_invoked": False,
        "presolve_invoked": True,
        "formal_gate_b_permitted": True,
        "technical_ranking_permitted": False,
        "audit": {"passed": True},
    }


def write_structure_manifest(audit_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    payload = compile_structure_manifest(audit_dir)
    manifest_path = output_dir / MANIFEST_NAME
    _write_json(manifest_path, payload)
    execution = {
        "schema_id": EXECUTION_SCHEMA_ID,
        "status": payload["status"],
        "manifest_sha256": _sha256(manifest_path),
        "runtime_seconds": perf_counter() - started,
        "optimization_invoked": False,
        "audit": {"passed": True},
    }
    _write_json(output_dir / EXECUTION_NAME, execution)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    audit = commands.add_parser("audit-case")
    audit.add_argument("--case-key", choices=tuple(_CASES_BY_KEY), required=True)
    audit.add_argument("--service-path", type=Path, required=True)
    audit.add_argument("--d40-gate-a-manifest-path", type=Path, required=True)
    audit.add_argument("--d41-gate-a-manifest-path", type=Path, required=True)
    audit.add_argument("--heat-path", type=Path, required=True)
    audit.add_argument("--vre-path", type=Path, required=True)
    audit.add_argument("--price-basis-path", type=Path, required=True)
    audit.add_argument("--output-dir", type=Path, required=True)

    compile_command = commands.add_parser("compile")
    compile_command.add_argument("--audit-dir", type=Path, required=True)
    compile_command.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "audit-case":
        write_full_year_structure_case(
            args.case_key,
            service_path=args.service_path,
            d40_gate_a_manifest_path=args.d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=args.d41_gate_a_manifest_path,
            heat_path=args.heat_path,
            vre_path=args.vre_path,
            price_basis_path=args.price_basis_path,
            output_dir=args.output_dir,
        )
        return
    if args.command == "compile":
        write_structure_manifest(args.audit_dir, args.output_dir)
        return
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    main()
