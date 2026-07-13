from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path

import pytest


pytestmark = [
    pytest.mark.solver,
    pytest.mark.integration,
    pytest.mark.data_integration,
]


def _formal_data_dir() -> Path:
    configured = os.environ.get("TES_BESS_E0B_FORMAL_DIR")
    if configured:
        return Path(configured)
    package_root = Path(__file__).resolve().parents[1]
    return package_root.parent / "数据采集" / "e0b_formal_2024"


def test_heat_bridge_writes_six_canonical_diagnostics_and_a_runtime_sidecar(
    tmp_path,
) -> None:
    from dataclasses import replace

    from tes_bess_boundary.heat_bridge import (
        run_e0c_heat_bridge_diagnostics,
        write_e0c_heat_bridge_diagnostics,
    )

    formal_dir = _formal_data_dir()
    run = run_e0c_heat_bridge_diagnostics(
        formal_dir / "e0b_heat_hourly_2024.csv",
        source_manifest=formal_dir / "manifest.json",
        adapter_output_dir=tmp_path / "window_adapters",
    )

    assert len(run.records) == 6
    assert all(record.termination == "optimal" for record in run.records)
    assert all(
        record.mip_gap == pytest.approx(0.0, abs=1e-12) for record in run.records
    )
    zero_record = next(
        record
        for record in run.records
        if record.window_id == "zero_segment_core_20241011"
        and record.interpretation == "zero_sensitivity_clipped"
    )
    assert zero_record.heat_energy_mwh == pytest.approx(1_872.258101851853)
    assert zero_record.heat_peak_mw == pytest.approx(87.315740740741)
    assert zero_record.fuel_tce == pytest.approx(852.127253672083)
    assert zero_record.pcc_export_mwh == pytest.approx(2_250.992757772414)

    first = write_e0c_heat_bridge_diagnostics(run, tmp_path / "first")
    second = write_e0c_heat_bridge_diagnostics(run, tmp_path / "second")

    assert first.csv_path.read_bytes() == second.csv_path.read_bytes()
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()
    assert b"\r\n" not in first.manifest_path.read_bytes()
    assert b"\r\n" not in first.execution_metadata_path.read_bytes()
    assert (
        first.canonical_output_sha256[first.csv_path.name]
        == hashlib.sha256(first.csv_path.read_bytes()).hexdigest()
    )
    assert (
        first.canonical_output_sha256[first.manifest_path.name]
        == hashlib.sha256(first.manifest_path.read_bytes()).hexdigest()
    )
    golden_directory = tmp_path / "golden"
    golden = write_e0c_heat_bridge_diagnostics(
        replace(run, adapter_output_dir=golden_directory / "windows"),
        golden_directory,
    )
    assert golden.canonical_output_sha256 == {
        "e0c_heat_bridge_diagnostics_2024.csv": (
            "502a72db115eb50c69077f0b458d4726034b4d00b5226a373c99e8113edd6ed6"
        ),
        "e0c_heat_bridge_diagnostics_2024.manifest.json": (
            "6fc0d94dc6f20eb9322237e0f3cc5a300beb7604f1832d99130ba76dc2eb7f33"
        ),
    }

    with first.csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 6
    assert {row["window_role"] for row in rows} == {
        "negative_hour_contract",
        "zero_segment_contract",
    }
    assert {row["architecture"] for row in rows} == {"no_storage"}
    assert {row["low_load_fuel_rule"] for row in rows} == {"clamp_30_percent_rate"}
    assert {row["transition_proxy_mode"] for row in rows} == {"omitted"}
    assert all(row["adapter_csv_sha256"] for row in rows)

    canonical_manifest_text = first.manifest_path.read_text(encoding="utf-8")
    assert "runtime_seconds" not in canonical_manifest_text
    manifest = json.loads(canonical_manifest_text)
    assert manifest["schema"] == "tes_bess_boundary.e0c_heat_bridge.v1"
    assert manifest["scientific_scope"] == (
        "orthogonal_input_and_physical_bridge_diagnostic_not_e1"
    )
    assert manifest["output"]["rows"] == 6
    assert (
        manifest["output"]["csv_sha256"]
        == first.canonical_output_sha256[first.csv_path.name]
    )
    assert all(
        item["csv"].startswith("../window_adapters/")
        and item["manifest"].startswith("../window_adapters/")
        for item in manifest["adapter_outputs"]
    )

    execution = json.loads(first.execution_metadata_path.read_text(encoding="utf-8"))
    assert execution["schema"] == ("tes_bess_boundary.e0c_heat_bridge_execution.v1")
    assert len(execution["solves"]) == 6
    assert all(item["runtime_seconds"] >= 0.0 for item in execution["solves"])
    assert (
        first.execution_metadata_sha256
        == hashlib.sha256(first.execution_metadata_path.read_bytes()).hexdigest()
    )
