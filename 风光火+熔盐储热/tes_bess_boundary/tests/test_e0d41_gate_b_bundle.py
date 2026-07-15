from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gate_a(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import tes_bess_boundary.e0d41_gate_b_bundle as bundle

    path = tmp_path / "gate_a_manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_id": bundle.GATE_A_SCHEMA_ID,
                "status": "gate_a_passed",
                "audit": {"passed": True},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bundle, "D41_GATE_A_MANIFEST_SHA256", _sha(path))
    return path


def _architecture_manifest(
    tmp_path: Path,
    bundle: object,
    name: str,
    *,
    passed: bool,
    lower_bound: float | None,
) -> None:
    payload = {
        "schema_id": bundle.ARCHITECTURE_SCHEMA_ID,
        "architecture": name,
        "d41_gate_a_manifest_sha256": bundle.D41_GATE_A_MANIFEST_SHA256,
        "technical_ranking_permitted": False,
        "representative_period_input_used": False,
        "gate_b_passed": passed,
        "status": "gate_b_passed" if passed else "gate_b_failed",
        "strict_lower_bound_cny": lower_bound,
    }
    (tmp_path / f"gate_b_{name}_manifest.json").write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_bundle_records_bess_pass_tes_failure_and_hybrid_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d41_gate_b_bundle as bundle

    gate_a = _gate_a(tmp_path, monkeypatch)
    _architecture_manifest(
        tmp_path, bundle, "bess", passed=True, lower_bound=100.0
    )
    _architecture_manifest(
        tmp_path, bundle, "tes", passed=False, lower_bound=None
    )

    payload = bundle.compile_gate_b_bundle(
        d41_gate_a_manifest_path=gate_a,
        result_dir=tmp_path,
    )

    assert payload["status"] == "no_strict_certificate"
    assert payload["architectures"]["bess"]["strict_lower_bound_cny"] == 100.0
    assert payload["architectures"]["tes"]["state"] == "failed"
    assert payload["architectures"]["hybrid"]["state"] == "not_started"
    assert payload["serial_stop_rule_followed"] is True
    assert payload["gate_c_permitted"] is False
    assert payload["technical_ranking_permitted"] is False


def test_bundle_rejects_architecture_started_after_prior_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d41_gate_b_bundle as bundle

    gate_a = _gate_a(tmp_path, monkeypatch)
    _architecture_manifest(
        tmp_path, bundle, "bess", passed=True, lower_bound=100.0
    )
    _architecture_manifest(
        tmp_path, bundle, "tes", passed=False, lower_bound=None
    )
    _architecture_manifest(
        tmp_path, bundle, "hybrid", passed=True, lower_bound=110.0
    )

    with pytest.raises(ValueError, match="serial stop rule was violated"):
        bundle.compile_gate_b_bundle(
            d41_gate_a_manifest_path=gate_a,
            result_dir=tmp_path,
        )


def test_bundle_requires_all_three_passes_before_gate_c(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d41_gate_b_bundle as bundle

    gate_a = _gate_a(tmp_path, monkeypatch)
    for index, name in enumerate(("bess", "tes", "hybrid")):
        _architecture_manifest(
            tmp_path,
            bundle,
            name,
            passed=True,
            lower_bound=100.0 + index,
        )

    payload = bundle.compile_gate_b_bundle(
        d41_gate_a_manifest_path=gate_a,
        result_dir=tmp_path,
    )

    assert payload["status"] == "gate_b_passed"
    assert payload["gate_b_passed"] is True
    assert payload["gate_c_permitted"] is True
    assert payload["gate_d_permitted"] is False
