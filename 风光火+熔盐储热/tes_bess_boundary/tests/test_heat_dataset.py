from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from openpyxl import Workbook

from tes_bess_boundary.heat_dataset import (
    HeatBuildSpec,
    HeatQualityFlag,
    HeatSourceBundle,
    YANG_LING_SOURCE_HASHES,
    YANG_LING_DONGFANG_SIGN_MISMATCH_TIMESTAMPS,
    build_heat_dataset,
    write_heat_dataset,
)
from tes_bess_boundary.raw_heat import ConflictingDuplicateError


DATA_ROOT = Path(__file__).resolve().parents[2]


def _write_records(path: Path, rows: list[str]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    for row_number, value in enumerate(rows, start=9):
        sheet.cell(row=row_number, column=1, value=value)
    workbook.save(path)


def _row(timestamp: str, values: str) -> str:
    return f"{timestamp} {values}"


def _relaxed_spec() -> HeatBuildSpec:
    return HeatBuildSpec(
        year=2024,
        enforce_source_contract=False,
        enforce_complete_grid=False,
        zero_segment_start=None,
        zero_segment_end=None,
    )


def test_source_ledger_keeps_duplicate_and_non_grid_evidence_and_repairs_only_sentinel(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"
    _write_records(
        first,
        [
            _row("2024-09-30 17:50:00", "11.06 88.65 14.47 30.69 4.33"),
            _row(
                "2024-09-30 18:00:00",
                "11.05 160.87 -10000000 56.24 -10000000000",
            ),
            _row("2024-09-30 18:10:00", "11.24 120.87 24.57 41.22 8.40"),
        ],
    )
    _write_records(
        second,
        [
            _row("2024-09-30 18:10:00", "11.24 120.87 24.57 41.22 8.40"),
            _row("2024-09-30 23:59:59", "1 2 3 4 5"),
        ],
    )

    dataset = build_heat_dataset(
        HeatSourceBundle(first, second),
        spec=_relaxed_spec(),
    )

    assert len(dataset.source_ledger) == 5
    duplicate_rows = [
        point
        for point in dataset.source_ledger
        if HeatQualityFlag.SOURCE_DUPLICATE in point.flags
    ]
    assert len(duplicate_rows) == 2
    assert sum(point.canonical for point in duplicate_rows) == 1
    assert dataset.audit.duplicate_timestamp_count == 1
    assert dataset.audit.duplicate_extra_count == 1
    assert dataset.audit.duplicate_ledger_flagged_row_count == 2
    assert dataset.audit.duplicate_canonical_flagged_count == 1
    excluded = [
        point
        for point in dataset.source_ledger
        if HeatQualityFlag.NON_GRID_EXCLUDED in point.flags
    ]
    assert len(excluded) == 1
    assert not excluded[0].included

    sentinel = next(
        point
        for point in dataset.grid_points
        if point.timestamp == datetime(2024, 9, 30, 18, 0)
    )
    assert sentinel.raw.oldcity_gj_per_h == -10_000_000
    assert sentinel.repaired.oldcity_gj_per_h == pytest.approx(19.52)
    assert sentinel.repaired.oldcity_flow == pytest.approx(6.365)
    assert sentinel.repaired.resident_gj_per_h == 11.05
    assert sentinel.repaired.dongfang_gj_per_h == 160.87
    assert sentinel.repaired.dongfang_flow == 56.24
    assert HeatQualityFlag.SENTINEL_INTERPOLATED in sentinel.flags


def test_conflicting_duplicate_fails_loudly(tmp_path: Path) -> None:
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"
    _write_records(first, [_row("2024-01-01 00:00:00", "1 2 3 4 5")])
    _write_records(second, [_row("2024-01-01 00:00:00", "1 2 4 4 5")])

    with pytest.raises(ConflictingDuplicateError):
        build_heat_dataset(
            HeatSourceBundle(first, second),
            spec=_relaxed_spec(),
        )


def test_duplicate_metrics_distinguish_timestamp_extra_and_flagged_rows(
    tmp_path: Path,
) -> None:
    source = tmp_path / "three_identical_rows.xlsx"
    row = _row("2024-01-01 00:00:00", "1 2 3 4 5")
    _write_records(source, [row, row, row])

    audit = build_heat_dataset(
        HeatSourceBundle(source),
        spec=_relaxed_spec(),
    ).audit

    assert audit.duplicate_timestamp_count == 1
    assert audit.duplicate_extra_count == 2
    assert audit.duplicate_ledger_flagged_row_count == 3
    assert audit.duplicate_canonical_flagged_count == 1
    assert audit.flag_counts[HeatQualityFlag.SOURCE_DUPLICATE] == 1


def test_signed_net_is_preserved_and_forward_series_clips_each_branch(
    tmp_path: Path,
) -> None:
    path = tmp_path / "signed.xlsx"
    _write_records(
        path,
        [
            _row("2024-01-01 00:00:00", "-29.37 5 -1 2 3"),
            _row("2024-01-01 00:10:00", "5 -22.41 1 -7.30 2"),
            _row("2024-01-01 00:20:00", "1 -1 0 -1 0"),
            _row("2024-01-01 00:30:00", "0 0 0 0 0"),
        ],
    )

    dataset = build_heat_dataset(
        HeatSourceBundle(path),
        spec=_relaxed_spec(),
    )
    resident_negative, reverse, zero_sum, exact_zero = dataset.grid_points

    assert resident_negative.heat_net_mw == pytest.approx((-29.37 + 5 - 1) / 3.6)
    assert resident_negative.heat_net_mw < 0
    assert resident_negative.heat_forward_mw == pytest.approx(5 / 3.6)
    assert HeatQualityFlag.RESIDENT_NEGATIVE in resident_negative.flags

    assert reverse.repaired.dongfang_gj_per_h == -22.41
    assert reverse.repaired.dongfang_flow == -7.30
    assert HeatQualityFlag.SIGNED_REVERSE_FLOW in reverse.flags
    assert reverse.heat_forward_mw == pytest.approx(6 / 3.6)

    assert zero_sum.heat_net_mw == 0.0
    assert HeatQualityFlag.ALL_SIGNAL_ZERO not in zero_sum.flags
    assert HeatQualityFlag.ALL_SIGNAL_ZERO in exact_zero.flags


def test_negative_dongfang_heat_without_negative_flow_fails(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mismatch.xlsx"
    _write_records(path, [_row("2024-01-01 00:00:00", "1 -2 3 4 5")])

    with pytest.raises(ValueError, match="negative Dongfang heat requires negative flow"):
        build_heat_dataset(
            HeatSourceBundle(path),
            spec=_relaxed_spec(),
        )


def test_negative_dongfang_flow_during_sign_transition_is_preserved_and_flagged(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transition.xlsx"
    _write_records(path, [_row("2024-09-30 17:30:00", "11.03 17.68 51.89 -4.24 17.54")])

    point = build_heat_dataset(
        HeatSourceBundle(path),
        spec=_relaxed_spec(),
    ).grid_points[0]

    assert point.repaired.dongfang_flow == -4.24
    assert HeatQualityFlag.SIGNED_REVERSE_FLOW not in point.flags
    assert HeatQualityFlag.DONGFANG_SIGN_MISMATCH in point.flags


def test_unregistered_extreme_value_fails(tmp_path: Path) -> None:
    path = tmp_path / "extreme.xlsx"
    _write_records(
        path,
        [_row("2024-01-01 00:00:00", "1 2 -1000000 4 5")],
    )

    with pytest.raises(ValueError, match="unregistered sentinel"):
        build_heat_dataset(
            HeatSourceBundle(path),
            spec=_relaxed_spec(),
        )


def _imputation_spec(target: datetime) -> HeatBuildSpec:
    return HeatBuildSpec(
        year=2024,
        enforce_source_contract=False,
        enforce_complete_grid=False,
        zero_segment_start=target,
        zero_segment_end=target,
    )


def test_registered_zero_segment_uses_fieldwise_four_donor_median(
    tmp_path: Path,
) -> None:
    path = tmp_path / "zero_segment.xlsx"
    target = datetime(2024, 1, 15, 6, 20)
    donor_values = {
        -14: "10 20 30 40 50",
        -7: "30 40 50 60 70",
        7: "50 60 70 80 90",
        14: "70 80 90 100 110",
    }
    rows = [
        _row(f"{target + timedelta(days=offset):%Y-%m-%d %H:%M:%S}", values)
        for offset, values in donor_values.items()
    ]
    rows.extend(
        [
            _row(f"{target:%Y-%m-%d %H:%M:%S}", "0 0 0 0 0"),
            _row("2024-01-16 06:20:00", "0 0 0 0 0"),
        ]
    )
    _write_records(path, rows)

    dataset = build_heat_dataset(
        HeatSourceBundle(path),
        spec=_imputation_spec(target),
    )

    imputed = next(point for point in dataset.grid_points if point.timestamp == target)
    untouched = next(
        point
        for point in dataset.grid_points
        if point.timestamp == datetime(2024, 1, 16, 6, 20)
    )
    assert imputed.raw.values == (0.0, 0.0, 0.0, 0.0, 0.0)
    assert imputed.repaired.values == (0.0, 0.0, 0.0, 0.0, 0.0)
    assert imputed.zero_sensitivity.values == (40.0, 50.0, 60.0, 70.0, 80.0)
    assert imputed.heat_net_mw == 0.0
    assert imputed.heat_forward_mw == 0.0
    assert imputed.heat_zero_sensitivity_mw == pytest.approx(150 / 3.6)
    assert HeatQualityFlag.ALL_SIGNAL_ZERO in imputed.flags
    assert HeatQualityFlag.ZERO_SEGMENT_IMPUTED in imputed.flags
    assert untouched.zero_sensitivity.values == untouched.repaired.values
    assert HeatQualityFlag.ZERO_SEGMENT_IMPUTED not in untouched.flags


def test_zero_imputation_fails_when_any_registered_donor_is_all_zero(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad_donor.xlsx"
    target = datetime(2024, 1, 15, 6, 20)
    rows = [
        _row(
            f"{target + timedelta(days=offset):%Y-%m-%d %H:%M:%S}",
            "0 0 0 0 0" if offset == -7 else "10 20 30 40 50",
        )
        for offset in (-14, -7, 7, 14)
    ]
    rows.append(_row(f"{target:%Y-%m-%d %H:%M:%S}", "0 0 0 0 0"))
    _write_records(path, rows)

    with pytest.raises(ValueError, match="invalid zero-imputation donor"):
        build_heat_dataset(
            HeatSourceBundle(path),
            spec=_imputation_spec(target),
        )


def test_hourly_values_are_means_of_exactly_six_rates_and_flags_are_counts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "hour.xlsx"
    timestamp = datetime(2024, 1, 1, 0, 0)
    values = [
        "-6 12 6 2 3",
        "0 -3 3 -1 1",
        "0 0 0 0 0",
        "6 12 18 2 3",
        "12 18 24 3 4",
        "18 24 30 4 5",
    ]
    _write_records(
        path,
        [
            _row(
                f"{timestamp + timedelta(minutes=10 * index):%Y-%m-%d %H:%M:%S}",
                row_values,
            )
            for index, row_values in enumerate(values)
        ],
    )

    dataset = build_heat_dataset(
        HeatSourceBundle(path),
        spec=_relaxed_spec(),
    )

    assert len(dataset.hourly_points) == 1
    hour = dataset.hourly_points[0]
    assert hour.timestamp == timestamp
    assert hour.source_sample_count == 6
    assert hour.resident_gj_per_h == pytest.approx(5.0)
    assert hour.dongfang_gj_per_h == pytest.approx(10.5)
    assert hour.oldcity_gj_per_h == pytest.approx(13.5)
    assert hour.heat_net_mw == pytest.approx(29 / 3.6)
    expected_forward = sum(point.heat_forward_mw for point in dataset.grid_points) / 6
    assert hour.heat_forward_mw == pytest.approx(expected_forward)
    assert hour.heat_zero_sensitivity_mw == pytest.approx(hour.heat_net_mw)
    assert hour.flag_counts[HeatQualityFlag.RESIDENT_NEGATIVE] == 1
    assert hour.flag_counts[HeatQualityFlag.SIGNED_REVERSE_FLOW] == 1
    assert hour.flag_counts[HeatQualityFlag.ALL_SIGNAL_ZERO] == 1
    assert all(isinstance(count, int) for count in hour.flag_counts.values())

    ten_minute_energy_mwh = sum(
        point.heat_net_mw / 6.0 for point in dataset.grid_points
    )
    hourly_energy_mwh = sum(point.heat_net_mw for point in dataset.hourly_points)
    assert hourly_energy_mwh == pytest.approx(ten_minute_energy_mwh)


def test_export_is_byte_stable_and_manifest_hashes_match_files(
    tmp_path: Path,
) -> None:
    first_source = tmp_path / "first_half.xlsx"
    second_source = tmp_path / "second_half.xlsx"
    start = datetime(2024, 1, 1)
    _write_records(
        first_source,
        [
            _row(
                f"{start + timedelta(minutes=10 * index):%Y-%m-%d %H:%M:%S}",
                f"1 1 1 {index + 4} {index + 5}",
            )
            for index in range(3)
        ],
    )
    _write_records(
        second_source,
        [
            _row(
                f"{start + timedelta(minutes=10 * index):%Y-%m-%d %H:%M:%S}",
                f"1 1 1 {index + 4} {index + 5}",
            )
            for index in range(3, 6)
        ],
    )
    spec = _relaxed_spec()
    dataset = build_heat_dataset(
        HeatSourceBundle(first_source, second_source),
        spec=spec,
    )

    assert dataset.spec is spec
    assert dataset.registry_version == "yangling_heat_2024.v1"

    first = write_heat_dataset(dataset, tmp_path / "first")
    second = write_heat_dataset(dataset, tmp_path / "second")

    assert first.ledger_path.name == "e0b_heat_source_ledger_2024.csv"
    assert first.hourly_path.name == "e0b_heat_hourly_2024.csv"
    assert first.manifest_path.name == "manifest.json"
    for first_path, second_path in (
        (first.ledger_path, second.ledger_path),
        (first.hourly_path, second.hourly_path),
        (first.manifest_path, second.manifest_path),
    ):
        assert first_path.read_bytes() == second_path.read_bytes()
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "tes_bess_boundary.e0b_heat_dataset.v2"
    assert manifest["registry_version"] == dataset.registry_version
    assert manifest["sources"] == [
        {
            "name": first_source.name,
            "role": "first_half",
            "sha256": hashlib.sha256(first_source.read_bytes()).hexdigest(),
        },
        {
            "name": second_source.name,
            "role": "second_half",
            "sha256": hashlib.sha256(second_source.read_bytes()).hexdigest(),
        },
    ]
    contract = manifest["contract"]
    assert contract["canonicalization"]["duplicate_resolution"] == (
        "first_row_wins_when_all_five_signals_are_identical"
    )
    assert contract["sentinel_repair"] == {
        "neighbor_offsets_minutes": [-10, 10],
        "operation": "arithmetic_mean",
        "raw_signature": {
            "oldcity_flow": -10_000_000_000.0,
            "oldcity_gj_per_h": -10_000_000.0,
        },
        "repair_fields": ["oldcity_gj_per_h", "oldcity_flow"],
        "timestamp": "2024-09-30T18:00:00",
        "unregistered_abs_threshold": 1_000_000.0,
    }
    assert contract["zero_sensitivity"]["donor_day_offsets"] == [-14, -7, 7, 14]
    assert contract["zero_sensitivity"]["donor_rejections"] == [
        "missing",
        "all_five_signals_zero",
        "sentinel_interpolated",
    ]
    assert contract["sign_classification"]["signed_reverse_flow"] == {
        "predicate": "dongfang_gj_per_h < 0 and dongfang_flow < 0",
        "registry_expected_count": 29,
    }
    assert contract["sign_classification"]["dongfang_sign_mismatch"][
        "predicate"
    ] == "dongfang_gj_per_h >= 0 and dongfang_flow < 0"
    assert contract["sign_classification"]["dongfang_sign_mismatch"][
        "registry_expected_count"
    ] == 49
    assert contract["negative_net_hour_signature"] == {
        "predicate": "heat_net_mw < 0",
        "registry_expected_count": 1,
        "registry_expected_timestamps": ["2024-05-27T02:00:00"],
    }
    assert manifest["counts"]["duplicates"] == {
        "canonical_flagged_rows": 0,
        "extra_rows": 0,
        "ledger_flagged_rows": 0,
        "timestamp_count": 0,
    }
    assert manifest["hourly_ranges_mw"]["heat_net_mw"]["min"] == (
        0.833333333333
    )
    assert "0.8333333333333" not in first.manifest_path.read_text(encoding="utf-8")
    assert manifest["outputs"][first.ledger_path.name]["sha256"] == hashlib.sha256(
        first.ledger_path.read_bytes()
    ).hexdigest()
    assert manifest["outputs"][first.hourly_path.name]["sha256"] == hashlib.sha256(
        first.hourly_path.read_bytes()
    ).hexdigest()
    assert str(tmp_path).encode() not in first.ledger_path.read_bytes()
    assert b"1.000000000000" in first.ledger_path.read_bytes()
    assert first.manifest_path.name not in manifest["outputs"]
    assert first.output_sha256[first.manifest_path.name] == hashlib.sha256(
        first.manifest_path.read_bytes()
    ).hexdigest()


def _real_sources() -> HeatSourceBundle:
    base = DATA_ROOT / "杨凌机组数据" / "杨凌机组数据" / "热功率"
    return HeatSourceBundle(
        base / "2024.1.1-2024.6.30杨凌供热数据.xlsx",
        base / "2024.7.1-2024.12.31杨凌供热数据.xlsx",
    )


@pytest.mark.data_integration
def test_real_formal_dataset_matches_locked_2024_signature() -> None:
    dataset = build_heat_dataset(_real_sources(), spec=HeatBuildSpec())

    assert dataset.audit.formal_ready
    assert dataset.audit.source_row_count == 52_707
    assert dataset.audit.canonical_count == 52_704
    assert dataset.audit.hourly_count == 8_784
    assert dataset.audit.duplicate_extra_count == 1
    assert dataset.audit.non_grid_excluded_count == 2
    assert dataset.audit.flag_counts[HeatQualityFlag.SENTINEL_INTERPOLATED] == 1
    assert dataset.audit.flag_counts[HeatQualityFlag.SIGNED_REVERSE_FLOW] == 29
    assert dataset.audit.flag_counts[HeatQualityFlag.RESIDENT_NEGATIVE] == 2_050
    assert dataset.audit.flag_counts[HeatQualityFlag.ALL_SIGNAL_ZERO] == 316
    assert dataset.audit.flag_counts[HeatQualityFlag.ZERO_SEGMENT_IMPUTED] == 226
    assert dataset.audit.flag_counts[HeatQualityFlag.DONGFANG_SIGN_MISMATCH] == 49
    assert tuple(
        point.timestamp
        for point in dataset.grid_points
        if HeatQualityFlag.DONGFANG_SIGN_MISMATCH in point.flags
    ) == YANG_LING_DONGFANG_SIGN_MISMATCH_TIMESTAMPS
    assert dataset.audit.negative_net_hour_count == 1
    assert sum(point.heat_net_mw * 3.6 for point in dataset.hourly_points) == pytest.approx(
        5_024_409.853333,
        abs=1e-6,
    )
    assert sum(
        point.heat_forward_mw * 3.6 for point in dataset.hourly_points
    ) == pytest.approx(5_026_386.438333, abs=1e-6)


@pytest.mark.data_integration
def test_real_formal_export_is_independently_reproducible_and_self_consistent(
    tmp_path: Path,
) -> None:
    first_dataset = build_heat_dataset(_real_sources(), spec=HeatBuildSpec())
    first_export = write_heat_dataset(first_dataset, tmp_path / "first")
    second_dataset = build_heat_dataset(_real_sources(), spec=HeatBuildSpec())
    second_export = write_heat_dataset(second_dataset, tmp_path / "second")

    for first_path, second_path in (
        (first_export.ledger_path, second_export.ledger_path),
        (first_export.hourly_path, second_export.hourly_path),
        (first_export.manifest_path, second_export.manifest_path),
    ):
        assert first_path.read_bytes() == second_path.read_bytes()

    with first_export.ledger_path.open(encoding="utf-8", newline="") as handle:
        ledger_rows = list(csv.DictReader(handle))
    with first_export.hourly_path.open(encoding="utf-8", newline="") as handle:
        hourly_rows = list(csv.DictReader(handle))
    manifest = json.loads(first_export.manifest_path.read_text(encoding="utf-8"))

    assert len(ledger_rows) == 52_707
    assert len(hourly_rows) == 8_784
    assert manifest["outputs"][first_export.ledger_path.name]["rows"] == 52_707
    assert manifest["outputs"][first_export.hourly_path.name]["rows"] == 8_784
    assert manifest["counts"]["duplicates"] == {
        "canonical_flagged_rows": 1,
        "extra_rows": 1,
        "ledger_flagged_rows": 2,
        "timestamp_count": 1,
    }
    assert manifest["counts"]["canonical_flagged_rows_by_quality"][
        HeatQualityFlag.SOURCE_DUPLICATE.value
    ] == 1
    assert [item["role"] for item in manifest["sources"]] == [
        "first_half",
        "second_half",
    ]
    assert {item["name"]: item["sha256"] for item in manifest["sources"]} == dict(
        YANG_LING_SOURCE_HASHES
    )

    zero_points = [
        point
        for point in first_dataset.grid_points
        if HeatQualityFlag.ZERO_SEGMENT_IMPUTED in point.flags
    ]
    assert len(zero_points) == 226
    assert zero_points[0].timestamp == datetime(2024, 10, 10, 19, 30)
    assert zero_points[-1].timestamp == datetime(2024, 10, 12, 9, 0)
    assert all(
        point.raw.values == (0.0, 0.0, 0.0, 0.0, 0.0)
        and HeatQualityFlag.ALL_SIGNAL_ZERO in point.flags
        for point in zero_points
    )
    assert manifest["observed_signatures"]["zero_segment"] == {
        "count": 226,
        "end": "2024-10-12T09:00:00",
        "predicate": "all_five_signals_zero and zero_segment_imputed",
        "start": "2024-10-10T19:30:00",
    }
    zero_contract = manifest["contract"]["zero_sensitivity"]
    assert zero_contract["interval"] == {
        "closure": "both",
        "end": "2024-10-12T09:00:00",
        "start": "2024-10-10T19:30:00",
    }
    assert zero_contract["expected_point_count"] == 226

    annual_from_csv = {
        "heat_net": sum(float(row["heat_net_mw"]) * 3.6 for row in hourly_rows),
        "heat_forward": sum(
            float(row["heat_forward_mw"]) * 3.6 for row in hourly_rows
        ),
        "heat_zero_sensitivity": sum(
            float(row["heat_zero_sensitivity_mw"]) * 3.6
            for row in hourly_rows
        ),
    }
    for name, value in annual_from_csv.items():
        assert manifest["annual_energy_gj"][name] == pytest.approx(value, abs=1e-6)
    for path in (first_export.ledger_path, first_export.hourly_path):
        assert manifest["outputs"][path.name]["sha256"] == hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    assert first_export.manifest_path.name not in manifest["outputs"]
    assert first_export.output_sha256[first_export.manifest_path.name] == (
        hashlib.sha256(first_export.manifest_path.read_bytes()).hexdigest()
    )
