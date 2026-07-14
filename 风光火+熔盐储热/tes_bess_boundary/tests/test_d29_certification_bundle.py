from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest


def _canonical_bundle() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "数据采集"
        / "e0d29_export_linked_bound_tightening"
    )


def test_d29_bundle_reproduces_canonical_outputs(tmp_path: Path) -> None:
    from tes_bess_boundary.d29_certification_bundle import write_bundle

    canonical = _canonical_bundle()
    exported = write_bundle(canonical / "probes", tmp_path)

    assert exported.csv_path.read_bytes() == (
        canonical / "e0d29_bound_tightening_certificate.csv"
    ).read_bytes()
    assert exported.manifest_path.read_bytes() == (
        canonical / "manifest.json"
    ).read_bytes()
    assert exported.execution_path.read_bytes() == (
        canonical / "execution.json"
    ).read_bytes()


def test_d29_bundle_rejects_integer_feasible_set_change(tmp_path: Path) -> None:
    from tes_bess_boundary.d29_certification_bundle import write_bundle

    probe_dir = tmp_path / "probes"
    shutil.copytree(_canonical_bundle() / "probes", probe_dir)
    target = probe_dir / "336h.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["cut_audit"]["feasible_set_changed_for_integer_solutions"] = True
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match="cut audit"):
        write_bundle(probe_dir, tmp_path / "output")


def test_d29_bundle_rejects_promoted_nonfinite_global_dual(tmp_path: Path) -> None:
    from tes_bess_boundary.d29_certification_bundle import write_bundle

    probe_dir = tmp_path / "probes"
    shutil.copytree(_canonical_bundle() / "probes", probe_dir)
    target = probe_dir / "336h.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["global_dual_is_valid_l1_upper_bound"] = False
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match="global dual"):
        write_bundle(probe_dir, tmp_path / "output")
