from __future__ import annotations

import json
from pathlib import Path

import pytest


def _canonical_write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_load_locked_structure_case_uses_downloaded_gate_a_hash_chain() -> None:
    from tes_bess_boundary.e0d42_gate_b_formal import load_locked_structure_case

    project_dir = Path(__file__).resolve().parents[1]
    structure_dir = (
        project_dir.parent
        / "数据采集"
        / "e0d42_native_highs_lagrangian_bound"
    )
    manifest, case = load_locked_structure_case(structure_dir, "tes_r0")

    assert manifest["formal_gate_b_permitted"] is True
    assert case["case_key"] == "tes_r0"
    assert (
        case["lp_identity_audit"]["presolved_lp"]["presolved_lp_sha256"]
        == "c2049cacd4b32aef3206998d2d47e792c4ad024aa72c80eaba9722b312fa5da5"
    )


def test_locked_hybrid_relaxation_fixes_only_the_complete_topology_branch() -> None:
    from pyomo.environ import Binary, Block, ConcreteModel, Var

    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
    )
    from tes_bess_boundary.e0d42_gate_b_formal import (
        FormalCase,
        _apply_locked_case_relaxation,
    )
    from tes_bess_boundary.model import Architecture

    model = ConcreteModel()
    model.bess = Block()
    model.bess.installed = Var(domain=Binary)
    model.dispatch_on = Var(domain=Binary)
    spec = FormalCase(
        "hybrid_r1_bess1",
        Architecture.HYBRID,
        RelaxationMode.R1,
        1,
    )

    inventory, relaxation = _apply_locked_case_relaxation(model, spec)

    assert inventory["topology_binary_variable_count"] == 1
    assert inventory["operational_binary_variable_count"] == 1
    assert relaxation["remaining_binary_variable_count"] == 1
    assert model.bess.installed.fixed is True
    assert model.bess.installed.value == 1
    assert model.bess.installed.is_binary() is False
    assert model.dispatch_on.is_binary() is False


def test_bess_and_tes_prerequisites_require_parent_execution_hashes(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    from tes_bess_boundary.e0d42_gate_b_formal import (
        BESS_REUSE_EXECUTION_SCHEMA_ID,
        BESS_REUSE_SCHEMA_ID,
        CASE_EXECUTION_SCHEMA_ID,
        CASE_MANIFEST_SCHEMA_ID,
        _load_bess_prerequisite,
        _load_tes_prerequisite,
    )

    bess_path = tmp_path / "bess_reuse_result.json"
    _canonical_write(
        bess_path,
        {
            "schema_id": BESS_REUSE_SCHEMA_ID,
            "status": "bess_d41_bound_reuse_passed",
            "formal_lower_bound_eligible": True,
            "optimization_invoked": False,
            "audit": {"passed": True},
        },
    )
    _canonical_write(
        tmp_path / "bess_reuse_execution.json",
        {
            "schema_id": BESS_REUSE_EXECUTION_SCHEMA_ID,
            "status": "complete",
            "return_code": 0,
            "resource_gate_passed": True,
            "stop_reason": None,
            "hard_wall_enforced_by_parent": True,
            "result_sha256": _sha256(bess_path),
        },
    )
    assert _load_bess_prerequisite(bess_path)["audit"]["passed"] is True

    tes_path = tmp_path / "case_manifest.json"
    _canonical_write(
        tes_path,
        {
            "schema_id": CASE_MANIFEST_SCHEMA_ID,
            "status": "certified_finite_lower_bound",
            "case_key": "tes_r0",
            "formal_lower_bound_eligible": True,
        },
    )
    _canonical_write(
        tmp_path / "case_execution.json",
        {
            "schema_id": CASE_EXECUTION_SCHEMA_ID,
            "status": "certified_finite_lower_bound",
            "case_key": "tes_r0",
            "case_manifest_sha256": _sha256(tes_path),
        },
    )
    assert _load_tes_prerequisite(tes_path)["case_key"] == "tes_r0"

    payload = json.loads(bess_path.read_text(encoding="utf-8"))
    payload["audit"] = {"passed": False}
    _canonical_write(bess_path, payload)
    with pytest.raises(ValueError, match="not eligible"):
        _load_bess_prerequisite(bess_path)


def test_hybrid_manifest_applies_min_branches_then_max_relaxations(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d42_gate_b_formal import (
        CASE_MANIFEST_SCHEMA_ID,
        compile_hybrid_manifest,
    )

    paths: dict[str, Path] = {}
    for key, bound, status in (
        ("hybrid_r0", "100.0000000000000001", "certified_optimal_relaxation"),
        ("hybrid_r1_bess0", "90.25", "certified_optimal_relaxation"),
        ("hybrid_r1_bess1", "110.75", "certified_finite_lower_bound"),
    ):
        path = tmp_path / f"{key}.json"
        _canonical_write(
            path,
            {
                "schema_id": CASE_MANIFEST_SCHEMA_ID,
                "status": status,
                "case_key": key,
                "formal_lower_bound_eligible": True,
                "formal_lower_bound_decimal": bound,
                "formal_lower_bound_float": float(bound),
            },
        )
        paths[key] = path

    manifest = compile_hybrid_manifest(
        hybrid_r0_path=paths["hybrid_r0"],
        hybrid_r1_bess0_path=paths["hybrid_r1_bess0"],
        hybrid_r1_bess1_path=paths["hybrid_r1_bess1"],
    )

    assert manifest["hybrid_r1_lower_bound_decimal"] == "90.25"
    assert manifest["formal_lower_bound_decimal"] == "100.0000000000000001"
    assert manifest["status"] == "certified_finite_lower_bound"
    assert manifest["technical_ranking_permitted"] is False


def test_formal_parser_exposes_only_registered_case_keys() -> None:
    from tes_bess_boundary.e0d42_gate_b_formal import (
        FORMAL_CASE_BY_KEY,
        build_parser,
    )

    assert tuple(FORMAL_CASE_BY_KEY) == (
        "tes_r0",
        "hybrid_r0",
        "hybrid_r1_bess0",
        "hybrid_r1_bess1",
    )
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run-case", "--case-key", "tes_r1"])
