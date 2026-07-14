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
        / "e0d26_numerical_certification"
    )


def test_d26_bundle_reproduces_canonical_outputs(tmp_path: Path) -> None:
    from tes_bess_boundary.d26_certification_bundle import write_bundle

    canonical = _canonical_bundle()
    exported = write_bundle(canonical / "probes", tmp_path)

    assert exported.csv_path.read_bytes() == (
        canonical / "e0d26_numerical_certification.csv"
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
    for name, expected_hash in manifest["probes"].items():
        assert expected_hash == hashlib.sha256(
            (canonical / "probes" / name).read_bytes()
        ).hexdigest()


def test_d26_bundle_rejects_a_reopened_result_worse_than_its_witness(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.d26_certification_bundle import write_bundle

    probe_dir = tmp_path / "probes"
    shutil.copytree(_canonical_bundle() / "probes", probe_dir)
    target = probe_dir / "24h_reopened_min.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["primal_bound_mwh"] = (
        float(payload["conditional_face_warm_start_mwh"]) + 1.0
    )
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match="worse than its witness"):
        write_bundle(probe_dir, tmp_path / "output")
