from __future__ import annotations

import csv
import json
from pathlib import Path


def test_d32_locked_negative_screen_builds_two_row_bundle(tmp_path: Path) -> None:
    from tes_bess_boundary.d32_screening_bundle import (
        D32_BUNDLE_SCHEMA,
        write_d32_bundle,
    )

    source = (
        Path(__file__).resolve().parents[2]
        / "数据采集"
        / "e0d32_joint_block_envelope"
    )
    export = write_d32_bundle(source, tmp_path)

    with export.csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    manifest = json.loads(export.manifest_path.read_text(encoding="utf-8"))

    assert [row["hours"] for row in rows] == ["24", "336"]
    assert rows[0]["exact_24h_equivalence_gate_passed"] == "true"
    assert rows[1]["materiality_gate_passed"] == "false"
    assert rows[1]["global_probe_launched"] == "false"
    assert rows[1]["retained_strict_global_upper_bound_mwh"] == "777141.368858457"
    assert manifest["schema"] == D32_BUNDLE_SCHEMA
    assert manifest["method_contract"]["global_probe_336h_launched"] is False
    assert manifest["scientific_boundaries"]["latest_336h_strict_interval_source"] == "E0-D-30"
