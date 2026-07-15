"""Strict representative-period adapter for independent block-cyclic planning.

The default contract remains the frozen D36 artifact.  Explicit callers may
provide another fully locked hash/block contract, such as the preregistered D39
eight-week refinement.  The adapter does not build or solve a planning case.
"""

from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from tes_bess_boundary.economics import (
    AnnualDispatchBlock,
    BlockAnnualHorizonSpec,
)
from tes_bess_boundary.model import E0CTimeSeries


D36_PERIODS_SHA256 = (
    "02b168d6b4169101c1d601a548c7a475d8aea8a8a280de5f52fcaaf6ec09aaa9"
)
D37_SCHEMA_ID = "tes_bess_boundary.e0d37_block_horizon.v1"
EXPECTED_REPRESENTATIVE_BLOCKS = (
    ("representative_week_04", 1.0),
    ("representative_week_05", 3.0),
    ("representative_week_08", 10.0),
    ("representative_week_29", 13.0),
    ("representative_week_39", 21.0),
    ("representative_week_48", 4.0),
)
TAIL_BLOCK_ID = "year_end_tail"
MODEL_PERIOD_COUNT = 1_080
REPRESENTATIVE_WEEK_HOURS = 168
TAIL_WARMUP_HOURS = 24
TAIL_SCORED_HOURS = 48

_REQUIRED_COLUMNS = frozenset(
    {
        "model_period",
        "block_id",
        "block_kind",
        "block_order",
        "block_period",
        "source_hour_index",
        "source_timestamp",
        "scored",
        "annual_weight",
        "heat_demand_mw",
        "wind_available_mw",
        "pv_available_mw",
        "ambient_temperature_c",
    }
)


@dataclass(frozen=True)
class E0D37BlockHorizonInput:
    """Validated representative-period inputs and their block annual horizon."""

    timeseries: E0CTimeSeries
    horizon: BlockAnnualHorizonSpec
    source_timestamps: tuple[datetime, ...]
    source_hour_indices: tuple[int, ...]
    source_sha256: str
    schema_id: str = D37_SCHEMA_ID

    @property
    def block_ids(self) -> tuple[str, ...]:
        return tuple(block.block_id for block in self.horizon.dispatch_blocks)


def _parse_finite_float(row: dict[str, str], field: str, row_number: int) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"row {row_number} has invalid {field}") from exc
    if not math.isfinite(value):
        raise ValueError(f"row {row_number} has non-finite {field}")
    return value


def _parse_int(row: dict[str, str], field: str, row_number: int) -> int:
    try:
        return int(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"row {row_number} has invalid integer {field}") from exc


def _parse_scored(value: str, row_number: int) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"row {row_number} has invalid scored flag")


def load_e0d37_block_horizon(
    periods_csv: str | Path,
    *,
    expected_sha256: str = D36_PERIODS_SHA256,
    expected_representative_blocks: tuple[tuple[str, float], ...] = (
        EXPECTED_REPRESENTATIVE_BLOCKS
    ),
    expected_model_period_count: int = MODEL_PERIOD_COUNT,
    artifact_label: str = "D36",
) -> E0D37BlockHorizonInput:
    """Load one hash-locked representative-period artifact."""

    if not artifact_label.strip():
        raise ValueError("representative-period artifact label must be non-empty")
    if not expected_representative_blocks:
        raise ValueError("at least one representative block is required")
    structural_period_count = (
        len(expected_representative_blocks) * REPRESENTATIVE_WEEK_HOURS
        + TAIL_WARMUP_HOURS
        + TAIL_SCORED_HOURS
    )
    if expected_model_period_count != structural_period_count:
        raise ValueError(
            "representative-period model count does not match its block contract"
        )

    path = Path(periods_csv)
    payload = path.read_bytes()
    source_sha256 = hashlib.sha256(payload).hexdigest()
    if source_sha256 != expected_sha256:
        raise ValueError(
            f"{artifact_label} representative-period SHA-256 mismatch: "
            f"expected {expected_sha256}, received {source_sha256}"
        )

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = frozenset(reader.fieldnames or ())
        missing = sorted(_REQUIRED_COLUMNS - fieldnames)
        if missing:
            raise ValueError(
                f"{artifact_label} periods CSV is missing columns: {missing}"
            )
        rows = tuple(reader)
    if len(rows) != expected_model_period_count:
        raise ValueError(
            f"{artifact_label} periods CSV must contain "
            f"{expected_model_period_count} model rows"
        )

    heat_demand: list[float] = []
    wind_available: list[float] = []
    pv_available: list[float] = []
    ambient_temperature: list[float] = []
    weights: list[float] = []
    timestamps: list[datetime] = []
    source_hour_indices: list[int] = []
    block_rows: list[list[int]] = []
    block_ids: list[str] = []
    current_block_id: str | None = None

    expected_source_start = datetime(2024, 1, 1)
    for zero_based_period, row in enumerate(rows):
        row_number = zero_based_period + 2
        if _parse_int(row, "model_period", row_number) != zero_based_period + 1:
            raise ValueError("model_period must be the consecutive 1-based row index")
        block_id = row["block_id"]
        if not block_id:
            raise ValueError(f"row {row_number} has an empty block_id")
        if block_id != current_block_id:
            if block_id in block_ids:
                raise ValueError(
                    f"{artifact_label} block rows must be contiguous"
                )
            block_ids.append(block_id)
            block_rows.append([])
            current_block_id = block_id
        block_rows[-1].append(zero_based_period)
        if _parse_int(row, "block_order", row_number) != len(block_rows):
            raise ValueError("block_order must match the contiguous block order")
        if _parse_int(row, "block_period", row_number) != len(block_rows[-1]):
            raise ValueError("block_period must be consecutive within each block")

        source_hour_index = _parse_int(row, "source_hour_index", row_number)
        try:
            timestamp = datetime.fromisoformat(row["source_timestamp"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"row {row_number} has invalid source_timestamp") from exc
        if timestamp != expected_source_start + timedelta(hours=source_hour_index):
            raise ValueError("source timestamp does not match source_hour_index")
        if len(block_rows[-1]) > 1 and timestamp != timestamps[-1] + timedelta(hours=1):
            raise ValueError("source timestamps must be hourly and consecutive within a block")

        heat_value = _parse_finite_float(row, "heat_demand_mw", row_number)
        wind_value = _parse_finite_float(row, "wind_available_mw", row_number)
        pv_value = _parse_finite_float(row, "pv_available_mw", row_number)
        if min(heat_value, wind_value, pv_value) < 0.0:
            raise ValueError("heat and renewable availability must be non-negative")
        heat_demand.append(heat_value)
        wind_available.append(wind_value)
        pv_available.append(pv_value)
        ambient_temperature.append(
            _parse_finite_float(row, "ambient_temperature_c", row_number)
        )
        weights.append(_parse_finite_float(row, "annual_weight", row_number))
        timestamps.append(timestamp)
        source_hour_indices.append(source_hour_index)

        scored = _parse_scored(row["scored"], row_number)
        if scored != (weights[-1] > 0.0):
            raise ValueError("scored flag must be equivalent to a positive annual weight")

    expected_block_ids = tuple(
        block_id for block_id, _weight in expected_representative_blocks
    ) + (TAIL_BLOCK_ID,)
    if tuple(block_ids) != expected_block_ids:
        raise ValueError(
            f"{artifact_label} representative block ids or order changed"
        )

    for block_index, (expected_id, expected_weight) in enumerate(
        expected_representative_blocks
    ):
        periods = block_rows[block_index]
        if len(periods) != REPRESENTATIVE_WEEK_HOURS:
            raise ValueError(f"{expected_id} must contain 168 periods")
        if any(rows[period]["block_kind"] != "representative_week" for period in periods):
            raise ValueError(f"{expected_id} has an invalid block_kind")
        if any(weights[period] != expected_weight for period in periods):
            raise ValueError(f"{expected_id} annual weight changed")

    tail_periods = block_rows[-1]
    if len(tail_periods) != TAIL_WARMUP_HOURS + TAIL_SCORED_HOURS:
        raise ValueError("year-end tail must contain 72 periods")
    if any(rows[period]["block_kind"] != "tail_with_warmup" for period in tail_periods):
        raise ValueError("year-end tail has an invalid block_kind")
    tail_weights = tuple(weights[period] for period in tail_periods)
    if tail_weights != (0.0,) * TAIL_WARMUP_HOURS + (1.0,) * TAIL_SCORED_HOURS:
        raise ValueError("year-end tail must be 24 zero-weight plus 48 unit-weight hours")

    dispatch_blocks = tuple(
        AnnualDispatchBlock(block_id=block_id, periods=tuple(periods))
        for block_id, periods in zip(block_ids, block_rows, strict=True)
    )
    horizon = BlockAnnualHorizonSpec(
        period_weights=tuple(weights),
        dispatch_blocks=dispatch_blocks,
    )
    horizon.validate_time_grid(
        period_count=expected_model_period_count,
        dt_hours=1.0,
    )
    timeseries = E0CTimeSeries(
        heat_demand_mw=tuple(heat_demand),
        wind_available_mw=tuple(wind_available),
        pv_available_mw=tuple(pv_available),
        ambient_temperature_c=tuple(ambient_temperature),
    )
    return E0D37BlockHorizonInput(
        timeseries=timeseries,
        horizon=horizon,
        source_timestamps=tuple(timestamps),
        source_hour_indices=tuple(source_hour_indices),
        source_sha256=source_sha256,
    )
