from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest


def _canonical_bundle() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "数据采集"
        / "e0d27_direction_generation"
    )


def test_d27_bundle_reproduces_canonical_outputs(tmp_path: Path) -> None:
    from tes_bess_boundary.d27_certification_bundle import write_bundle

    canonical = _canonical_bundle()
    exported = write_bundle(canonical / "probes", tmp_path)

    assert exported.csv_path.read_bytes() == (
        canonical / "e0d27_numerical_certificate.csv"
    ).read_bytes()
    assert exported.manifest_path.read_bytes() == (
        canonical / "manifest.json"
    ).read_bytes()
    assert exported.execution_path.read_bytes() == (
        canonical / "execution.json"
    ).read_bytes()
    manifest = json.loads(exported.manifest_path.read_text(encoding="utf-8"))
    assert manifest["execution_sidecar"]["sha256"] == hashlib.sha256(
        exported.execution_path.read_bytes()
    ).hexdigest()


def test_d27_bundle_rejects_support_dual_promoted_to_global(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.d27_certification_bundle import write_bundle

    probe_dir = tmp_path / "probes"
    shutil.copytree(_canonical_bundle() / "probes", probe_dir)
    target = probe_dir / "336h_support_final.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["support_dual_is_global_l1_upper_bound"] = True
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match="crosses the global boundary"):
        write_bundle(probe_dir, tmp_path / "output")


def test_d27_bundle_rejects_global_bound_below_support_witness(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.d27_certification_bundle import write_bundle

    probe_dir = tmp_path / "probes"
    shutil.copytree(_canonical_bundle() / "probes", probe_dir)
    target = probe_dir / "336h_global.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["disaggregated_global"]["dual_bound_mwh"] = 1.0
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match="below its incumbent|does not dominate"):
        write_bundle(probe_dir, tmp_path / "output")
