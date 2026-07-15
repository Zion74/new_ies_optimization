from __future__ import annotations

import pytest

from tes_bess_boundary.e0d38_weekly_diagnostic import (
    group_actual_weeks,
    group_representative_weeks,
    summarize_assignment_error,
)


def test_group_actual_weeks_retains_52_weeks_and_tail() -> None:
    curtailment = [1.0] * 8_784
    renewable = [2.0] * 8_784

    weeks, tail = group_actual_weeks(curtailment, renewable)

    assert len(weeks) == 52
    assert weeks[1]["curtailment_mwh"] == pytest.approx(168.0)
    assert weeks[52]["curtailment_rate"] == pytest.approx(0.5)
    assert tail["curtailment_mwh"] == pytest.approx(48.0)


def test_representative_grouping_excludes_tail_warmup() -> None:
    rows = [
        {"source_role": "representative_scored", "source_week_index": "4"},
        {"source_role": "tail_warmup", "source_week_index": "52"},
        {"source_role": "tail_scored", "source_week_index": ""},
    ]

    weeks, tail = group_representative_weeks(
        [3.0, 100.0, 5.0],
        [6.0, 100.0, 10.0],
        rows,
    )

    assert weeks[4]["curtailment_mwh"] == pytest.approx(3.0)
    assert tail["curtailment_mwh"] == pytest.approx(5.0)
    assert tail["curtailment_rate"] == pytest.approx(0.5)


def test_assignment_summary_ranks_underrepresented_actual_week() -> None:
    actual = {
        1: {"curtailment_mwh": 12.0, "curtailment_rate": 0.2},
        2: {"curtailment_mwh": 4.0, "curtailment_rate": 0.1},
    }
    representatives = {
        4: {"curtailment_mwh": 5.0, "curtailment_rate": 0.1},
    }
    assignments = [
        {
            "original_week_index": "1",
            "assigned_representative_week_index": "4",
            "week_start": "2024-01-01T00:00:00",
            "week_end": "2024-01-07T23:00:00",
        },
        {
            "original_week_index": "2",
            "assigned_representative_week_index": "4",
            "week_start": "2024-01-08T00:00:00",
            "week_end": "2024-01-14T23:00:00",
        },
    ]

    weekly, clusters = summarize_assignment_error(
        actual,
        representatives,
        assignments,
    )

    assert weekly[0]["original_week_index"] == 1
    assert weekly[0]["curtailment_underrepresentation_mwh"] == pytest.approx(7.0)
    assert clusters[0]["actual_minimum_curtailment_mwh"] == pytest.approx(16.0)
    assert clusters[0]["representative_projected_curtailment_mwh"] == pytest.approx(
        10.0
    )
