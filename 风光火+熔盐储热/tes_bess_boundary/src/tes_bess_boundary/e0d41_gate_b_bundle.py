"""Compile the immutable E0-D-41 Gate B architecture evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
from typing import Any

from tes_bess_boundary.e0d40_full_year_compute_gate import (
    CLAIM_SCOPE,
    FORMAL_PROJECT_TAC_READY,
    _sha256,
    _write_json,
)
from tes_bess_boundary.e0d41_gate_b_lower_bound import (
    ARCHITECTURE_SCHEMA_ID,
    D41_GATE_A_MANIFEST_SHA256,
)
from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
    GATE_A_SCHEMA_ID,
)
from tes_bess_boundary.model import Architecture


SUMMARY_SCHEMA_ID = "tes_bess_boundary.e0d41_gate_b_bundle.v1"
EXECUTION_SCHEMA_ID = f"{SUMMARY_SCHEMA_ID}.execution"
ARCHITECTURE_ORDER = (
    Architecture.BESS,
    Architecture.TES,
    Architecture.HYBRID,
)


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _load_gate_a(path: Path) -> dict[str, Any]:
    if _sha256(path) != D41_GATE_A_MANIFEST_SHA256:
        raise ValueError("D41 Gate B bundle Gate A hash mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_id") != GATE_A_SCHEMA_ID:
        raise ValueError("D41 Gate B bundle Gate A schema mismatch")
    if payload.get("status") != "gate_a_passed":
        raise ValueError("D41 Gate B bundle requires passed Gate A")
    if payload.get("audit", {}).get("passed") is not True:
        raise ValueError("D41 Gate A audit is not passed")
    return payload


def _load_architecture_manifest(
    result_dir: Path,
    architecture: Architecture,
) -> tuple[dict[str, Any] | None, str | None]:
    path = result_dir / f"gate_b_{architecture.value}_manifest.json"
    if not path.is_file():
        return None, None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_id") != ARCHITECTURE_SCHEMA_ID:
        raise ValueError(f"D41 Gate B {architecture.value} schema mismatch")
    if payload.get("architecture") != architecture.value:
        raise ValueError(f"D41 Gate B {architecture.value} identity mismatch")
    if payload.get("d41_gate_a_manifest_sha256") != D41_GATE_A_MANIFEST_SHA256:
        raise ValueError(f"D41 Gate B {architecture.value} Gate A hash mismatch")
    if payload.get("technical_ranking_permitted") is not False:
        raise ValueError(f"D41 Gate B {architecture.value} ranking flag mismatch")
    if payload.get("representative_period_input_used") is not False:
        raise ValueError(f"D41 Gate B {architecture.value} used representative periods")
    passed = payload.get("gate_b_passed") is True
    expected_status = "gate_b_passed" if passed else "gate_b_failed"
    if payload.get("status") != expected_status:
        raise ValueError(f"D41 Gate B {architecture.value} status mismatch")
    if passed and not isinstance(payload.get("strict_lower_bound_cny"), (int, float)):
        raise ValueError(f"D41 Gate B {architecture.value} lacks a numeric lower bound")
    if not passed and payload.get("strict_lower_bound_cny") is not None:
        raise ValueError(f"failed D41 Gate B {architecture.value} exposes a bound")
    return payload, _sha256(path)


def compile_gate_b_bundle(
    *,
    d41_gate_a_manifest_path: Path,
    result_dir: Path,
) -> dict[str, Any]:
    """Apply the frozen weakest-case and serial-stop rules to Gate B evidence."""

    _load_gate_a(d41_gate_a_manifest_path)
    architectures: dict[str, Any] = {}
    first_nonpass_index: int | None = None
    first_nonpass_architecture: str | None = None
    for index, architecture in enumerate(ARCHITECTURE_ORDER):
        manifest, manifest_hash = _load_architecture_manifest(
            result_dir, architecture
        )
        if manifest is None:
            state = "not_started"
            passed = False
            bound = None
        else:
            passed = manifest["gate_b_passed"] is True
            state = "passed" if passed else "failed"
            bound = manifest.get("strict_lower_bound_cny")
        if not passed and first_nonpass_index is None:
            first_nonpass_index = index
            first_nonpass_architecture = architecture.value
        architectures[architecture.value] = {
            "state": state,
            "gate_b_passed": passed,
            "strict_lower_bound_cny": bound,
            "manifest_sha256": manifest_hash,
        }

    stop_rule_followed = True
    if first_nonpass_index is not None:
        for architecture in ARCHITECTURE_ORDER[first_nonpass_index + 1 :]:
            if architectures[architecture.value]["state"] != "not_started":
                stop_rule_followed = False
    all_passed = all(
        architectures[architecture.value]["gate_b_passed"]
        for architecture in ARCHITECTURE_ORDER
    )
    if not stop_rule_followed:
        raise ValueError("D41 Gate B serial stop rule was violated")
    gate_b_passed = all_passed
    return {
        "schema_id": SUMMARY_SCHEMA_ID,
        "status": "gate_b_passed" if gate_b_passed else "no_strict_certificate",
        "gate_b_passed": gate_b_passed,
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "d41_gate_a_manifest_sha256": D41_GATE_A_MANIFEST_SHA256,
        "architecture_order": [item.value for item in ARCHITECTURE_ORDER],
        "architectures": architectures,
        "weakest_or_first_nonpass_architecture": first_nonpass_architecture,
        "serial_stop_rule_followed": stop_rule_followed,
        "gate_c_permitted": gate_b_passed,
        "gate_d_permitted": False,
        "technical_ranking_permitted": False,
        "representative_period_input_used": False,
        "conclusion": (
            "all_architectures_have_strict_lower_bounds"
            if gate_b_passed
            else "missing_strict_lower_bound_for_at_least_one_architecture"
        ),
    }


def write_gate_b_bundle(
    *,
    d41_gate_a_manifest_path: Path,
    result_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    payload = compile_gate_b_bundle(
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        result_dir=result_dir,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_bytes = _canonical_json_bytes(payload)
    manifest_path = output_dir / "gate_b_manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    source_path = Path(__file__).resolve()
    execution = {
        "schema_id": EXECUTION_SCHEMA_ID,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "compiler_sha256": _sha256(source_path),
        "solver_invoked": False,
    }
    _write_json(output_dir / "gate_b_execution.json", execution)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--d41-gate-a-manifest", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = write_gate_b_bundle(
        d41_gate_a_manifest_path=args.d41_gate_a_manifest,
        result_dir=args.result_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
