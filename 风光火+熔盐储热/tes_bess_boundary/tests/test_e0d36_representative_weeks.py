from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta

import pytest


def _synthetic_rows():
    from tes_bess_boundary.e0d17_exploration import E0D17InputRow

    rows = []
    start = datetime(2024, 1, 1)
    for hour in range(8_784):
        day_angle = 2.0 * math.pi * (hour % 24) / 24.0
        year_angle = 2.0 * math.pi * hour / 8_784.0
        heat = 300.0 + 75.0 * math.cos(year_angle) + 20.0 * math.cos(day_angle)
        wind = min(
            0.82,
            max(0.05, 0.40 + 0.18 * math.sin(3.0 * year_angle + day_angle)),
        )
        daylight = max(0.0, math.sin(day_angle - math.pi / 2.0))
        pv = min(0.95, daylight * (0.55 + 0.25 * math.sin(year_angle)))
        temperature = 12.0 - 14.0 * math.cos(year_angle) + 3.0 * math.sin(day_angle)
        week = hour // 168
        if week == 9 and hour % 168 == 80:
            heat = 800.0
        if week == 29:
            wind = 1.0
            pv = max(pv, 0.75)
        rows.append(
            E0D17InputRow(
                timestamp=start + timedelta(hours=hour),
                heat_demand_mw=heat,
                wind_cf=wind,
                pv_cf=pv,
                ambient_temperature_c=temperature,
            )
        )
    return tuple(rows)


@pytest.fixture(scope="module")
def representative_plan():
    from tes_bess_boundary.e0d36_representative_weeks import (
        build_representative_week_plan,
    )

    return build_representative_week_plan(_synthetic_rows())


def test_d36_deterministic_pam_has_locked_tie_break() -> None:
    from tes_bess_boundary.e0d36_representative_weeks import deterministic_pam

    distances = (
        (0.0, 1.0, 10.0, 11.0),
        (1.0, 0.0, 9.0, 10.0),
        (10.0, 9.0, 0.0, 1.0),
        (11.0, 10.0, 1.0, 0.0),
    )

    assert deterministic_pam(distances, medoid_count=2) == (1, 2)


def test_d36_minimum_chp_proxy_respects_offline_and_heat_envelope() -> None:
    from tes_bess_boundary.e0d36_representative_weeks import (
        minimum_net_chp_power_for_heat,
    )

    assert minimum_net_chp_power_for_heat(0.0) == pytest.approx(0.0)
    assert 0.0 < minimum_net_chp_power_for_heat(83.0) < 100.0
    assert minimum_net_chp_power_for_heat(876.0) > 500.0
    with pytest.raises(ValueError, match="exceeds"):
        minimum_net_chp_power_for_heat(876.1)


def test_d36_rejects_a_timestamp_gap() -> None:
    from tes_bess_boundary.e0d36_representative_weeks import (
        build_representative_week_plan,
    )

    rows = list(_synthetic_rows())
    rows[100] = replace(rows[100], timestamp=rows[100].timestamp + timedelta(hours=1))
    with pytest.raises(ValueError, match="timestamp 100"):
        build_representative_week_plan(rows)


def test_d36_plan_covers_52_weeks_and_forces_both_extremes(
    representative_plan,
) -> None:
    plan = representative_plan

    assert len(plan.base_medoids) == 4
    assert len(plan.representatives) == 6
    assert len(set(plan.representatives)) == 6
    assert len(plan.assignments) == 52
    assert sum(plan.representative_weights) == 52
    assert min(plan.representative_weights) >= 1
    assert plan.peak_heat_extreme == 9
    assert plan.high_vre_extreme == 29
    assert "peak_heat_low_wind_extreme" in plan.roles_by_week[9]
    assert "high_vre_low_absorption_extreme" in plan.roles_by_week[29]


def test_d36_period_contract_has_real_tail_warmup_and_8784_weighted_hours(
    representative_plan,
) -> None:
    from tes_bess_boundary.e0d36_representative_weeks import _period_rows

    rows = _period_rows(representative_plan)
    scored = [row for row in rows if row["scored"] == "true"]
    warmup = [row for row in rows if row["source_role"] == "tail_warmup"]
    tail = [row for row in rows if row["source_role"] == "tail_scored"]

    assert len(rows) == 1_080
    assert len(scored) == 1_056
    assert len(warmup) == 24
    assert len(tail) == 48
    assert sum(float(row["annual_weight"]) for row in scored) == pytest.approx(
        8_784.0
    )
    assert {row["annual_weight"] for row in warmup} == {0}
    assert warmup[0]["source_timestamp"] == "2024-12-29T00:00:00"
    assert tail[0]["source_timestamp"] == "2024-12-30T00:00:00"
    assert tail[-1]["source_timestamp"] == "2024-12-31T23:00:00"


def test_d36_canonical_export_is_byte_deterministic(
    representative_plan,
    tmp_path,
) -> None:
    from tes_bess_boundary.e0d36_representative_weeks import (
        ASSIGNMENTS_NAME,
        MANIFEST_NAME,
        PERIODS_NAME,
        export_representative_week_plan,
    )

    first = tmp_path / "first"
    second = tmp_path / "second"
    manifest_first = export_representative_week_plan(representative_plan, first)
    manifest_second = export_representative_week_plan(representative_plan, second)

    assert manifest_first == manifest_second
    assert manifest_first["audit"]["passed"] is True
    for name in (ASSIGNMENTS_NAME, PERIODS_NAME, MANIFEST_NAME):
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert b"\r\n" not in (first / name).read_bytes()
