from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest


def _synthetic_rows():
    from tes_bess_boundary.e0d17_exploration import E0D17InputRow

    rows = []
    start = datetime(2024, 1, 1)
    for hour in range(8_784):
        daily = 2.0 * math.pi * (hour % 24) / 24.0
        yearly = 2.0 * math.pi * hour / 8_784.0
        rows.append(
            E0D17InputRow(
                timestamp=start + timedelta(hours=hour),
                heat_demand_mw=300.0 + 70.0 * math.cos(yearly),
                wind_cf=0.4 + 0.2 * math.sin(yearly + daily),
                pv_cf=max(0.0, 0.8 * math.sin(daily - math.pi / 2.0)),
                ambient_temperature_c=12.0 - 15.0 * math.cos(yearly),
            )
        )
    return tuple(rows)


def _diagnostic(ranking: list[int]) -> dict:
    scores = {week: float(100 - index) for index, week in enumerate(ranking)}
    rows = [
        {
            "original_week_index": week,
            "curtailment_underrepresentation_mwh": scores.get(week, -float(week)),
        }
        for week in range(1, 53)
    ]
    return {
        "schema_id": "tes_bess_boundary.e0d38_weekly_failure_diagnostic.v1",
        "status": "complete",
        "state": {"state_id": "baseline"},
        "weekly_diagnostics": rows,
    }


def test_d39_selector_uses_top_two_non_d36_weeks_and_low_week_tie_break() -> None:
    from tes_bess_boundary.e0d39_service_aware_weeks import (
        LOCKED_D36_REPRESENTATIVE_WEEKS,
        select_additional_weeks,
    )

    diagnostic = _diagnostic([8, 49, 16])
    rows = diagnostic["weekly_diagnostics"]
    rows[15]["curtailment_underrepresentation_mwh"] = 90.0
    rows[48]["curtailment_underrepresentation_mwh"] = 90.0

    assert select_additional_weeks(
        diagnostic,
        LOCKED_D36_REPRESENTATIVE_WEEKS,
    ) == (16, 49)


def test_d39_selector_rejects_duplicate_week_indices() -> None:
    from tes_bess_boundary.e0d39_service_aware_weeks import (
        LOCKED_D36_REPRESENTATIVE_WEEKS,
        select_additional_weeks,
    )

    diagnostic = _diagnostic([49, 16])
    diagnostic["weekly_diagnostics"][0]["original_week_index"] = 2
    with pytest.raises(ValueError, match="uniquely cover"):
        select_additional_weeks(diagnostic, LOCKED_D36_REPRESENTATIVE_WEEKS)


@pytest.fixture(scope="module")
def synthetic_d39_plan():
    from tes_bess_boundary.e0d36_representative_weeks import (
        build_representative_week_plan,
    )
    from tes_bess_boundary.e0d39_service_aware_weeks import (
        build_service_aware_plan,
    )

    rows = _synthetic_rows()
    d36 = build_representative_week_plan(rows)
    original = {item + 1 for item in d36.representatives}
    additions = [week for week in range(1, 53) if week not in original][:2]
    return build_service_aware_plan(rows, _diagnostic(additions))


def test_d39_plan_reassigns_all_weeks_and_adds_exactly_two(synthetic_d39_plan) -> None:
    plan = synthetic_d39_plan

    assert len(plan.original_representatives) == 6
    assert len(plan.added_weeks_ranked) == 2
    assert len(plan.representatives) == 8
    assert len(plan.assignments) == 52
    assert sum(plan.representative_weights) == 52
    assert min(plan.representative_weights) >= 1
    for representative in plan.representatives:
        assert plan.assignments[representative] == representative


def test_d39_period_contract_has_nine_blocks_and_8784_weighted_hours(
    synthetic_d39_plan,
) -> None:
    from tes_bess_boundary.e0d39_service_aware_weeks import period_rows

    rows = period_rows(synthetic_d39_plan)
    scored = [row for row in rows if row["scored"] == "true"]
    tail = [row for row in rows if row["block_id"] == "year_end_tail"]

    assert len(rows) == 1_416
    assert len(scored) == 1_392
    assert len({row["block_id"] for row in rows}) == 9
    assert {row["block_order"] for row in tail} == {9}
    assert sum(float(row["annual_weight"]) for row in scored) == pytest.approx(
        8_784.0
    )
    assert tail[0]["source_timestamp"] == "2024-12-29T00:00:00"
    assert tail[-1]["source_timestamp"] == "2024-12-31T23:00:00"


def test_d39_export_is_byte_deterministic(synthetic_d39_plan, tmp_path) -> None:
    from tes_bess_boundary.e0d39_service_aware_weeks import (
        ASSIGNMENTS_NAME,
        MANIFEST_NAME,
        PERIODS_NAME,
        export_service_aware_plan,
    )

    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = export_service_aware_plan(synthetic_d39_plan, first)
    second_manifest = export_service_aware_plan(synthetic_d39_plan, second)

    assert first_manifest == second_manifest
    assert first_manifest["audit"]["passed"] is True
    for name in (ASSIGNMENTS_NAME, PERIODS_NAME, MANIFEST_NAME):
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert b"\r\n" not in (first / name).read_bytes()


def test_d39_formal_manifest_records_constructor_code_hashes() -> None:
    from tes_bess_boundary.e0d39_service_aware_weeks import (
        constructor_code_hashes,
    )

    hashes = constructor_code_hashes()
    assert set(hashes) == {"d39_code_sha256", "d36_code_sha256"}
    assert all(len(value) == 64 for value in hashes.values())
