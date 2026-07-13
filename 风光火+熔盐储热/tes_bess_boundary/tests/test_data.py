from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pytest

from tes_bess_boundary.data import (
    OPERATIONS_PROFILE,
    PLANNING_PROFILE,
    audit_csv,
)


DATA_ROOT = Path(__file__).resolve().parents[2]


def _write_planning_csv(path: Path, timestamps: list[str], *, total_offset: float = 0.0) -> None:
    fields = [
        "ts",
        "P1",
        "P2",
        "P_elec_MW",
        "heat_demand_MWth",
        "pv_cf",
        "wind_cf_dingbian",
        "price_sell",
        "price_buy",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for timestamp in timestamps:
            writer.writerow(
                {
                    "ts": timestamp,
                    "P1": 100.0,
                    "P2": 110.0,
                    "P_elec_MW": 210.0 + total_offset,
                    "heat_demand_MWth": 200.0,
                    "pv_cf": 0.2,
                    "wind_cf_dingbian": 0.5,
                    "price_sell": 0.3,
                    "price_buy": 0.4,
                }
            )


@pytest.mark.data_integration
def test_real_planning_dataset_is_a_complete_leap_year() -> None:
    path = DATA_ROOT / "数据采集" / "口径3_统一数据集_2024.csv"

    report = audit_csv(path, PLANNING_PROFILE, year=2024)

    assert report.ok, report.issues
    assert report.row_count == 8784
    assert report.first_timestamp == datetime(2024, 1, 1, 0, 0)
    assert report.last_timestamp == datetime(2024, 12, 31, 23, 0)
    assert report.metrics["electric_total_max_abs_error_mw"] < 1e-9


@pytest.mark.data_integration
def test_real_operations_dataset_preserves_power_and_heat_totals() -> None:
    path = DATA_ROOT / "杨凌_合并逐时_2024_清洗.csv"

    report = audit_csv(path, OPERATIONS_PROFILE, year=2024)

    assert report.ok, report.issues
    assert report.metrics["electric_total_max_abs_error_mw"] < 1e-9
    assert report.metrics["heat_total_max_abs_error_mw"] < 1e-9


def test_missing_hour_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    _write_planning_csv(
        path,
        ["2024-01-01 00:00:00", "2024-01-01 02:00:00"],
    )

    report = audit_csv(path, PLANNING_PROFILE, year=2024)

    assert "timestamp_gap" in report.issue_codes


def test_duplicate_timestamp_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.csv"
    _write_planning_csv(
        path,
        [
            "2024-01-01 00:00:00",
            "2024-01-01 00:00:00",
            "2024-01-01 01:00:00",
        ],
    )

    report = audit_csv(path, PLANNING_PROFILE, year=2024)

    assert "duplicate_timestamp" in report.issue_codes


def test_inconsistent_electric_total_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "bad_total.csv"
    _write_planning_csv(path, ["2024-01-01 00:00:00"], total_offset=1.0)

    report = audit_csv(path, PLANNING_PROFILE, year=2024)

    assert "electric_total_mismatch" in report.issue_codes
    assert report.metrics["electric_total_max_abs_error_mw"] == pytest.approx(1.0)
