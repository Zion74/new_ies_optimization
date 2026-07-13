from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tes_bess_boundary.e0d19_same_pcc_service import E0D19PCCTraceRecord
from tes_bess_boundary.pcc_settlement_exposure import (
    price_spread_settlement_bound_cny_per_year,
    settlement_difference_cny_per_year,
    summarize_pcc_settlement_exposure,
)


def _trace() -> tuple[E0D19PCCTraceRecord, ...]:
    start = datetime(2024, 1, 1)
    comparator = (10.0, 20.0, 30.0)
    candidate = (20.0, 10.0, 30.0)
    return tuple(
        E0D19PCCTraceRecord(
            window_id="synthetic",
            timestamp=(start + timedelta(hours=index)).isoformat(timespec="seconds"),
            period_index=index,
            annual_weight_per_hour=100.0,
            comparator_pcc_export_mw=comparator[index],
            candidate_pcc_export_mw=candidate[index],
        )
        for index in range(3)
    )


def test_exposure_summary_preserves_energy_and_measures_redistribution() -> None:
    summary = summarize_pcc_settlement_exposure(
        _trace(), common_pcc_export_mwh=6_000.0
    )

    assert summary.comparator_pcc_export_mwh == pytest.approx(6_000.0)
    assert summary.candidate_pcc_export_mwh == pytest.approx(6_000.0)
    assert summary.annual_export_difference_mwh == pytest.approx(0.0)
    assert summary.positive_shifted_export_mwh == pytest.approx(1_000.0)
    assert summary.negative_shifted_export_mwh == pytest.approx(1_000.0)
    assert summary.gross_absolute_redistribution_mwh == pytest.approx(2_000.0)
    assert summary.redistributed_export_mwh == pytest.approx(1_000.0)
    assert summary.redistribution_fraction_of_common_export == pytest.approx(1 / 6)
    assert summary.max_abs_period_delta_mw == pytest.approx(10.0)
    assert (
        summary.settlement_delta_bound_cny_per_year_per_cny_per_mwh_spread
        == pytest.approx(1_000.0)
    )
    assert summary.flat_price_settlement_difference_cny_per_year == 0.0
    assert summary.time_varying_settlement_complete is False
    assert summary.trace_solution_uniqueness_proven is False


def test_flat_price_cancels_but_tou_value_is_bounded_by_price_spread() -> None:
    trace = _trace()
    summary = summarize_pcc_settlement_exposure(
        trace, common_pcc_export_mwh=6_000.0
    )

    assert settlement_difference_cny_per_year(trace, (200.0, 200.0, 200.0)) == (
        pytest.approx(0.0)
    )
    tou_delta = settlement_difference_cny_per_year(
        trace, (300.0, 100.0, 200.0)
    )
    bound = price_spread_settlement_bound_cny_per_year(
        summary, minimum_price_cny_per_mwh=100.0, maximum_price_cny_per_mwh=300.0
    )
    assert tou_delta == pytest.approx(200_000.0)
    assert abs(tou_delta) == pytest.approx(bound)


@pytest.mark.parametrize(
    ("prices", "message"),
    [
        ((1.0, 2.0), "one price per trace point"),
        ((1.0, float("nan"), 3.0), "finite"),
    ],
)
def test_settlement_evaluator_rejects_invalid_price_vectors(
    prices: tuple[float, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        settlement_difference_cny_per_year(_trace(), prices)


def test_summary_rejects_non_energy_neutral_same_service_trace() -> None:
    trace = list(_trace())
    trace[-1] = E0D19PCCTraceRecord(
        window_id="synthetic",
        timestamp=trace[-1].timestamp,
        period_index=trace[-1].period_index,
        annual_weight_per_hour=trace[-1].annual_weight_per_hour,
        comparator_pcc_export_mw=trace[-1].comparator_pcc_export_mw,
        candidate_pcc_export_mw=trace[-1].candidate_pcc_export_mw + 1.0,
    )

    with pytest.raises(ValueError, match="same annual PCC service"):
        summarize_pcc_settlement_exposure(
            tuple(trace), common_pcc_export_mwh=6_000.0
        )
