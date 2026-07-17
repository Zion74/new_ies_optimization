from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest


def _canonical_dir() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "数据采集"
        / "e0d30_physics_service_bound_tightening"
    )


def test_d30_bundle_reproduces_canonical_outputs(tmp_path: Path) -> None:
    from tes_bess_boundary.d30_certification_bundle import write_bundle

    canonical = _canonical_dir()
    result = write_bundle(canonical, tmp_path)

    assert result.csv_path.read_bytes() == (
        canonical / "e0d30_physics_service_bound_certificate.csv"
    ).read_bytes()
    assert result.manifest_path.read_bytes() == (
        canonical / "manifest.json"
    ).read_bytes()
    assert result.execution_path.read_bytes() == (
        canonical / "execution.json"
    ).read_bytes()


def test_d30_bundle_rejects_integer_feasible_set_change(tmp_path: Path) -> None:
    from tes_bess_boundary.d30_certification_bundle import write_bundle

    canonical = _canonical_dir()
    fixture = tmp_path / "fixture"
    shutil.copytree(canonical, fixture)
    screen_path = fixture / "screen_24h.json"
    payload = json.loads(screen_path.read_text(encoding="utf-8"))
    payload["bound_audit"]["feasible_set_changed_for_integer_solutions"] = True
    screen_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match="screen audit is inconsistent"):
        write_bundle(fixture, tmp_path / "output")


def test_d30_bundle_rejects_invalid_d29_source_lock(tmp_path: Path) -> None:
    from tes_bess_boundary.d30_certification_bundle import write_bundle

    canonical = _canonical_dir()
    fixture = tmp_path / "fixture"
    shutil.copytree(canonical, fixture)
    probe_path = fixture / "336h.json"
    payload = json.loads(probe_path.read_text(encoding="utf-8"))
    payload["reference_d29_csv_sha256"] = "0" * 64
    probe_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match="D29 CSV source lock mismatch"):
        write_bundle(fixture, tmp_path / "output")
