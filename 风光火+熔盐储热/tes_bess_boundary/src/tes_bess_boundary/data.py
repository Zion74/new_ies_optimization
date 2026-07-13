"""Strict structural audits for the Yangling hourly input files."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class CsvProfile:
    """Expected schema and identities for one hourly CSV family."""

    name: str
    required_columns: tuple[str, ...]
    numeric_columns: tuple[str, ...]
    nonnegative_columns: tuple[str, ...]
    bounded_columns: Mapping[str, tuple[float, float]]
    electric_total_column: str
    electric_component_columns: tuple[str, str]
    heat_total_column: str | None = None
    heat_component_columns: tuple[str, ...] = ()
    heat_component_divisor: float = 1.0


PLANNING_PROFILE = CsvProfile(
    name="planning",
    required_columns=(
        "ts",
        "P1",
        "P2",
        "P_elec_MW",
        "heat_demand_MWth",
        "pv_cf",
        "wind_cf_dingbian",
        "price_sell",
        "price_buy",
    ),
    numeric_columns=(
        "P1",
        "P2",
        "P_elec_MW",
        "heat_demand_MWth",
        "pv_cf",
        "wind_cf_dingbian",
        "price_sell",
        "price_buy",
    ),
    nonnegative_columns=(
        "P1",
        "P2",
        "P_elec_MW",
        "heat_demand_MWth",
        "pv_cf",
        "wind_cf_dingbian",
        "price_sell",
        "price_buy",
    ),
    bounded_columns={"pv_cf": (0.0, 1.0), "wind_cf_dingbian": (0.0, 1.0)},
    electric_total_column="P_elec_MW",
    electric_component_columns=("P1", "P2"),
)

OPERATIONS_PROFILE = CsvProfile(
    name="operations",
    required_columns=(
        "ts",
        "P1",
        "P2",
        "P_total",
        "heat_total_MW",
        "居民供热",
        "东方专业",
        "老城区",
    ),
    numeric_columns=(
        "P1",
        "P2",
        "P_total",
        "heat_total_MW",
        "居民供热",
        "东方专业",
        "老城区",
    ),
    nonnegative_columns=(
        "P1",
        "P2",
        "P_total",
        "heat_total_MW",
        "居民供热",
        "东方专业",
        "老城区",
    ),
    bounded_columns={},
    electric_total_column="P_total",
    electric_component_columns=("P1", "P2"),
    heat_total_column="heat_total_MW",
    heat_component_columns=("居民供热", "东方专业", "老城区"),
    heat_component_divisor=3.6,
)


@dataclass(frozen=True)
class AuditIssue:
    code: str
    message: str
    row_number: int | None = None


@dataclass(frozen=True)
class DataAudit:
    path: Path
    profile: str
    row_count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    issues: tuple[AuditIssue, ...]
    metrics: Mapping[str, float]

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def issue_codes(self) -> frozenset[str]:
        return frozenset(issue.code for issue in self.issues)


def _expected_hours(year: int) -> int:
    start = datetime(year, 1, 1)
    end = datetime(year + 1, 1, 1)
    return int((end - start).total_seconds() // 3600)


def _parse_timestamp(raw: str) -> datetime:
    return datetime.fromisoformat(raw.strip())


def audit_csv(
    path: str | Path,
    profile: CsvProfile,
    *,
    year: int,
    tolerance: float = 1e-8,
) -> DataAudit:
    """Audit schema, hourly coverage, numeric bounds, and energy identities.

    This is a structural audit of the generated hourly file. It does not certify
    that the upstream 10-minute source parser was scientifically correct.
    """

    csv_path = Path(path)
    issues: list[AuditIssue] = []
    metrics: dict[str, float] = {}

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        missing = [column for column in profile.required_columns if column not in fieldnames]
        if missing:
            issues.append(
                AuditIssue(
                    "missing_column",
                    f"Missing required columns: {', '.join(missing)}",
                )
            )
        rows = list(reader)

    timestamps: list[datetime] = []
    numeric_rows: list[dict[str, float]] = []
    for row_number, row in enumerate(rows, start=2):
        try:
            timestamp = _parse_timestamp(row.get("ts", ""))
        except (TypeError, ValueError):
            issues.append(
                AuditIssue("invalid_timestamp", "Timestamp is not ISO-compatible", row_number)
            )
        else:
            timestamps.append(timestamp)

        parsed: dict[str, float] = {}
        for column in profile.numeric_columns:
            raw = row.get(column)
            try:
                value = float(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                issues.append(
                    AuditIssue(
                        "invalid_numeric",
                        f"{column} is not numeric",
                        row_number,
                    )
                )
                continue
            if not math.isfinite(value):
                issues.append(
                    AuditIssue(
                        "invalid_numeric",
                        f"{column} is not finite",
                        row_number,
                    )
                )
                continue
            parsed[column] = value
            if column in profile.nonnegative_columns and value < -tolerance:
                issues.append(
                    AuditIssue(
                        "negative_value",
                        f"{column} must be non-negative",
                        row_number,
                    )
                )
            if column in profile.bounded_columns:
                lower, upper = profile.bounded_columns[column]
                if value < lower - tolerance or value > upper + tolerance:
                    issues.append(
                        AuditIssue(
                            "out_of_bounds",
                            f"{column} must lie in [{lower}, {upper}]",
                            row_number,
                        )
                    )
        numeric_rows.append(parsed)

    expected_count = _expected_hours(year)
    if len(rows) != expected_count:
        issues.append(
            AuditIssue(
                "row_count",
                f"Expected {expected_count} hourly rows for {year}, found {len(rows)}",
            )
        )

    if len(timestamps) != len(set(timestamps)):
        issues.append(AuditIssue("duplicate_timestamp", "Duplicate timestamps detected"))

    expected_start = datetime(year, 1, 1)
    expected_end = datetime(year + 1, 1, 1) - timedelta(hours=1)
    if timestamps:
        if timestamps[0] != expected_start or timestamps[-1] != expected_end:
            issues.append(
                AuditIssue(
                    "timestamp_coverage",
                    f"Expected coverage {expected_start} through {expected_end}",
                )
            )
        if any(
            current - previous != timedelta(hours=1)
            for previous, current in zip(timestamps, timestamps[1:])
        ):
            issues.append(
                AuditIssue(
                    "timestamp_gap",
                    "Timestamps must be strictly increasing at one-hour intervals",
                )
            )

    electric_errors: list[float] = []
    heat_errors: list[float] = []
    for row in numeric_rows:
        p1, p2 = profile.electric_component_columns
        if all(
            column in row
            for column in (p1, p2, profile.electric_total_column)
        ):
            electric_errors.append(
                abs(row[profile.electric_total_column] - row[p1] - row[p2])
            )
        if (
            profile.heat_total_column
            and all(column in row for column in profile.heat_component_columns)
            and profile.heat_total_column in row
        ):
            component_total = (
                sum(row[column] for column in profile.heat_component_columns)
                / profile.heat_component_divisor
            )
            heat_errors.append(abs(row[profile.heat_total_column] - component_total))

    electric_max_error = max(electric_errors, default=math.inf)
    metrics["electric_total_max_abs_error_mw"] = electric_max_error
    if electric_max_error > tolerance:
        issues.append(
            AuditIssue(
                "electric_total_mismatch",
                f"Maximum electric total residual is {electric_max_error:.6g} MW",
            )
        )

    if profile.heat_total_column:
        heat_max_error = max(heat_errors, default=math.inf)
        metrics["heat_total_max_abs_error_mw"] = heat_max_error
        if heat_max_error > tolerance:
            issues.append(
                AuditIssue(
                    "heat_total_mismatch",
                    f"Maximum heat total residual is {heat_max_error:.6g} MW",
                )
            )

    return DataAudit(
        path=csv_path,
        profile=profile.name,
        row_count=len(rows),
        first_timestamp=timestamps[0] if timestamps else None,
        last_timestamp=timestamps[-1] if timestamps else None,
        issues=tuple(issues),
        metrics=metrics,
    )
