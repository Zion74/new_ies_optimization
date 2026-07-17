from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable


class DataQualityReporter:
    """Generate lightweight readiness reports for scenario profile files."""

    @staticmethod
    def check_monthly_typical_profiles(
        path: str | Path,
        required_profile_types: Iterable[str],
    ) -> dict[str, Any]:
        path = Path(path)
        required_types = [str(item) for item in required_profile_types]
        expected_keys = {
            (month, hour, profile_type)
            for month in range(1, 13)
            for hour in range(24)
            for profile_type in required_types
        }
        errors: list[str] = []
        warnings: list[str] = []
        rows: list[dict[str, Any]] = []

        if not path.exists():
            return {
                "status": "blocked",
                "expected_rows": len(expected_keys),
                "actual_rows": 0,
                "errors": [f"profile file does not exist: {path}"],
                "warnings": [],
            }

        with path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = set(reader.fieldnames or [])
            profile_column = "profile_type" if "profile_type" in fieldnames else "demand_id"
            required_columns = {"month", "hour", "value", "unit", profile_column}
            missing_columns = sorted(required_columns - fieldnames)
            if missing_columns:
                errors.append(f"missing required columns: {', '.join(missing_columns)}")
                return _report(len(expected_keys), 0, errors, warnings)
            rows = list(reader)

        hour_values = []
        for row_index, row in enumerate(rows, start=2):
            hour = _parse_int(row.get("hour"), "hour", row_index, errors)
            if hour is not None:
                hour_values.append(hour)
        hour_range = range(1, 25) if 24 in hour_values and 0 not in hour_values else range(24)
        expected_keys = {
            (month, hour, profile_type)
            for month in range(1, 13)
            for hour in hour_range
            for profile_type in required_types
        }

        seen: set[tuple[int, int, str]] = set()
        for row_index, row in enumerate(rows, start=2):
            month = _parse_int(row.get("month"), "month", row_index, errors)
            hour = _parse_int(row.get("hour"), "hour", row_index, errors)
            profile_type = str(row.get(profile_column) or "").strip()
            _parse_float(row.get("value"), "value", row_index, errors)

            if not profile_type:
                errors.append(f"row {row_index}: {profile_column} is empty")
                continue
            if month is None or hour is None:
                continue
            key = (month, hour, profile_type)
            if key in seen:
                errors.append(f"duplicate profile row: month={month}, hour={hour}, profile_type={profile_type}")
            seen.add(key)
            if profile_type not in required_types:
                warnings.append(f"row {row_index}: profile_type {profile_type} is not required")
            if month < 1 or month > 12:
                errors.append(f"row {row_index}: month out of range: {month}")
            if hour not in hour_range:
                errors.append(f"row {row_index}: hour out of range: {hour}")

        missing = sorted(expected_keys - seen)
        if missing:
            sample = ", ".join(
                f"month={month}/hour={hour}/type={profile_type}"
                for month, hour, profile_type in missing[:5]
            )
            errors.append(f"missing {len(missing)} required profile rows; examples: {sample}")

        return _report(len(expected_keys), len(rows), errors, warnings)


def _report(
    expected_rows: int,
    actual_rows: int,
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "status": "ok" if not errors else "blocked",
        "expected_rows": expected_rows,
        "actual_rows": actual_rows,
        "errors": errors,
        "warnings": warnings,
    }


def _parse_int(value: Any, field: str, row_index: int, errors: list[str]) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        errors.append(f"row {row_index}: non-numeric {field}: {value!r}")
        return None


def _parse_float(value: Any, field: str, row_index: int, errors: list[str]) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        errors.append(f"row {row_index}: non-numeric {field}: {value!r}")
        return None
