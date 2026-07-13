from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.mark.solver
@pytest.mark.integration
def test_real_24h_same_pcc_service_contract_closes_flat_settlement() -> None:
    from tes_bess_boundary.e0d17_exploration import DEFAULT_WINDOWS
    from tes_bess_boundary.e0d19_same_pcc_service import run_e0d19

    package_root = Path(__file__).resolve().parents[1]
    data_root = package_root.parent / "数据采集"
    configured_formal_dir = os.environ.get("TES_BESS_E0B_FORMAL_DIR")
    formal_dir = (
        Path(configured_formal_dir)
        if configured_formal_dir
        else data_root / "e0b_formal_2024"
    )
    run = run_e0d19(
        formal_dir / "e0b_heat_hourly_2024.csv",
        data_root / "口径3_统一数据集_2024.csv",
        windows=DEFAULT_WINDOWS[:1],
    )

    record = run.records[0]
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
