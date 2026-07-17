"""Auditable construction of the 2024 Yangling heat dataset.

The module deliberately keeps every in-year source row in a ledger while a
separate canonical grid feeds transformations and hourly aggregation.  It is
therefore impossible for de-duplication, boundary exclusion, or registered
repair to erase the source evidence that motivated the transformation.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from statistics import median
from typing import Mapping

from .raw_heat import (
    ConflictingDuplicateError,
    HEAT_VALUE_FIELDS,
    HeatRecord,
    parse_heat_workbook,
)


YANG_LING_SOURCE_HASHES: Mapping[str, str] = {
    "2024.1.1-2024.6.30杨凌供热数据.xlsx": (
        "1ddb1251f5e7504ac580182260d257b99994a3d595b3a918d1d514296b431fef"
    ),
    "2024.7.1-2024.12.31杨凌供热数据.xlsx": (
        "e028d6abc0c1e3817b5451045b10fac3a6ff9804981ea64cc13b78e64249086b"
    ),
}
YANG_LING_HEAT_REGISTRY_VERSION = "yangling_heat_2024.v1"


class HeatQualityFlag(str, Enum):
    SOURCE_DUPLICATE = "source_duplicate"
    NON_GRID_EXCLUDED = "non_grid_excluded"
    SENTINEL_INTERPOLATED = "sentinel_interpolated"
    SIGNED_REVERSE_FLOW = "signed_reverse_flow"
    RESIDENT_NEGATIVE = "resident_negative"
    ALL_SIGNAL_ZERO = "all_signal_zero"
    ZERO_SEGMENT_IMPUTED = "zero_segment_imputed"
    DONGFANG_SIGN_MISMATCH = "dongfang_sign_mismatch"


YANG_LING_DONGFANG_SIGN_MISMATCH_TIMESTAMPS = tuple(
    datetime.fromisoformat(value)
    for value in (
        "2024-09-30T17:30:00",
        "2024-10-09T06:20:00",
        "2024-10-12T11:30:00",
        "2024-10-12T13:00:00",
        "2024-10-12T13:10:00",
        "2024-10-12T13:30:00",
        "2024-10-12T13:50:00",
        "2024-10-12T19:40:00",
        "2024-10-12T19:50:00",
        "2024-10-12T20:00:00",
        "2024-10-12T20:10:00",
        "2024-10-23T09:00:00",
        "2024-10-23T11:00:00",
        "2024-10-23T11:10:00",
        "2024-10-23T11:20:00",
        "2024-10-23T11:40:00",
        "2024-10-23T11:50:00",
        "2024-10-23T12:00:00",
        "2024-10-23T12:10:00",
        "2024-10-23T12:20:00",
        "2024-10-23T12:30:00",
        "2024-10-23T12:40:00",
        "2024-10-23T12:50:00",
        "2024-10-23T13:00:00",
        "2024-10-23T13:10:00",
        "2024-10-23T13:50:00",
        "2024-10-23T14:00:00",
        "2024-10-23T14:10:00",
        "2024-10-23T14:40:00",
        "2024-10-23T15:20:00",
        "2024-10-23T15:30:00",
        "2024-10-23T15:40:00",
        "2024-10-23T15:50:00",
        "2024-10-23T16:00:00",
        "2024-10-23T16:10:00",
        "2024-10-23T16:20:00",
        "2024-10-23T16:30:00",
        "2024-10-23T16:40:00",
        "2024-10-23T16:50:00",
        "2024-11-28T12:10:00",
        "2024-12-28T06:50:00",
        "2024-12-28T07:00:00",
        "2024-12-28T07:10:00",
        "2024-12-28T07:20:00",
        "2024-12-28T07:30:00",
        "2024-12-28T07:40:00",
        "2024-12-28T07:50:00",
        "2024-12-28T11:00:00",
        "2024-12-28T11:10:00",
    )
)


class SourceDisposition(str, Enum):
    CANONICAL = "canonical"
    DUPLICATE = "duplicate"
    NON_GRID_EXCLUDED = "non_grid_excluded"


@dataclass(frozen=True)
class HeatSignals:
    resident_gj_per_h: float
    dongfang_gj_per_h: float
    oldcity_gj_per_h: float
    dongfang_flow: float
    oldcity_flow: float

    @classmethod
    def from_record(cls, record: HeatRecord) -> "HeatSignals":
        return cls(*(float(getattr(record, name)) for name in HEAT_VALUE_FIELDS))

    @property
    def values(self) -> tuple[float, ...]:
        return tuple(float(getattr(self, name)) for name in HEAT_VALUE_FIELDS)


@dataclass(frozen=True)
class HeatSourceBundle:
    first_half: Path
    second_half: Path | None = None

    @property
    def paths(self) -> tuple[Path, ...]:
        if self.second_half is None:
            return (Path(self.first_half),)
        return (Path(self.first_half), Path(self.second_half))


@dataclass(frozen=True)
class HeatBuildSpec:
    year: int = 2024
    registry_version: str = YANG_LING_HEAT_REGISTRY_VERSION
    expected_source_hashes: Mapping[str, str] = field(
        default_factory=lambda: dict(YANG_LING_SOURCE_HASHES)
    )
    enforce_source_contract: bool = True
    enforce_complete_grid: bool = True
    sentinel_timestamp: datetime = datetime(2024, 9, 30, 18, 0)
    sentinel_oldcity_heat: float = -10_000_000.0
    sentinel_oldcity_flow: float = -10_000_000_000.0
    sentinel_abs_threshold: float = 1_000_000.0
    zero_segment_start: datetime | None = datetime(2024, 10, 10, 19, 30)
    zero_segment_end: datetime | None = datetime(2024, 10, 12, 9, 0)
    expected_source_row_count: int = 52_707
    expected_canonical_count: int = 52_704
    expected_hourly_count: int = 8_784
    expected_duplicate_extra_count: int = 1
    expected_non_grid_excluded_count: int = 2
    expected_duplicate_extra_timestamps: tuple[datetime, ...] = (
        datetime(2024, 6, 30, 23, 50),
    )
    expected_non_grid_excluded_timestamps: tuple[datetime, ...] = (
        datetime(2024, 6, 30, 23, 59, 59),
        datetime(2024, 12, 31, 23, 59, 59),
    )
    expected_sentinel_count: int = 1
    expected_reverse_flow_count: int = 29
    expected_resident_negative_count: int = 2_050
    expected_all_signal_zero_count: int = 316
    expected_zero_segment_imputed_count: int = 226
    expected_dongfang_sign_mismatch_timestamps: tuple[datetime, ...] = (
        YANG_LING_DONGFANG_SIGN_MISMATCH_TIMESTAMPS
    )
    expected_negative_net_hour_count: int = 1
    expected_negative_net_hour_timestamps: tuple[datetime, ...] = (
        datetime(2024, 5, 27, 2, 0),
    )
    expected_annual_net_gj: float = 5_024_409.853333
    expected_annual_forward_gj: float = 5_026_386.438333


@dataclass(frozen=True)
class SourceHeatPoint:
    timestamp: datetime
    source_path: Path
    source_sha256: str
    source_sheet: str
    source_row: int
    source_raw_cell: str
    raw: HeatSignals
    repaired: HeatSignals
    zero_sensitivity: HeatSignals
    included: bool
    canonical: bool
    flags: frozenset[HeatQualityFlag]
    disposition: SourceDisposition

    @property
    def heat_net_mw(self) -> float:
        return (
            self.repaired.resident_gj_per_h
            + self.repaired.dongfang_gj_per_h
            + self.repaired.oldcity_gj_per_h
        ) / 3.6

    @property
    def heat_forward_mw(self) -> float:
        return (
            max(self.repaired.resident_gj_per_h, 0.0)
            + max(self.repaired.dongfang_gj_per_h, 0.0)
            + max(self.repaired.oldcity_gj_per_h, 0.0)
        ) / 3.6

    @property
    def heat_zero_sensitivity_mw(self) -> float:
        return (
            self.zero_sensitivity.resident_gj_per_h
            + self.zero_sensitivity.dongfang_gj_per_h
            + self.zero_sensitivity.oldcity_gj_per_h
        ) / 3.6


@dataclass(frozen=True)
class HourlyHeatPoint:
    timestamp: datetime
    resident_gj_per_h: float
    dongfang_gj_per_h: float
    oldcity_gj_per_h: float
    dongfang_flow: float
    oldcity_flow: float
    heat_net_mw: float
    heat_forward_mw: float
    heat_zero_sensitivity_mw: float
    zero_sensitivity: HeatSignals
    source_sample_count: int
    flag_counts: Mapping[HeatQualityFlag, int]


@dataclass(frozen=True)
class HeatDatasetAudit:
    source_row_count: int
    canonical_count: int
    hourly_count: int
    flag_counts: Mapping[HeatQualityFlag, int]
    source_hashes: Mapping[str, str]
    duplicate_timestamp_count: int
    duplicate_extra_count: int
    duplicate_ledger_flagged_row_count: int
    duplicate_canonical_flagged_count: int
    non_grid_excluded_count: int
    negative_net_hour_count: int
    annual_net_gj: float
    annual_forward_gj: float
    annual_zero_sensitivity_gj: float
    formal_ready: bool


@dataclass(frozen=True)
class HeatSourceIdentity:
    role: str
    name: str
    sha256: str


@dataclass(frozen=True)
class BuiltHeatDataset:
    source_ledger: tuple[SourceHeatPoint, ...]
    grid_points: tuple[SourceHeatPoint, ...]
    hourly_points: tuple[HourlyHeatPoint, ...]
    audit: HeatDatasetAudit
    spec: HeatBuildSpec
    registry_version: str
    source_identities: tuple[HeatSourceIdentity, ...]


@dataclass(frozen=True)
class ExportManifest:
    ledger_path: Path
    hourly_path: Path
    manifest_path: Path
    output_sha256: Mapping[str, str]


def _is_grid_point(timestamp: datetime) -> bool:
    return (
        timestamp.minute % 10 == 0
        and timestamp.second == 0
        and timestamp.microsecond == 0
    )


def _source_point(
    record: HeatRecord,
    *,
    included: bool,
    canonical: bool,
    disposition: SourceDisposition,
    flags: frozenset[HeatQualityFlag] = frozenset(),
) -> SourceHeatPoint:
    if (
        record.source_path is None
        or record.source_sha256 is None
        or record.source_sheet is None
        or record.source_row is None
        or record.source_raw_cell is None
    ):
        raise ValueError("source provenance is required for every heat record")
    signals = HeatSignals.from_record(record)
    return SourceHeatPoint(
        timestamp=record.timestamp,
        source_path=record.source_path,
        source_sha256=record.source_sha256,
        source_sheet=record.source_sheet,
        source_row=record.source_row,
        source_raw_cell=record.source_raw_cell,
        raw=signals,
        repaired=signals,
        zero_sensitivity=signals,
        included=included,
        canonical=canonical,
        flags=flags,
        disposition=disposition,
    )


def _validate_source_hashes(
    source_hashes: Mapping[str, str], spec: HeatBuildSpec
) -> None:
    if not spec.enforce_source_contract:
        return
    expected = {name: value.lower() for name, value in spec.expected_source_hashes.items()}
    actual = {name: value.lower() for name, value in source_hashes.items()}
    if actual != expected:
        raise ValueError(
            f"source workbook contract mismatch: expected {expected!r}, got {actual!r}"
        )


def _repair_registered_sentinel(
    points: dict[datetime, SourceHeatPoint], spec: HeatBuildSpec
) -> None:
    timestamp = spec.sentinel_timestamp
    point = points.get(timestamp)
    if point is None:
        if spec.enforce_source_contract:
            raise ValueError("registered sentinel timestamp is absent")
        return
    raw = point.raw
    is_registered = (
        raw.oldcity_gj_per_h == spec.sentinel_oldcity_heat
        and raw.oldcity_flow == spec.sentinel_oldcity_flow
    )
    if not is_registered:
        if spec.enforce_source_contract:
            raise ValueError("registered sentinel does not match its locked signature")
        return
    before = points.get(timestamp - timedelta(minutes=10))
    after = points.get(timestamp + timedelta(minutes=10))
    if before is None or after is None:
        raise ValueError("registered sentinel requires exact +/-10 minute neighbors")
    if any(
        abs(value) >= spec.sentinel_abs_threshold
        for neighbor in (before, after)
        for value in neighbor.repaired.values
    ):
        raise ValueError("registered sentinel neighbors must be valid")
    repaired = replace(
        raw,
        oldcity_gj_per_h=(
            before.repaired.oldcity_gj_per_h + after.repaired.oldcity_gj_per_h
        )
        / 2.0,
        oldcity_flow=(before.repaired.oldcity_flow + after.repaired.oldcity_flow)
        / 2.0,
    )
    points[timestamp] = replace(
        point,
        repaired=repaired,
        zero_sensitivity=repaired,
        flags=point.flags | {HeatQualityFlag.SENTINEL_INTERPOLATED},
    )


def _reject_unregistered_sentinels(
    points: Mapping[datetime, SourceHeatPoint], spec: HeatBuildSpec
) -> None:
    for timestamp, point in points.items():
        extreme_fields = {
            name
            for name in HEAT_VALUE_FIELDS
            if abs(getattr(point.raw, name)) >= spec.sentinel_abs_threshold
        }
        if not extreme_fields:
            continue
        registered = (
            timestamp == spec.sentinel_timestamp
            and extreme_fields
            == {"oldcity_gj_per_h", "oldcity_flow"}
            and point.raw.oldcity_gj_per_h == spec.sentinel_oldcity_heat
            and point.raw.oldcity_flow == spec.sentinel_oldcity_flow
        )
        if not registered:
            raise ValueError(
                f"unregistered sentinel at {timestamp.isoformat()}: "
                f"{sorted(extreme_fields)!r}"
            )


def _classify_point(point: SourceHeatPoint) -> SourceHeatPoint:
    signals = point.repaired
    dongfang_heat_negative = signals.dongfang_gj_per_h < 0.0
    dongfang_flow_negative = signals.dongfang_flow < 0.0
    if dongfang_heat_negative and not dongfang_flow_negative:
        raise ValueError(
            "negative Dongfang heat requires negative flow at "
            f"{point.timestamp.isoformat()}"
        )
    flags = set(point.flags)
    if dongfang_heat_negative:
        flags.add(HeatQualityFlag.SIGNED_REVERSE_FLOW)
    elif dongfang_flow_negative:
        flags.add(HeatQualityFlag.DONGFANG_SIGN_MISMATCH)
    if signals.resident_gj_per_h < 0.0:
        flags.add(HeatQualityFlag.RESIDENT_NEGATIVE)
    if all(value == 0.0 for value in signals.values):
        flags.add(HeatQualityFlag.ALL_SIGNAL_ZERO)
    return replace(point, flags=frozenset(flags))


def _apply_zero_segment_sensitivity(
    points: dict[datetime, SourceHeatPoint], spec: HeatBuildSpec
) -> None:
    if spec.zero_segment_start is None and spec.zero_segment_end is None:
        return
    if spec.zero_segment_start is None or spec.zero_segment_end is None:
        raise ValueError("zero segment start and end must be provided together")
    if spec.zero_segment_end < spec.zero_segment_start:
        raise ValueError("zero segment end precedes start")
    duration = spec.zero_segment_end - spec.zero_segment_start
    if duration.total_seconds() % 600 != 0:
        raise ValueError("zero segment endpoints must lie on the ten-minute grid")
    target_count = int(duration.total_seconds() // 600) + 1
    if spec.enforce_source_contract and target_count != 226:
        raise ValueError("formal zero-imputation segment must contain 226 points")

    for index in range(target_count):
        timestamp = spec.zero_segment_start + timedelta(minutes=10 * index)
        target = points.get(timestamp)
        if target is None:
            raise ValueError(
                f"registered zero-imputation target is missing at {timestamp.isoformat()}"
            )
        if HeatQualityFlag.ALL_SIGNAL_ZERO not in target.flags:
            raise ValueError(
                f"registered zero-imputation target is not all-zero at "
                f"{timestamp.isoformat()}"
            )
        donors: list[SourceHeatPoint] = []
        for offset_days in (-14, -7, 7, 14):
            donor_timestamp = timestamp + timedelta(days=offset_days)
            donor = points.get(donor_timestamp)
            invalid = (
                donor is None
                or HeatQualityFlag.ALL_SIGNAL_ZERO in donor.flags
                or HeatQualityFlag.SENTINEL_INTERPOLATED in donor.flags
            )
            if invalid:
                raise ValueError(
                    f"invalid zero-imputation donor at {donor_timestamp.isoformat()} "
                    f"for target {timestamp.isoformat()}"
                )
            donors.append(donor)
        imputed = HeatSignals(
            *(
                float(median(getattr(donor.repaired, field_name) for donor in donors))
                for field_name in HEAT_VALUE_FIELDS
            )
        )
        points[timestamp] = replace(
            target,
            zero_sensitivity=imputed,
            flags=target.flags | {HeatQualityFlag.ZERO_SEGMENT_IMPUTED},
        )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _aggregate_hourly(
    grid_points: tuple[SourceHeatPoint, ...], spec: HeatBuildSpec
) -> tuple[HourlyHeatPoint, ...]:
    groups: dict[datetime, list[SourceHeatPoint]] = defaultdict(list)
    for point in grid_points:
        hour = point.timestamp.replace(minute=0, second=0, microsecond=0)
        groups[hour].append(point)

    hourly: list[HourlyHeatPoint] = []
    expected_minutes = [0, 10, 20, 30, 40, 50]
    for timestamp in sorted(groups):
        points = sorted(groups[timestamp], key=lambda point: point.timestamp)
        complete = (
            len(points) == 6
            and [point.timestamp.minute for point in points] == expected_minutes
        )
        if not complete:
            if spec.enforce_complete_grid:
                raise ValueError(
                    f"hour {timestamp.isoformat()} does not contain six grid samples"
                )
            continue
        repaired_means = {
            field_name: _mean(
                [getattr(point.repaired, field_name) for point in points]
            )
            for field_name in HEAT_VALUE_FIELDS
        }
        hourly.append(
            HourlyHeatPoint(
                timestamp=timestamp,
                **repaired_means,
                heat_net_mw=_mean([point.heat_net_mw for point in points]),
                heat_forward_mw=_mean(
                    [point.heat_forward_mw for point in points]
                ),
                heat_zero_sensitivity_mw=_mean(
                    [point.heat_zero_sensitivity_mw for point in points]
                ),
                zero_sensitivity=HeatSignals(
                    *(
                        _mean(
                            [
                                getattr(point.zero_sensitivity, field_name)
                                for point in points
                            ]
                        )
                        for field_name in HEAT_VALUE_FIELDS
                    )
                ),
                source_sample_count=6,
                flag_counts={
                    flag: int(sum(flag in point.flags for point in points))
                    for flag in HeatQualityFlag
                },
            )
        )
    return tuple(hourly)


def _quality_counts(
    grid_points: tuple[SourceHeatPoint, ...],
) -> dict[HeatQualityFlag, int]:
    """Count canonical ten-minute rows carrying each quality flag."""

    return {
        flag: sum(flag in point.flags for point in grid_points)
        for flag in HeatQualityFlag
    }


def _validate_formal_signature(
    audit: HeatDatasetAudit,
    ledger: list[SourceHeatPoint],
    grid_points: tuple[SourceHeatPoint, ...],
    hourly_points: tuple[HourlyHeatPoint, ...],
    spec: HeatBuildSpec,
) -> None:
    if not spec.enforce_source_contract:
        return
    expected_scalars = {
        "source_row_count": spec.expected_source_row_count,
        "canonical_count": spec.expected_canonical_count,
        "hourly_count": spec.expected_hourly_count,
        "duplicate_extra_count": spec.expected_duplicate_extra_count,
        "non_grid_excluded_count": spec.expected_non_grid_excluded_count,
        "negative_net_hour_count": spec.expected_negative_net_hour_count,
    }
    for field_name, expected in expected_scalars.items():
        actual = getattr(audit, field_name)
        if actual != expected:
            raise ValueError(
                f"formal heat signature mismatch for {field_name}: "
                f"expected {expected}, got {actual}"
            )
    expected_flags = {
        HeatQualityFlag.SENTINEL_INTERPOLATED: spec.expected_sentinel_count,
        HeatQualityFlag.SIGNED_REVERSE_FLOW: spec.expected_reverse_flow_count,
        HeatQualityFlag.RESIDENT_NEGATIVE: spec.expected_resident_negative_count,
        HeatQualityFlag.ALL_SIGNAL_ZERO: spec.expected_all_signal_zero_count,
        HeatQualityFlag.ZERO_SEGMENT_IMPUTED: spec.expected_zero_segment_imputed_count,
        HeatQualityFlag.DONGFANG_SIGN_MISMATCH: len(
            spec.expected_dongfang_sign_mismatch_timestamps
        ),
    }
    for flag, expected in expected_flags.items():
        actual = audit.flag_counts[flag]
        if actual != expected:
            raise ValueError(
                f"formal heat signature mismatch for {flag.value}: "
                f"expected {expected}, got {actual}"
            )
    mismatch_timestamps = tuple(
        point.timestamp
        for point in grid_points
        if HeatQualityFlag.DONGFANG_SIGN_MISMATCH in point.flags
    )
    if mismatch_timestamps != spec.expected_dongfang_sign_mismatch_timestamps:
        raise ValueError(
            "formal heat signature mismatch for Dongfang sign-mismatch "
            f"timestamps: expected {spec.expected_dongfang_sign_mismatch_timestamps!r}, "
            f"got {mismatch_timestamps!r}"
        )
    timestamp_signatures = (
        (
            "duplicate-extra",
            tuple(
                point.timestamp
                for point in ledger
                if point.disposition is SourceDisposition.DUPLICATE
            ),
            spec.expected_duplicate_extra_timestamps,
        ),
        (
            "non-grid-excluded",
            tuple(
                point.timestamp
                for point in ledger
                if point.disposition is SourceDisposition.NON_GRID_EXCLUDED
            ),
            spec.expected_non_grid_excluded_timestamps,
        ),
        (
            "negative-net-hour",
            tuple(
                point.timestamp
                for point in hourly_points
                if point.heat_net_mw < 0.0
            ),
            spec.expected_negative_net_hour_timestamps,
        ),
    )
    for name, actual, expected in timestamp_signatures:
        if actual != expected:
            raise ValueError(
                f"formal heat signature mismatch for {name} timestamps: "
                f"expected {expected!r}, got {actual!r}"
            )
    for field_name, expected in (
        ("annual_net_gj", spec.expected_annual_net_gj),
        ("annual_forward_gj", spec.expected_annual_forward_gj),
    ):
        actual = getattr(audit, field_name)
        if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError(
                f"formal heat signature mismatch for {field_name}: "
                f"expected {expected:.6f}, got {actual:.6f}"
            )


def build_heat_dataset(
    sources: HeatSourceBundle, *, spec: HeatBuildSpec
) -> BuiltHeatDataset:
    """Build the canonical ten-minute dataset while retaining a source ledger."""

    parsed = [parse_heat_workbook(path) for path in sources.paths]
    issues = [issue for workbook in parsed for issue in workbook.issues]
    if issues:
        first = issues[0]
        raise ValueError(
            f"heat source parse issue at {first.path}:{first.row_number}: {first.reason}"
        )
    source_roles = ("first_half", "second_half")
    source_identities = tuple(
        HeatSourceIdentity(
            role=source_roles[index],
            name=workbook.path.name,
            sha256=hashlib.sha256(workbook.path.read_bytes()).hexdigest(),
        )
        for index, workbook in enumerate(parsed)
    )
    source_hashes = {
        identity.name: identity.sha256 for identity in source_identities
    }
    if len(source_hashes) != len(source_identities):
        raise ValueError("heat source workbook names must be unique")
    _validate_source_hashes(source_hashes, spec)

    start = datetime(spec.year, 1, 1)
    end = datetime(spec.year + 1, 1, 1)
    ledger: list[SourceHeatPoint] = []
    canonical: dict[datetime, SourceHeatPoint] = {}
    canonical_ledger_index: dict[datetime, int] = {}
    for workbook in parsed:
        for record in workbook.records:
            if not start <= record.timestamp < end:
                continue
            if not _is_grid_point(record.timestamp):
                ledger.append(
                    _source_point(
                        record,
                        included=False,
                        canonical=False,
                        disposition=SourceDisposition.NON_GRID_EXCLUDED,
                        flags=frozenset({HeatQualityFlag.NON_GRID_EXCLUDED}),
                    )
                )
                continue
            existing = canonical.get(record.timestamp)
            if existing is None:
                point = _source_point(
                    record,
                    included=True,
                    canonical=True,
                    disposition=SourceDisposition.CANONICAL,
                )
                canonical[record.timestamp] = point
                canonical_ledger_index[record.timestamp] = len(ledger)
                ledger.append(point)
                continue
            if existing.raw.values != HeatSignals.from_record(record).values:
                raise ConflictingDuplicateError(
                    f"Conflicting heat records at {record.timestamp.isoformat()}"
                )
            first_index = canonical_ledger_index[record.timestamp]
            first = replace(
                ledger[first_index],
                flags=ledger[first_index].flags
                | {HeatQualityFlag.SOURCE_DUPLICATE},
            )
            ledger[first_index] = first
            canonical[record.timestamp] = first
            ledger.append(
                _source_point(
                    record,
                    included=False,
                    canonical=False,
                    disposition=SourceDisposition.DUPLICATE,
                    flags=frozenset({HeatQualityFlag.SOURCE_DUPLICATE}),
                )
            )

    if spec.enforce_complete_grid:
        expected = int((end - start).total_seconds() // 600)
        if len(canonical) != expected:
            raise ValueError(
                f"strict ten-minute grid requires {expected} points, got {len(canonical)}"
            )

    _reject_unregistered_sentinels(canonical, spec)
    _repair_registered_sentinel(canonical, spec)
    canonical = {
        timestamp: _classify_point(point)
        for timestamp, point in canonical.items()
    }
    _apply_zero_segment_sensitivity(canonical, spec)
    for timestamp, point in canonical.items():
        ledger_index = canonical_ledger_index[timestamp]
        ledger[ledger_index] = point

    grid_points = tuple(canonical[timestamp] for timestamp in sorted(canonical))
    hourly_points = _aggregate_hourly(grid_points, spec)
    flag_counts = _quality_counts(grid_points)
    annual_net_gj = sum(point.heat_net_mw * 3.6 for point in hourly_points)
    annual_forward_gj = sum(
        point.heat_forward_mw * 3.6 for point in hourly_points
    )
    annual_zero_sensitivity_gj = sum(
        point.heat_zero_sensitivity_mw * 3.6 for point in hourly_points
    )
    audit = HeatDatasetAudit(
        source_row_count=len(ledger),
        canonical_count=len(grid_points),
        hourly_count=len(hourly_points),
        flag_counts=flag_counts,
        source_hashes=source_hashes,
        duplicate_timestamp_count=len(
            {
                point.timestamp
                for point in ledger
                if HeatQualityFlag.SOURCE_DUPLICATE in point.flags
            }
        ),
        duplicate_extra_count=sum(
            point.disposition is SourceDisposition.DUPLICATE for point in ledger
        ),
        duplicate_ledger_flagged_row_count=sum(
            HeatQualityFlag.SOURCE_DUPLICATE in point.flags for point in ledger
        ),
        duplicate_canonical_flagged_count=sum(
            HeatQualityFlag.SOURCE_DUPLICATE in point.flags
            for point in grid_points
        ),
        non_grid_excluded_count=sum(
            point.disposition is SourceDisposition.NON_GRID_EXCLUDED
            for point in ledger
        ),
        negative_net_hour_count=sum(
            point.heat_net_mw < 0.0 for point in hourly_points
        ),
        annual_net_gj=annual_net_gj,
        annual_forward_gj=annual_forward_gj,
        annual_zero_sensitivity_gj=annual_zero_sensitivity_gj,
        formal_ready=False,
    )
    _validate_formal_signature(audit, ledger, grid_points, hourly_points, spec)
    if spec.enforce_source_contract and spec.enforce_complete_grid:
        audit = replace(audit, formal_ready=True)
    return BuiltHeatDataset(
        tuple(ledger),
        grid_points,
        hourly_points,
        audit,
        spec,
        spec.registry_version,
        source_identities,
    )


def _number(value: float) -> str:
    if abs(value) < 0.5e-12:
        value = 0.0
    return f"{value:.12f}"


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _flags(flags: frozenset[HeatQualityFlag]) -> str:
    return ";".join(sorted(flag.value for flag in flags))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _round_json_numbers(value: object) -> object:
    """Round every JSON float to twelve decimal places before serialization."""

    if isinstance(value, float):
        rounded = round(value, 12)
        return 0.0 if rounded == 0.0 else rounded
    if isinstance(value, dict):
        return {key: _round_json_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round_json_numbers(item) for item in value]
    return value


def _write_source_ledger(dataset: BuiltHeatDataset, path: Path) -> None:
    signal_columns = [
        f"{prefix}_{field_name}"
        for prefix in ("raw", "repaired", "zero_sensitivity")
        for field_name in HEAT_VALUE_FIELDS
    ]
    fieldnames = [
        "timestamp",
        "source_file",
        "source_sha256",
        "source_sheet",
        "source_row",
        "source_raw_cell",
        "included",
        "canonical",
        "disposition",
        "flags",
        *signal_columns,
        "heat_net_mw",
        "heat_forward_mw",
        "heat_zero_sensitivity_mw",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for point in dataset.source_ledger:
            row: dict[str, str | int] = {
                "timestamp": _timestamp(point.timestamp),
                "source_file": point.source_path.name,
                "source_sha256": point.source_sha256,
                "source_sheet": point.source_sheet,
                "source_row": point.source_row,
                "source_raw_cell": point.source_raw_cell,
                "included": int(point.included),
                "canonical": int(point.canonical),
                "disposition": point.disposition.value,
                "flags": _flags(point.flags),
                "heat_net_mw": _number(point.heat_net_mw),
                "heat_forward_mw": _number(point.heat_forward_mw),
                "heat_zero_sensitivity_mw": _number(
                    point.heat_zero_sensitivity_mw
                ),
            }
            for prefix, signals in (
                ("raw", point.raw),
                ("repaired", point.repaired),
                ("zero_sensitivity", point.zero_sensitivity),
            ):
                row.update(
                    {
                        f"{prefix}_{field_name}": _number(
                            getattr(signals, field_name)
                        )
                        for field_name in HEAT_VALUE_FIELDS
                    }
                )
            writer.writerow(row)


def _write_hourly(dataset: BuiltHeatDataset, path: Path) -> None:
    fieldnames = [
        "timestamp",
        *HEAT_VALUE_FIELDS,
        *(f"zero_sensitivity_{name}" for name in HEAT_VALUE_FIELDS),
        "heat_net_mw",
        "heat_forward_mw",
        "heat_zero_sensitivity_mw",
        "source_sample_count",
        *(f"{flag.value}_count" for flag in HeatQualityFlag),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for point in dataset.hourly_points:
            row: dict[str, str | int] = {
                "timestamp": _timestamp(point.timestamp),
                **{
                    name: _number(getattr(point, name))
                    for name in HEAT_VALUE_FIELDS
                },
                **{
                    f"zero_sensitivity_{name}": _number(
                        getattr(point.zero_sensitivity, name)
                    )
                    for name in HEAT_VALUE_FIELDS
                },
                "heat_net_mw": _number(point.heat_net_mw),
                "heat_forward_mw": _number(point.heat_forward_mw),
                "heat_zero_sensitivity_mw": _number(
                    point.heat_zero_sensitivity_mw
                ),
                "source_sample_count": point.source_sample_count,
                **{
                    f"{flag.value}_count": point.flag_counts[flag]
                    for flag in HeatQualityFlag
                },
            }
            writer.writerow(row)


def write_heat_dataset(
    dataset: BuiltHeatDataset, output_dir: str | Path
) -> ExportManifest:
    """Write deterministic source-ledger, hourly, and manifest artifacts."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    ledger_path = directory / f"e0b_heat_source_ledger_{dataset.spec.year}.csv"
    hourly_path = directory / f"e0b_heat_hourly_{dataset.spec.year}.csv"
    manifest_path = directory / "manifest.json"
    _write_source_ledger(dataset, ledger_path)
    _write_hourly(dataset, hourly_path)
    output_sha256 = {
        ledger_path.name: _sha256(ledger_path),
        hourly_path.name: _sha256(hourly_path),
    }
    audit = dataset.audit
    hourly_values = {
        "heat_net_mw": [point.heat_net_mw for point in dataset.hourly_points],
        "heat_forward_mw": [
            point.heat_forward_mw for point in dataset.hourly_points
        ],
        "heat_zero_sensitivity_mw": [
            point.heat_zero_sensitivity_mw for point in dataset.hourly_points
        ],
    }
    zero_signature_points = [
        point
        for point in dataset.grid_points
        if HeatQualityFlag.ALL_SIGNAL_ZERO in point.flags
        and HeatQualityFlag.ZERO_SEGMENT_IMPUTED in point.flags
    ]
    spec = dataset.spec
    zero_enabled = (
        spec.zero_segment_start is not None and spec.zero_segment_end is not None
    )
    if zero_enabled:
        zero_point_count = int(
            (spec.zero_segment_end - spec.zero_segment_start).total_seconds() // 600
        ) + 1
    else:
        zero_point_count = 0
    manifest = {
        "schema": "tes_bess_boundary.e0b_heat_dataset.v2",
        "registry_version": dataset.registry_version,
        "year": spec.year,
        "formal_ready": audit.formal_ready,
        "sources": [
            {
                "role": identity.role,
                "name": identity.name,
                "sha256": identity.sha256,
            }
            for identity in dataset.source_identities
        ],
        "source_files": dict(sorted(audit.source_hashes.items())),
        "outputs": {
            ledger_path.name: {
                "rows": audit.source_row_count,
                "sha256": output_sha256[ledger_path.name],
            },
            hourly_path.name: {
                "rows": audit.hourly_count,
                "sha256": output_sha256[hourly_path.name],
            },
        },
        "counts": {
            "source_rows": audit.source_row_count,
            "canonical_ten_minute_points": audit.canonical_count,
            "hourly_points": audit.hourly_count,
            "duplicate_extra_rows": audit.duplicate_extra_count,
            "non_grid_excluded_rows": audit.non_grid_excluded_count,
            "negative_net_hours": audit.negative_net_hour_count,
            "duplicates": {
                "timestamp_count": audit.duplicate_timestamp_count,
                "extra_rows": audit.duplicate_extra_count,
                "ledger_flagged_rows": audit.duplicate_ledger_flagged_row_count,
                "canonical_flagged_rows": audit.duplicate_canonical_flagged_count,
            },
            "canonical_flagged_rows_by_quality": {
                flag.value: audit.flag_counts[flag] for flag in HeatQualityFlag
            },
        },
        "annual_energy_gj": {
            "heat_net": audit.annual_net_gj,
            "heat_forward": audit.annual_forward_gj,
            "heat_zero_sensitivity": audit.annual_zero_sensitivity_gj,
        },
        "hourly_ranges_mw": {
            name: {
                "min": min(values) if values else None,
                "max": max(values) if values else None,
            }
            for name, values in hourly_values.items()
        },
        "observed_signatures": {
            "zero_segment": {
                "predicate": "all_five_signals_zero and zero_segment_imputed",
                "count": len(zero_signature_points),
                "start": (
                    _timestamp(zero_signature_points[0].timestamp)
                    if zero_signature_points
                    else None
                ),
                "end": (
                    _timestamp(zero_signature_points[-1].timestamp)
                    if zero_signature_points
                    else None
                ),
            }
        },
        "units": {
            "branch_heat": "GJ/h",
            "flow": "t/h",
            "heat_series": "MWth",
            "annual_energy": "GJ",
        },
        "contract": {
            "canonicalization": {
                "grid_minutes": 10,
                "duplicate_resolution": (
                    "first_row_wins_when_all_five_signals_are_identical"
                ),
                "conflicting_duplicate_policy": "error",
                "non_grid_policy": (
                    "retain_in_source_ledger_and_exclude_from_canonical"
                ),
            },
            "sentinel_repair": {
                "timestamp": _timestamp(spec.sentinel_timestamp),
                "raw_signature": {
                    "oldcity_gj_per_h": spec.sentinel_oldcity_heat,
                    "oldcity_flow": spec.sentinel_oldcity_flow,
                },
                "repair_fields": ["oldcity_gj_per_h", "oldcity_flow"],
                "neighbor_offsets_minutes": [-10, 10],
                "operation": "arithmetic_mean",
                "unregistered_abs_threshold": spec.sentinel_abs_threshold,
            },
            "zero_sensitivity": {
                "enabled": zero_enabled,
                "interval": {
                    "start": (
                        _timestamp(spec.zero_segment_start)
                        if spec.zero_segment_start is not None
                        else None
                    ),
                    "end": (
                        _timestamp(spec.zero_segment_end)
                        if spec.zero_segment_end is not None
                        else None
                    ),
                    "closure": "both",
                },
                "expected_point_count": zero_point_count,
                "donor_day_offsets": [-14, -7, 7, 14],
                "aggregation": "fieldwise_median",
                "donor_rejections": [
                    "missing",
                    "all_five_signals_zero",
                    "sentinel_interpolated",
                ],
            },
            "sign_classification": {
                "signed_reverse_flow": {
                    "predicate": (
                        "dongfang_gj_per_h < 0 and dongfang_flow < 0"
                    ),
                    "registry_expected_count": spec.expected_reverse_flow_count,
                },
                "dongfang_sign_mismatch": {
                    "predicate": (
                        "dongfang_gj_per_h >= 0 and dongfang_flow < 0"
                    ),
                    "registry_expected_count": len(
                        spec.expected_dongfang_sign_mismatch_timestamps
                    ),
                    "registry_expected_timestamps": [
                        _timestamp(timestamp)
                        for timestamp in spec.expected_dongfang_sign_mismatch_timestamps
                    ],
                },
            },
            "negative_net_hour_signature": {
                "predicate": "heat_net_mw < 0",
                "registry_expected_count": spec.expected_negative_net_hour_count,
                "registry_expected_timestamps": [
                    _timestamp(timestamp)
                    for timestamp in spec.expected_negative_net_hour_timestamps
                ],
            },
            "series": {
                "net": (
                    "signed sum of three repaired heat branches divided by 3.6"
                ),
                "forward": (
                    "sum of branch-level max(value, 0) divided by 3.6"
                ),
                "hourly": "arithmetic mean of six ten-minute rate samples",
            },
        },
    }
    manifest = _round_json_numbers(manifest)
    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    output_sha256[manifest_path.name] = _sha256(manifest_path)
    return ExportManifest(
        ledger_path=ledger_path,
        hourly_path=hourly_path,
        manifest_path=manifest_path,
        output_sha256=output_sha256,
    )
