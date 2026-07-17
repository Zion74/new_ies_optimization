from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest


def _canonical_bundle() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "数据采集"
        / "e0d28_multistart_direction"
    )


def test_d28_bundle_reproduces_canonical_outputs(tmp_path: Path) -> None:
    from tes_bess_boundary.d28_multistart_bundle import write_bundle

    canonical = _canonical_bundle()
    exported = write_bundle(canonical / "probes", tmp_path)

    assert exported.csv_path.read_bytes() == (
        canonical / "e0d28_multistart_screening.csv"
    ).read_bytes()
    assert exported.manifest_path.read_bytes() == (
        canonical / "manifest.json"
    ).read_bytes()
    assert exported.execution_path.read_bytes() == (
        canonical / "execution.json"
    ).read_bytes()


def test_d28_bundle_rejects_support_dual_promoted_to_global(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.d28_multistart_bundle import write_bundle

    probe_dir = tmp_path / "probes"
    shutil.copytree(_canonical_bundle() / "probes", probe_dir)
    target = probe_dir / "336h_negated.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["support_dual_is_global_l1_upper_bound"] = True
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match="global-bound boundary"):
        write_bundle(probe_dir, tmp_path / "output")


def test_d28_bundle_rejects_inconsistent_best_witness(tmp_path: Path) -> None:
    from tes_bess_boundary.d28_multistart_bundle import write_bundle

    probe_dir = tmp_path / "probes"
    shutil.copytree(_canonical_bundle() / "probes", probe_dir)
    target = probe_dir / "336h_alternating.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["best_feasible_l1_redistribution_mwh"] = 1.0
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match="best witness"):
        write_bundle(probe_dir, tmp_path / "output")
