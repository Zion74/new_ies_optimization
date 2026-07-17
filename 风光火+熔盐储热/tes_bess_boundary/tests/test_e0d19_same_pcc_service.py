from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest


@pytest.mark.solver
@pytest.mark.integration
def test_real_24h_same_pcc_service_contract_closes_flat_settlement(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d17_exploration import DEFAULT_WINDOWS
    from tes_bess_boundary.pcc_settlement_exposure import (
        E0D22_SCHEMA,
        run_e0d22,
        write_e0d22,
    )

    package_root = Path(__file__).resolve().parents[1]
    data_root = package_root.parent / "数据采集"
    configured_formal_dir = os.environ.get("TES_BESS_E0B_FORMAL_DIR")
    formal_dir = (
        Path(configured_formal_dir)
        if configured_formal_dir
        else data_root / "e0b_formal_2024"
    )
    d22_run = run_e0d22(
        formal_dir / "e0b_heat_hourly_2024.csv",
        data_root / "口径3_统一数据集_2024.csv",
        windows=DEFAULT_WINDOWS[:1],
    )

    record = d22_run.d19_run.records[0]
    assert record.scientific_status == "exact_24h_same_pcc_service_diagnostic"
    assert record.candidate_primary_mip_gap == pytest.approx(0.0, abs=1e-12)
    assert record.secondary_curtailment_mip_gap == pytest.approx(0.0, abs=1e-12)
    assert record.pcc_export_difference_mwh == pytest.approx(0.0, abs=1e-6)
    assert record.flat_price_settlement_difference_cny_per_year == 0.0
    assert record.candidate_service_feasibility_warm_start is False
    assert record.candidate_service_feasibility_deviation_mw is None
    assert record.fuel_saving_tce == pytest.approx(16_099.093175, abs=1e-5)
    assert record.tes_ownership_eac_lower_bound_cny_per_year == pytest.approx(
        record.comparator_primary_cost_cny - record.candidate_audited_cost_cny,
        abs=1e-8,
    )
    assert record.candidate_audited_cost_cny <= (
        record.candidate_primary_primal_bound_cny
        + record.candidate_primary_cost_tolerance_cny
        + 1e-4
    )
    assert record.tes_ownership_eac_lower_bound_cny_per_year == pytest.approx(
        12_893_119.760015,
        abs=1e-4,
    )
    assert record.tes_ownership_eac_upper_bound_cny_per_year == pytest.approx(
        record.tes_ownership_eac_lower_bound_cny_per_year,
        abs=1e-8,
    )
    assert len(d22_run.d19_run.pcc_traces) == 24
    exposure = d22_run.exposures[0]
    assert exposure.window_id == record.window_id
    assert exposure.comparator_pcc_export_mwh == pytest.approx(
        record.comparator_pcc_export_mwh, abs=1e-5
    )
    assert exposure.candidate_pcc_export_mwh == pytest.approx(
        record.candidate_pcc_export_mwh, abs=1e-5
    )
    assert exposure.annual_export_difference_mwh == pytest.approx(0.0, abs=1e-5)
    assert exposure.redistributed_export_mwh > 0.0
    assert exposure.flat_price_settlement_difference_cny_per_year == 0.0
    assert exposure.time_varying_settlement_complete is False
    assert exposure.trace_solution_uniqueness_proven is False

    source_dir = data_root / "e0d19_same_pcc_service"
    first = write_e0d22(
        d22_run,
        tmp_path / "first",
        d19_source_dir=source_dir,
    )
    second = write_e0d22(
        d22_run,
        tmp_path / "second",
        d19_source_dir=source_dir,
    )
    for first_path, second_path in (
        (first.trace_csv_path, second.trace_csv_path),
        (first.exposure_csv_path, second.exposure_csv_path),
        (first.manifest_path, second.manifest_path),
    ):
        assert first_path.read_bytes() == second_path.read_bytes()
        assert b"\r\n" not in first_path.read_bytes()
        assert first.canonical_sha256[first_path.name] == hashlib.sha256(
            first_path.read_bytes()
        ).hexdigest()
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == E0D22_SCHEMA
    assert manifest["scientific_boundary"] == {
        "actual_price_path_assigned": False,
        "e1_ready": False,
        "flat_price_settlement_complete": True,
        "formal_tac": False,
        "time_varying_settlement_complete": False,
        "trace_solution_uniqueness_proven": False,
    }

    tampered_source = tmp_path / "tampered_d19"
    tampered_source.mkdir()
    for name in ("e0d19_same_pcc_service.csv", "manifest.json"):
        shutil.copy2(source_dir / name, tampered_source / name)
    with (tampered_source / "e0d19_same_pcc_service.csv").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="D19 CSV hash"):
        write_e0d22(
            d22_run,
            tmp_path / "tampered_output",
            d19_source_dir=tampered_source,
        )
