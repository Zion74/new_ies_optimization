from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest


def _canonical_dir() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "数据采集"
        / "e0d31_intertemporal_obbt"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_d31_bundle_reproduces_canonical_outputs(tmp_path: Path) -> None:
    from tes_bess_boundary.d31_screening_bundle import write_bundle

    canonical = _canonical_dir()
    generated = tmp_path / "generated"
    result = write_bundle(canonical, generated)

    assert _sha256(result.csv_path) == _sha256(
        canonical / "e0d31_intertemporal_obbt_screening.csv"
    )
    assert _sha256(result.manifest_path) == _sha256(canonical / "manifest.json")
    assert _sha256(result.execution_path) == _sha256(canonical / "execution.json")


def test_d31_bundle_rejects_an_unregistered_336h_global_probe(tmp_path: Path) -> None:
    from tes_bess_boundary.d31_screening_bundle import write_bundle

    source = tmp_path / "source"
    shutil.copytree(_canonical_dir(), source)
    (source / "336h.json").write_text("{}\n", encoding="utf-8", newline="\n")

    with pytest.raises(ValueError, match="must not contain a 336 h global probe"):
        write_bundle(source, tmp_path / "output")


def test_d31_bundle_rejects_a_screen_that_passes_the_materiality_gate(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.d31_screening_bundle import write_bundle

    source = tmp_path / "source"
    shutil.copytree(_canonical_dir(), source)
    path = source / "screen_336h.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["bound_audit"]["positive_width_reduction_vs_d30_fraction"] = 0.02
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match="passes the gate"):
        write_bundle(source, tmp_path / "output")


def test_d31_bundle_rejects_witness_exclusion(tmp_path: Path) -> None:
    from tes_bess_boundary.d31_screening_bundle import write_bundle

    source = tmp_path / "source"
    shutil.copytree(_canonical_dir(), source)
    path = source / "screen_336h.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["known_d19_witness_within_bounds"] = False
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match="excludes the D19 witness"):
        write_bundle(source, tmp_path / "output")
