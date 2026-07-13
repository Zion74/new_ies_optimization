"""Explicit E0-B hourly heat interpretations at the E0-C demand boundary."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

from tes_bess_boundary.heat_dataset import HeatQualityFlag


FORMAL_MANIFEST_SCHEMA = "tes_bess_boundary.e0b_heat_dataset.v2"
CANDIDATE_HEAT_COLUMNS = (
    "heat_net_mw",
    "heat_forward_mw",
    "heat_zero_sensitivity_mw",
)
QUALITY_COUNT_COLUMNS = tuple(
    f"{flag.value}_count" for flag in HeatQualityFlag
)
_INTEGER_TOKEN = re.compile(r"[+-]?\d+")


class HeatDemandInterpretation(str, Enum):
    """Registered E0-B series and its E0-C non-negative demand rule."""

    NET_CLIPPED = "net_clipped"
    FORWARD = "forward"
    ZERO_SENSITIVITY_CLIPPED = "zero_sensitivity_clipped"


@dataclass(frozen=True)
class _InterpretationContract:
    source_column: str
    formula: str
    scientific_status: str
    description: str
    clips_negative_values: bool


_INTERPRETATION_CONTRACTS = {
    HeatDemandInterpretation.NET_CLIPPED: _InterpretationContract(
        source_column="heat_net_mw",
        formula="max(heat_net_mw, 0)",
        scientific_status="primary",
        description="minimum-intervention non-negative E0-C demand boundary",
        clips_negative_values=True,
    ),
    HeatDemandInterpretation.FORWARD: _InterpretationContract(
        source_column="heat_forward_mw",
        formula="heat_forward_mw",
        scientific_status="sensitivity",
        description="derived ten-minute branch-positive sensitivity",
        clips_negative_values=False,
    ),
    HeatDemandInterpretation.ZERO_SENSITIVITY_CLIPPED: _InterpretationContract(
        source_column="heat_zero_sensitivity_mw",
        formula="max(heat_zero_sensitivity_mw, 0)",
        scientific_status="sensitivity",
        description="registered 226-point zero-segment sensitivity",
        clips_negative_values=True,
    ),
}


@dataclass(frozen=True)
class HourlyWindow:
    """Exact half-open hourly selection requested from a validated source."""

    start: datetime
    hours: int

    def __post_init__(self) -> None:
        if not isinstance(self.start, datetime):
            raise ValueError("window start must be a datetime")
        if self.start.tzinfo is not None or (
            self.start.minute != 0
            or self.start.second != 0
            or self.start.microsecond != 0
        ):
            raise ValueError("window start must be a naive whole hour")
        if type(self.hours) is not int or self.hours <= 0:
            raise ValueError("window hours must be a positive integer")

    @property
    def end_exclusive(self) -> datetime:
        return self.start + timedelta(hours=self.hours)


@dataclass(frozen=True)
class HeatDemandAdapterSpec:
    """One explicit source interpretation and optional E0-C time window."""

    interpretation: HeatDemandInterpretation
    year: int = 2024
    window: HourlyWindow | None = None
    enforce_formal_contract: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.interpretation, HeatDemandInterpretation):
            raise ValueError("interpretation must use HeatDemandInterpretation")
        if type(self.year) is not int or not 1 <= self.year <= 9998:
            raise ValueError("year must be an integer between 1 and 9998")
        if self.window is not None and not isinstance(self.window, HourlyWindow):
            raise ValueError("window must be an HourlyWindow")
        if type(self.enforce_formal_contract) is not bool:
            raise ValueError("enforce_formal_contract must be a bool")
        if self.window is not None:
            year_start = datetime(self.year, 1, 1)
            next_year = datetime(self.year + 1, 1, 1)
            if not (
                year_start <= self.window.start < next_year
                and self.window.end_exclusive <= next_year
            ):
                raise ValueError("window must stay inside the selected year")


@dataclass(frozen=True)
class HeatDemandModification:
    """One auditable source-to-model change at the E0-B/E0-C boundary."""

    timestamp: datetime
    source_value_mw: float
    model_value_mw: float
    clipped_amount_mw: float


@dataclass(frozen=True)
class AdaptedHeatDemand:
    """Non-negative E0-C heat demand plus preserved upstream evidence."""

    timestamps: tuple[datetime, ...]
    source_values_mw: tuple[float, ...]
    values_mw: tuple[float, ...]
    full_source_modifications: tuple[HeatDemandModification, ...]
    window_modifications: tuple[HeatDemandModification, ...]
    spec: HeatDemandAdapterSpec
    source_column: str
    formula: str
    scientific_status: str
    interpretation_description: str
    source_csv_name: str
    source_csv_sha256: str
    source_manifest_name: str | None
    source_manifest_sha256: str | None
    full_source_row_count: int
    full_source_energy_before_mwh: float
    full_source_energy_after_mwh: float
    energy_before_mwh: float
    energy_after_mwh: float
    full_source_quality_count_sums: tuple[tuple[str, int], ...]
    quality_count_sums: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class HeatDemandExport:
    csv_path: Path
    manifest_path: Path
    output_sha256: dict[str, str]


@dataclass(frozen=True)
class _HourlySourceRow:
    timestamp: datetime
    candidate_values_mw: dict[str, float]
    quality_counts: tuple[int, ...]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expected_hours(year: int) -> int:
    return int(
        (datetime(year + 1, 1, 1) - datetime(year, 1, 1)).total_seconds()
        // 3600
    )


def _strict_integer(raw: object, *, column: str, row_number: int) -> int:
    token = raw if isinstance(raw, str) else ""
    if _INTEGER_TOKEN.fullmatch(token) is None:
        raise ValueError(
            f"{column} must be an integer at CSV data row {row_number}"
        )
    return int(token)


def _read_hourly_source(
    path: Path, *, spec: HeatDemandAdapterSpec
) -> tuple[_HourlySourceRow, ...]:
    required_columns = {
        "timestamp",
        "source_sample_count",
        *CANDIDATE_HEAT_COLUMNS,
        *QUALITY_COUNT_COLUMNS,
    }
    rows: list[_HourlySourceRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError("hourly CSV must contain a header")
        if len(fieldnames) != len(set(fieldnames)):
            raise ValueError("hourly CSV contains duplicate header names")
        missing_columns = sorted(required_columns.difference(fieldnames))
        if missing_columns:
            raise ValueError(
                "hourly CSV is missing required columns: "
                + ", ".join(missing_columns)
            )

        for row_number, row in enumerate(reader, start=1):
            if None in row:
                raise ValueError(
                    f"hourly CSV data row {row_number} has extra fields"
                )
            try:
                timestamp = datetime.fromisoformat(row["timestamp"])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"timestamp is invalid at CSV data row {row_number}"
                ) from error
            if timestamp.tzinfo is not None or (
                timestamp.minute != 0
                or timestamp.second != 0
                or timestamp.microsecond != 0
            ):
                raise ValueError("hourly timestamps must be naive whole hours")

            try:
                candidate_values = {
                    column: float(row[column]) for column in CANDIDATE_HEAT_COLUMNS
                }
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    "candidate heat columns must be finite numeric values"
                ) from error
            if not all(math.isfinite(value) for value in candidate_values.values()):
                raise ValueError("candidate heat columns must be finite")
            if candidate_values["heat_forward_mw"] < 0.0:
                raise ValueError("heat_forward_mw must be non-negative")

            sample_count = _strict_integer(
                row["source_sample_count"],
                column="source_sample_count",
                row_number=row_number,
            )
            if sample_count != 6:
                raise ValueError("source_sample_count must equal 6 for every hour")
            quality_counts: list[int] = []
            for column in QUALITY_COUNT_COLUMNS:
                count = _strict_integer(
                    row[column], column=column, row_number=row_number
                )
                if not 0 <= count <= 6:
                    raise ValueError(f"{column} must be between 0 and 6")
                quality_counts.append(count)

            rows.append(
                _HourlySourceRow(
                    timestamp=timestamp,
                    candidate_values_mw=candidate_values,
                    quality_counts=tuple(quality_counts),
                )
            )

    if not rows:
        raise ValueError("hourly CSV must contain at least one data row")
    if spec.enforce_formal_contract:
        expected_count = _expected_hours(spec.year)
        if len(rows) != expected_count:
            raise ValueError(
                f"formal hourly CSV must contain exactly {expected_count} rows"
            )
        start = datetime(spec.year, 1, 1)
        for index, row in enumerate(rows):
            expected_timestamp = start + timedelta(hours=index)
            if row.timestamp != expected_timestamp:
                raise ValueError(
                    "formal hourly CSV must be the complete strictly ordered "
                    f"{spec.year} hourly grid; expected "
                    f"{expected_timestamp.isoformat(timespec='seconds')} at row "
                    f"{index + 1}"
                )
    return tuple(rows)


def _validate_formal_manifest(
    manifest_path: Path,
    *,
    hourly_path: Path,
    spec: HeatDemandAdapterSpec,
    row_count: int,
) -> None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("source manifest must be readable valid JSON") from error
    if not isinstance(manifest, dict):
        raise ValueError("source manifest must contain a JSON object")
    if manifest.get("schema") != FORMAL_MANIFEST_SCHEMA:
        raise ValueError(f"source manifest schema must be {FORMAL_MANIFEST_SCHEMA}")
    if manifest.get("formal_ready") is not True:
        raise ValueError("source manifest formal_ready must be true")
    if type(manifest.get("year")) is not int or manifest["year"] != spec.year:
        raise ValueError("source manifest year does not match the adapter spec")

    outputs = manifest.get("outputs")
    output_entry = outputs.get(hourly_path.name) if isinstance(outputs, dict) else None
    if not isinstance(output_entry, dict):
        raise ValueError("source manifest does not register the hourly CSV basename")
    if type(output_entry.get("rows")) is not int or output_entry["rows"] != row_count:
        raise ValueError("source manifest hourly row count does not match the CSV")
    recorded_sha = output_entry.get("sha256")
    if not isinstance(recorded_sha, str) or recorded_sha != _sha256(hourly_path):
        raise ValueError("source manifest hourly SHA-256 does not match the CSV")

    counts = manifest.get("counts")
    if not isinstance(counts, dict) or counts.get("hourly_points") != row_count:
        raise ValueError("source manifest hourly_points does not match the CSV")


def _quality_count_sums(
    rows: tuple[_HourlySourceRow, ...], indices: tuple[int, ...]
) -> tuple[tuple[str, int], ...]:
    return tuple(
        (
            column,
            sum(rows[index].quality_counts[position] for index in indices),
        )
        for position, column in enumerate(QUALITY_COUNT_COLUMNS)
    )


def adapt_e0b_heat_demand(
    hourly_csv: str | Path,
    *,
    spec: HeatDemandAdapterSpec,
    source_manifest: str | Path | None = None,
) -> AdaptedHeatDemand:
    """Adapt an E0-B hourly table without mutating or recomputing its evidence."""

    if spec.enforce_formal_contract and source_manifest is None:
        raise ValueError("source_manifest is required in formal mode")

    contract = _INTERPRETATION_CONTRACTS[spec.interpretation]
    source_column = contract.source_column

    path = Path(hourly_csv)
    manifest_path = Path(source_manifest) if source_manifest is not None else None
    rows = _read_hourly_source(path, spec=spec)
    if spec.enforce_formal_contract:
        _validate_formal_manifest(
            manifest_path,
            hourly_path=path,
            spec=spec,
            row_count=len(rows),
        )

    timestamps: list[datetime] = []
    source_values: list[float] = []
    model_values: list[float] = []
    modifications: list[HeatDemandModification] = []
    for row in rows:
        source_value = row.candidate_values_mw[source_column]
        model_value = (
            max(source_value, 0.0)
            if contract.clips_negative_values
            else source_value
        )
        timestamps.append(row.timestamp)
        source_values.append(source_value)
        model_values.append(model_value)
        if model_value != source_value:
            modifications.append(
                HeatDemandModification(
                    timestamp=row.timestamp,
                    source_value_mw=source_value,
                    model_value_mw=model_value,
                    clipped_amount_mw=model_value - source_value,
                )
            )

    modification_tuple = tuple(modifications)
    if spec.window is None:
        selected_indices = tuple(range(len(timestamps)))
        window_modifications = modification_tuple
    else:
        selected_indices = tuple(
            index
            for index, timestamp in enumerate(timestamps)
            if spec.window.start <= timestamp < spec.window.end_exclusive
        )
        if len(selected_indices) != spec.window.hours or any(
            timestamps[index] != spec.window.start + timedelta(hours=offset)
            for offset, index in enumerate(selected_indices)
        ):
            raise ValueError("hourly source does not fully cover the requested window")
        window_modifications = tuple(
            modification
            for modification in modification_tuple
            if spec.window.start
            <= modification.timestamp
            < spec.window.end_exclusive
        )
    selected_source_values = tuple(
        source_values[index] for index in selected_indices
    )
    selected_model_values = tuple(model_values[index] for index in selected_indices)
    full_indices = tuple(range(len(rows)))
    return AdaptedHeatDemand(
        timestamps=tuple(timestamps[index] for index in selected_indices),
        source_values_mw=selected_source_values,
        values_mw=selected_model_values,
        full_source_modifications=modification_tuple,
        window_modifications=window_modifications,
        spec=spec,
        source_column=contract.source_column,
        formula=contract.formula,
        scientific_status=contract.scientific_status,
        interpretation_description=contract.description,
        source_csv_name=path.name,
        source_csv_sha256=_sha256(path),
        source_manifest_name=(manifest_path.name if manifest_path is not None else None),
        source_manifest_sha256=(
            _sha256(manifest_path) if manifest_path is not None else None
        ),
        full_source_row_count=len(rows),
        full_source_energy_before_mwh=math.fsum(source_values),
        full_source_energy_after_mwh=math.fsum(model_values),
        energy_before_mwh=math.fsum(selected_source_values),
        energy_after_mwh=math.fsum(selected_model_values),
        full_source_quality_count_sums=_quality_count_sums(rows, full_indices),
        quality_count_sums=_quality_count_sums(rows, selected_indices),
    )


def _number(value: float) -> str:
    if abs(value) < 0.5e-12:
        value = 0.0
    return f"{value:.12f}"


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _round_json_numbers(value: object) -> object:
    if isinstance(value, float):
        rounded = round(value, 12)
        return 0.0 if rounded == 0.0 else rounded
    if isinstance(value, dict):
        return {key: _round_json_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round_json_numbers(item) for item in value]
    return value


def _modification_records(
    modifications: tuple[HeatDemandModification, ...]
) -> list[dict[str, str | float]]:
    return [
        {
            "timestamp": _timestamp(modification.timestamp),
            "source_value_mw": modification.source_value_mw,
            "model_value_mw": modification.model_value_mw,
            "clipped_amount_mw": modification.clipped_amount_mw,
        }
        for modification in modifications
    ]


def _output_stem(adapted: AdaptedHeatDemand) -> str:
    if adapted.spec.window is not None:
        interpretation_code = {
            HeatDemandInterpretation.NET_CLIPPED: "net",
            HeatDemandInterpretation.FORWARD: "fwd",
            HeatDemandInterpretation.ZERO_SENSITIVITY_CLIPPED: "zero",
        }[adapted.spec.interpretation]
        return (
            f"e0c_hd_{adapted.spec.year}_{interpretation_code}_"
            f"{adapted.spec.window.start.strftime('%Y%m%d%H')}_"
            f"{adapted.spec.window.hours}h"
        )
    return (
        f"e0c_heat_demand_{adapted.spec.year}_"
        f"{adapted.spec.interpretation.value}"
    )


def write_adapted_heat_demand(
    adapted: AdaptedHeatDemand, output_dir: str | Path
) -> HeatDemandExport:
    """Write a deterministic E0-C demand CSV and its scientific manifest."""

    if not isinstance(adapted, AdaptedHeatDemand):
        raise ValueError("adapted must be an AdaptedHeatDemand")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = _output_stem(adapted)
    csv_path = directory / f"{stem}.csv"
    manifest_path = directory / f"{stem}.manifest.json"

    modification_by_timestamp = {
        modification.timestamp: modification
        for modification in adapted.window_modifications
    }
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = (
            "timestamp",
            "source_heat_mw",
            "heat_demand_mw",
            "modified",
            "clipped_amount_mw",
        )
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for timestamp, source_value, model_value in zip(
            adapted.timestamps,
            adapted.source_values_mw,
            adapted.values_mw,
            strict=True,
        ):
            modification = modification_by_timestamp.get(timestamp)
            writer.writerow(
                {
                    "timestamp": _timestamp(timestamp),
                    "source_heat_mw": _number(source_value),
                    "heat_demand_mw": _number(model_value),
                    "modified": int(modification is not None),
                    "clipped_amount_mw": _number(
                        modification.clipped_amount_mw
                        if modification is not None
                        else 0.0
                    ),
                }
            )

    csv_sha256 = _sha256(csv_path)
    selection_start = adapted.timestamps[0]
    selection_end = adapted.timestamps[-1] + timedelta(hours=1)
    source_manifest = (
        {
            "file": adapted.source_manifest_name,
            "sha256": adapted.source_manifest_sha256,
        }
        if adapted.source_manifest_name is not None
        else None
    )
    manifest = {
        "schema": "tes_bess_boundary.e0c_heat_demand_adapter.v1",
        "year": adapted.spec.year,
        "interpretation": adapted.spec.interpretation.value,
        "source_column": adapted.source_column,
        "formula": adapted.formula,
        "scientific_status": adapted.scientific_status,
        "interpretation_description": adapted.interpretation_description,
        "selection": {
            "kind": "window" if adapted.spec.window is not None else "full_source",
            "start": _timestamp(selection_start),
            "end_exclusive": _timestamp(selection_end),
            "hours": len(adapted.timestamps),
        },
        "source": {
            "hourly_csv": adapted.source_csv_name,
            "hourly_csv_sha256": adapted.source_csv_sha256,
            "manifest": source_manifest,
            "formal_contract_enforced": adapted.spec.enforce_formal_contract,
        },
        "audit": {
            "full_source": {
                "rows": adapted.full_source_row_count,
                "energy_before_mwh": adapted.full_source_energy_before_mwh,
                "energy_after_mwh": adapted.full_source_energy_after_mwh,
                "quality_count_sums": dict(
                    adapted.full_source_quality_count_sums
                ),
                "modifications": _modification_records(
                    adapted.full_source_modifications
                ),
            },
            "selection": {
                "rows": len(adapted.timestamps),
                "energy_before_mwh": adapted.energy_before_mwh,
                "energy_after_mwh": adapted.energy_after_mwh,
                "quality_count_sums": dict(adapted.quality_count_sums),
                "modifications": _modification_records(
                    adapted.window_modifications
                ),
            },
        },
        "output": {
            "csv": csv_path.name,
            "rows": len(adapted.timestamps),
            "csv_sha256": csv_sha256,
        },
        "units": {
            "heat_power": "MWth",
            "energy": "MWhth",
        },
    }
    manifest = _round_json_numbers(manifest)
    manifest_text = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(manifest_text)
    output_sha256 = {
        csv_path.name: csv_sha256,
        manifest_path.name: _sha256(manifest_path),
    }
    return HeatDemandExport(
        csv_path=csv_path,
        manifest_path=manifest_path,
        output_sha256=output_sha256,
    )
