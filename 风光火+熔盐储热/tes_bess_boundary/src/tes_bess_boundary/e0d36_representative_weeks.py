"""Build the pre-registered E0-D-36 structured representative-week dataset.

This module freezes data selection and annual weights only.  It deliberately
does not concatenate the blocks into the existing single-cycle planning model;
block-local CHP, BESS and TES boundary semantics are an E0-D-37 requirement.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Iterable, Sequence

from tes_bess_boundary.components.chp import LowLoadFuelRule, yangling_chp_specs
from tes_bess_boundary.e0d17_exploration import (
    E0D17InputRow,
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
    PCC_CAPACITY_MW,
    PV_CAPACITY_MW,
    WIND_CAPACITY_MW,
    load_e0d17_inputs,
)


SCHEMA_ID = "tes_bess_boundary.e0d36_representative_weeks.v1"
DATA_SCOPE = "formal_2024_heat_plus_legacy_2019_vre_shapes"
ASSIGNMENTS_NAME = "e0d36_week_assignments.csv"
PERIODS_NAME = "e0d36_representative_periods.csv"
MANIFEST_NAME = "manifest.json"
EXECUTION_NAME = "execution.json"

YEAR_HOURS = 8_784
COMPLETE_WEEK_COUNT = 52
WEEK_HOURS = 168
COMPLETE_WEEK_HOURS = COMPLETE_WEEK_COUNT * WEEK_HOURS
TAIL_WARMUP_HOURS = 24
TAIL_SCORED_HOURS = 48
BASE_MEDOID_COUNT = 4
REPRESENTATIVE_WEEK_COUNT = 6
DISTANCE_TOLERANCE = 1e-12
EXPECTED_START = datetime(2024, 1, 1)

FEATURE_CHANNELS = (
    "heat_demand_mw",
    "wind_cf",
    "pv_cf",
    "ambient_temperature_c",
)
ROLE_ORDER = (
    "pam_medoid",
    "peak_heat_low_wind_extreme",
    "high_vre_low_absorption_extreme",
    "diversity_fill",
)


@dataclass(frozen=True)
class FeatureScale:
    channel: str
    mean: float
    population_std: float


@dataclass(frozen=True)
class WeekMetric:
    week_index: int
    start: datetime
    end: datetime
    peak_heat_mw: float
    mean_wind_cf: float
    positive_surplus_pressure_mwh: float
    peak_surplus_pressure_mw: float


@dataclass(frozen=True)
class RepresentativeWeekPlan:
    rows: tuple[E0D17InputRow, ...]
    feature_scales: tuple[FeatureScale, ...]
    week_metrics: tuple[WeekMetric, ...]
    base_medoids: tuple[int, ...]
    peak_heat_extreme: int
    high_vre_extreme: int
    diversity_fills: tuple[int, ...]
    representatives: tuple[int, ...]
    roles_by_week: tuple[tuple[str, ...], ...]
    assignments: tuple[int, ...]
    assignment_distance_squared: tuple[float, ...]
    representative_weights: tuple[int, ...]
    final_feature_distance_objective: float

    def weight_for(self, representative: int) -> int:
        position = self.representatives.index(representative)
        return self.representative_weights[position]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _validate_rows(rows: Sequence[E0D17InputRow]) -> tuple[E0D17InputRow, ...]:
    checked = tuple(rows)
    if len(checked) != YEAR_HOURS:
        raise ValueError(f"E0-D-36 requires exactly {YEAR_HOURS} hourly rows")
    if EXPECTED_START.weekday() != 0:
        raise AssertionError("the registered 2024 calendar must start on Monday")
    for index, row in enumerate(checked):
        expected = EXPECTED_START + timedelta(hours=index)
        if row.timestamp != expected:
            raise ValueError(
                f"timestamp {index} must be {expected.isoformat()}, "
                f"received {row.timestamp.isoformat()}"
            )
        heat = _finite(row.heat_demand_mw, "heat_demand_mw")
        wind = _finite(row.wind_cf, "wind_cf")
        pv = _finite(row.pv_cf, "pv_cf")
        _finite(row.ambient_temperature_c, "ambient_temperature_c")
        if heat < 0.0:
            raise ValueError("heat demand must be non-negative")
        if not 0.0 <= wind <= 1.0 or not 0.0 <= pv <= 1.0:
            raise ValueError("renewable capacity factors must lie in [0, 1]")
    return checked


def _channel_values(
    rows: Sequence[E0D17InputRow],
    channel: str,
) -> tuple[float, ...]:
    return tuple(float(getattr(row, channel)) for row in rows)


def _feature_vectors(
    rows: Sequence[E0D17InputRow],
) -> tuple[tuple[FeatureScale, ...], tuple[tuple[float, ...], ...]]:
    complete = rows[:COMPLETE_WEEK_HOURS]
    scales: list[FeatureScale] = []
    standardized_channels: dict[str, tuple[float, ...]] = {}
    for channel in FEATURE_CHANNELS:
        values = _channel_values(complete, channel)
        mean = math.fsum(values) / len(values)
        variance = math.fsum((value - mean) ** 2 for value in values) / len(values)
        population_std = math.sqrt(variance)
        if population_std <= 0.0:
            raise ValueError(f"feature channel {channel} has zero variance")
        scales.append(FeatureScale(channel, mean, population_std))
        standardized_channels[channel] = tuple(
            (value - mean) / population_std for value in values
        )

    features: list[tuple[float, ...]] = []
    for week in range(COMPLETE_WEEK_COUNT):
        start = week * WEEK_HOURS
        stop = start + WEEK_HOURS
        features.append(
            tuple(
                value
                for channel in FEATURE_CHANNELS
                for value in standardized_channels[channel][start:stop]
            )
        )
    return tuple(scales), tuple(features)


def _distance_matrix(
    features: Sequence[Sequence[float]],
) -> tuple[tuple[float, ...], ...]:
    count = len(features)
    matrix = [[0.0] * count for _ in range(count)]
    for first in range(count):
        for second in range(first + 1, count):
            distance = math.fsum(
                (left - right) ** 2
                for left, right in zip(
                    features[first],
                    features[second],
                    strict=True,
                )
            )
            matrix[first][second] = distance
            matrix[second][first] = distance
    return tuple(tuple(row) for row in matrix)


def _nearest_total(
    distances: Sequence[Sequence[float]],
    representatives: Iterable[int],
) -> float:
    selected = tuple(sorted(representatives))
    if not selected:
        raise ValueError("at least one representative is required")
    return math.fsum(min(row[item] for item in selected) for row in distances)


def _better_cost(
    candidate_cost: float,
    candidate_key: object,
    incumbent_cost: float | None,
    incumbent_key: object | None,
) -> bool:
    if incumbent_cost is None:
        return True
    if candidate_cost < incumbent_cost - DISTANCE_TOLERANCE:
        return True
    return (
        abs(candidate_cost - incumbent_cost) <= DISTANCE_TOLERANCE
        and candidate_key < incumbent_key
    )


def deterministic_pam(
    distances: Sequence[Sequence[float]],
    medoid_count: int = BASE_MEDOID_COUNT,
) -> tuple[int, ...]:
    """Return deterministic BUILD + SWAP medoids for a distance matrix."""

    count = len(distances)
    if not 0 < medoid_count <= count:
        raise ValueError("medoid_count must lie in [1, number of rows]")
    if any(len(row) != count for row in distances):
        raise ValueError("distance matrix must be square")

    selected: tuple[int, ...] = ()
    while len(selected) < medoid_count:
        best_candidate: int | None = None
        best_cost: float | None = None
        for candidate in range(count):
            if candidate in selected:
                continue
            cost = _nearest_total(distances, (*selected, candidate))
            if _better_cost(cost, candidate, best_cost, best_candidate):
                best_candidate = candidate
                best_cost = cost
        if best_candidate is None:
            raise AssertionError("BUILD failed to select a medoid")
        selected = tuple(sorted((*selected, best_candidate)))

    while True:
        current_cost = _nearest_total(distances, selected)
        best_swap: tuple[int, ...] | None = None
        best_cost: float | None = None
        nonselected = tuple(item for item in range(count) if item not in selected)
        for outgoing in selected:
            for incoming in nonselected:
                candidate = tuple(
                    sorted(item for item in (*selected, incoming) if item != outgoing)
                )
                cost = _nearest_total(distances, candidate)
                if cost >= current_cost - DISTANCE_TOLERANCE:
                    continue
                if _better_cost(cost, candidate, best_cost, best_swap):
                    best_swap = candidate
                    best_cost = cost
        if best_swap is None:
            return selected
        selected = best_swap


def minimum_net_chp_power_for_heat(heat_demand_mw: float) -> float:
    """Minimum two-unit net CHP power compatible with instantaneous heat."""

    heat = _finite(heat_demand_mw, "heat_demand_mw")
    if heat < 0.0:
        raise ValueError("heat demand must be non-negative")
    units = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE
    )
    maximum_heats = tuple(unit.feasible_region.maximum_heat_mw for unit in units)
    if heat > math.fsum(maximum_heats) + 1e-9:
        raise ValueError("heat demand exceeds the two-unit CHP heat envelope")
    if heat <= 1e-12:
        return 0.0

    first_knots = {vertex.heat_mw for vertex in units[0].feasible_region.vertices}
    second_knots = {vertex.heat_mw for vertex in units[1].feasible_region.vertices}
    candidates = {
        0.0,
        maximum_heats[0],
        heat,
        heat - maximum_heats[1],
        *first_knots,
        *(heat - knot for knot in second_knots),
    }
    feasible_splits = tuple(
        first_heat
        for first_heat in candidates
        if -1e-9 <= first_heat <= maximum_heats[0] + 1e-9
        and -1e-9 <= heat - first_heat <= maximum_heats[1] + 1e-9
    )
    if not feasible_splits:
        raise AssertionError("no feasible CHP heat split was generated")

    def contribution(unit_index: int, assigned_heat: float) -> float:
        assigned = min(maximum_heats[unit_index], max(0.0, assigned_heat))
        if assigned <= 1e-12:
            return 0.0
        unit = units[unit_index]
        gross = unit.feasible_region.minimum_power_for_heat(assigned)
        return (1.0 - unit.auxiliary_rate) * gross

    return min(
        contribution(0, first_heat) + contribution(1, heat - first_heat)
        for first_heat in feasible_splits
    )


def _surplus_pressure(row: E0D17InputRow) -> tuple[float, float]:
    minimum_chp = minimum_net_chp_power_for_heat(row.heat_demand_mw)
    pressure = max(
        0.0,
        minimum_chp
        + WIND_CAPACITY_MW * row.wind_cf
        + PV_CAPACITY_MW * row.pv_cf
        - PCC_CAPACITY_MW,
    )
    return minimum_chp, pressure


def _week_metrics(rows: Sequence[E0D17InputRow]) -> tuple[WeekMetric, ...]:
    metrics: list[WeekMetric] = []
    for week in range(COMPLETE_WEEK_COUNT):
        start = week * WEEK_HOURS
        selected = rows[start : start + WEEK_HOURS]
        pressures = tuple(_surplus_pressure(row)[1] for row in selected)
        metrics.append(
            WeekMetric(
                week_index=week,
                start=selected[0].timestamp,
                end=selected[-1].timestamp,
                peak_heat_mw=max(row.heat_demand_mw for row in selected),
                mean_wind_cf=(
                    math.fsum(row.wind_cf for row in selected) / WEEK_HOURS
                ),
                positive_surplus_pressure_mwh=math.fsum(pressures),
                peak_surplus_pressure_mw=max(pressures),
            )
        )
    return tuple(metrics)


def _assign(
    distances: Sequence[Sequence[float]],
    representatives: Sequence[int],
) -> tuple[tuple[int, ...], tuple[float, ...], tuple[int, ...]]:
    selected = tuple(sorted(representatives))
    assignments: list[int] = []
    assignment_distances: list[float] = []
    weights = {representative: 0 for representative in selected}
    for week, row in enumerate(distances):
        best = selected[0]
        best_distance = row[best]
        for representative in selected[1:]:
            distance = row[representative]
            if distance < best_distance - DISTANCE_TOLERANCE:
                best = representative
                best_distance = distance
        assignments.append(best)
        assignment_distances.append(best_distance)
        weights[best] += 1
    for representative in selected:
        if assignments[representative] != representative:
            raise AssertionError("a representative week did not self-assign")
    return (
        tuple(assignments),
        tuple(assignment_distances),
        tuple(weights[item] for item in selected),
    )


def build_representative_week_plan(
    rows: Sequence[E0D17InputRow],
) -> RepresentativeWeekPlan:
    checked = _validate_rows(rows)
    scales, features = _feature_vectors(checked)
    distances = _distance_matrix(features)
    metrics = _week_metrics(checked)
    medoids = deterministic_pam(distances)

    peak_heat_extreme = min(
        range(COMPLETE_WEEK_COUNT),
        key=lambda week: (
            -metrics[week].peak_heat_mw,
            metrics[week].mean_wind_cf,
            week,
        ),
    )
    high_vre_extreme = min(
        range(COMPLETE_WEEK_COUNT),
        key=lambda week: (
            -metrics[week].positive_surplus_pressure_mwh,
            -metrics[week].peak_surplus_pressure_mw,
            week,
        ),
    )

    selected = set(medoids)
    selected.add(peak_heat_extreme)
    selected.add(high_vre_extreme)
    fills: list[int] = []
    while len(selected) < REPRESENTATIVE_WEEK_COUNT:
        best_candidate: int | None = None
        best_cost: float | None = None
        for candidate in range(COMPLETE_WEEK_COUNT):
            if candidate in selected:
                continue
            cost = _nearest_total(distances, (*selected, candidate))
            if _better_cost(cost, candidate, best_cost, best_candidate):
                best_candidate = candidate
                best_cost = cost
        if best_candidate is None:
            raise AssertionError("diversity fill failed")
        selected.add(best_candidate)
        fills.append(best_candidate)
    if len(selected) != REPRESENTATIVE_WEEK_COUNT:
        raise ValueError(
            "the two forced extreme rules produced more than six unique weeks; "
            "the pre-registered six-week dataset cannot be formed"
        )
    representatives = tuple(sorted(selected))

    roles: list[list[str]] = [[] for _ in range(COMPLETE_WEEK_COUNT)]
    for week in medoids:
        roles[week].append("pam_medoid")
    roles[peak_heat_extreme].append("peak_heat_low_wind_extreme")
    roles[high_vre_extreme].append("high_vre_low_absorption_extreme")
    for week in fills:
        roles[week].append("diversity_fill")
    roles_by_week = tuple(
        tuple(role for role in ROLE_ORDER if role in assigned_roles)
        for assigned_roles in roles
    )

    assignments, assignment_distances, weights = _assign(
        distances,
        representatives,
    )
    if math.fsum(weights) != COMPLETE_WEEK_COUNT or any(weight < 1 for weight in weights):
        raise AssertionError("representative-week weights do not cover all 52 weeks")

    return RepresentativeWeekPlan(
        rows=checked,
        feature_scales=scales,
        week_metrics=metrics,
        base_medoids=medoids,
        peak_heat_extreme=peak_heat_extreme,
        high_vre_extreme=high_vre_extreme,
        diversity_fills=tuple(fills),
        representatives=representatives,
        roles_by_week=roles_by_week,
        assignments=assignments,
        assignment_distance_squared=assignment_distances,
        representative_weights=weights,
        final_feature_distance_objective=math.fsum(assignment_distances),
    )


def _roles_text(roles: Sequence[str]) -> str:
    return "|".join(roles)


def _assignment_rows(plan: RepresentativeWeekPlan) -> list[dict]:
    rows: list[dict] = []
    for metric, representative, distance in zip(
        plan.week_metrics,
        plan.assignments,
        plan.assignment_distance_squared,
        strict=True,
    ):
        representative_metric = plan.week_metrics[representative]
        rows.append(
            {
                "original_week_index": metric.week_index + 1,
                "week_start": metric.start.isoformat(),
                "week_end": metric.end.isoformat(),
                "week_roles": _roles_text(plan.roles_by_week[metric.week_index]),
                "assigned_representative_week_index": representative + 1,
                "representative_start": representative_metric.start.isoformat(),
                "representative_roles": _roles_text(
                    plan.roles_by_week[representative]
                ),
                "assignment_distance_squared": distance,
                "representative_weight_weeks": plan.weight_for(representative),
                "weekly_peak_heat_mw": metric.peak_heat_mw,
                "weekly_mean_wind_cf": metric.mean_wind_cf,
                "weekly_positive_surplus_pressure_mwh": (
                    metric.positive_surplus_pressure_mwh
                ),
                "weekly_peak_surplus_pressure_mw": (
                    metric.peak_surplus_pressure_mw
                ),
            }
        )
    return rows


def _period_payload(
    *,
    model_period: int,
    block_id: str,
    block_kind: str,
    block_order: int,
    block_period: int,
    source_hour_index: int,
    source_week_index: int | None,
    source_role: str,
    scored: bool,
    annual_weight: int,
    row: E0D17InputRow,
) -> dict:
    minimum_chp, pressure = _surplus_pressure(row)
    return {
        "model_period": model_period,
        "block_id": block_id,
        "block_kind": block_kind,
        "block_order": block_order,
        "block_period": block_period,
        "source_hour_index": source_hour_index,
        "source_timestamp": row.timestamp.isoformat(),
        "source_week_index": (
            "" if source_week_index is None else source_week_index + 1
        ),
        "source_role": source_role,
        "scored": str(scored).lower(),
        "annual_weight": annual_weight,
        "heat_demand_mw": row.heat_demand_mw,
        "wind_cf": row.wind_cf,
        "pv_cf": row.pv_cf,
        "ambient_temperature_c": row.ambient_temperature_c,
        "wind_available_mw": WIND_CAPACITY_MW * row.wind_cf,
        "pv_available_mw": PV_CAPACITY_MW * row.pv_cf,
        "minimum_heat_constrained_net_chp_mw": minimum_chp,
        "positive_surplus_pressure_mw": pressure,
    }


def _period_rows(plan: RepresentativeWeekPlan) -> list[dict]:
    output: list[dict] = []
    model_period = 1
    for block_order, week in enumerate(plan.representatives, start=1):
        source_start = week * WEEK_HOURS
        weight = plan.weight_for(week)
        for offset in range(WEEK_HOURS):
            source_index = source_start + offset
            output.append(
                _period_payload(
                    model_period=model_period,
                    block_id=f"representative_week_{week + 1:02d}",
                    block_kind="representative_week",
                    block_order=block_order,
                    block_period=offset + 1,
                    source_hour_index=source_index,
                    source_week_index=week,
                    source_role="representative_scored",
                    scored=True,
                    annual_weight=weight,
                    row=plan.rows[source_index],
                )
            )
            model_period += 1

    tail_start = COMPLETE_WEEK_HOURS - TAIL_WARMUP_HOURS
    tail_stop = YEAR_HOURS
    for offset, source_index in enumerate(range(tail_start, tail_stop), start=1):
        scored = source_index >= COMPLETE_WEEK_HOURS
        output.append(
            _period_payload(
                model_period=model_period,
                block_id="year_end_tail",
                block_kind="tail_with_warmup",
                block_order=REPRESENTATIVE_WEEK_COUNT + 1,
                block_period=offset,
                source_hour_index=source_index,
                source_week_index=(
                    COMPLETE_WEEK_COUNT - 1
                    if source_index < COMPLETE_WEEK_HOURS
                    else None
                ),
                source_role="tail_scored" if scored else "tail_warmup",
                scored=scored,
                annual_weight=1 if scored else 0,
                row=plan.rows[source_index],
            )
        )
        model_period += 1
    return output


def _aggregate_diagnostics(
    plan: RepresentativeWeekPlan,
    period_rows: Sequence[dict],
) -> dict:
    actual_heat = math.fsum(row.heat_demand_mw for row in plan.rows)
    actual_wind = math.fsum(WIND_CAPACITY_MW * row.wind_cf for row in plan.rows)
    actual_pv = math.fsum(PV_CAPACITY_MW * row.pv_cf for row in plan.rows)
    actual_temperature_mean = (
        math.fsum(row.ambient_temperature_c for row in plan.rows) / YEAR_HOURS
    )
    scored = tuple(row for row in period_rows if row["scored"] == "true")
    reconstructed_heat = math.fsum(
        float(row["annual_weight"]) * float(row["heat_demand_mw"])
        for row in scored
    )
    reconstructed_wind = math.fsum(
        float(row["annual_weight"]) * float(row["wind_available_mw"])
        for row in scored
    )
    reconstructed_pv = math.fsum(
        float(row["annual_weight"]) * float(row["pv_available_mw"])
        for row in scored
    )
    reconstructed_temperature_mean = math.fsum(
        float(row["annual_weight"]) * float(row["ambient_temperature_c"])
        for row in scored
    ) / YEAR_HOURS

    def energy_item(actual: float, reconstructed: float) -> dict:
        return {
            "actual": actual,
            "reconstructed": reconstructed,
            "relative_error_percent": 100.0 * (reconstructed - actual) / actual,
        }

    return {
        "heat_demand_mwh": energy_item(actual_heat, reconstructed_heat),
        "wind_available_mwh": energy_item(actual_wind, reconstructed_wind),
        "pv_available_mwh": energy_item(actual_pv, reconstructed_pv),
        "ambient_temperature_c": {
            "actual_mean": actual_temperature_mean,
            "reconstructed_mean": reconstructed_temperature_mean,
            "mean_bias_c": reconstructed_temperature_mean
            - actual_temperature_mean,
        },
        "acceptance_role": "descriptive_only_not_post_result_tuning_target",
    }


def _write_csv(path: Path, rows: Sequence[dict]) -> None:
    if not rows:
        raise ValueError("cannot write an empty canonical CSV")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )


def export_representative_week_plan(
    plan: RepresentativeWeekPlan,
    output_dir: Path,
) -> dict:
    assignment_rows = _assignment_rows(plan)
    period_rows = _period_rows(plan)
    output_dir.mkdir(parents=True, exist_ok=True)
    assignments_path = output_dir / ASSIGNMENTS_NAME
    periods_path = output_dir / PERIODS_NAME
    _write_csv(assignments_path, assignment_rows)
    _write_csv(periods_path, period_rows)

    scored_rows = tuple(row for row in period_rows if row["scored"] == "true")
    weighted_scored_hours = math.fsum(
        float(row["annual_weight"]) for row in scored_rows
    )
    representative_payload = []
    for week, weight in zip(
        plan.representatives,
        plan.representative_weights,
        strict=True,
    ):
        metric = plan.week_metrics[week]
        representative_payload.append(
            {
                "week_index": week + 1,
                "start": metric.start.isoformat(),
                "end": metric.end.isoformat(),
                "roles": list(plan.roles_by_week[week]),
                "weight_weeks": weight,
                "peak_heat_mw": metric.peak_heat_mw,
                "mean_wind_cf": metric.mean_wind_cf,
                "positive_surplus_pressure_mwh": (
                    metric.positive_surplus_pressure_mwh
                ),
                "peak_surplus_pressure_mw": metric.peak_surplus_pressure_mw,
            }
        )

    manifest = {
        "schema_id": SCHEMA_ID,
        "claim_scope": (
            "representative_week_dataset_freeze_not_technology_comparison_"
            "not_formal_project_tac"
        ),
        "formal_project_tac_ready": False,
        "source_data": {
            "scope": DATA_SCOPE,
            "formal_heat_sha256": FORMAL_HEAT_SHA256,
            "legacy_vre_sha256": LEGACY_VRE_SHA256,
            "renewable_baseline_formal": False,
            "hour_count": YEAR_HOURS,
            "first_timestamp": plan.rows[0].timestamp.isoformat(),
            "last_timestamp": plan.rows[-1].timestamp.isoformat(),
        },
        "calendar_contract": {
            "complete_week_count": COMPLETE_WEEK_COUNT,
            "complete_week_hours": COMPLETE_WEEK_HOURS,
            "tail_warmup_hours": TAIL_WARMUP_HOURS,
            "tail_scored_hours": TAIL_SCORED_HOURS,
            "representative_week_count": REPRESENTATIVE_WEEK_COUNT,
            "model_period_count": len(period_rows),
            "scored_source_row_count": len(scored_rows),
            "weighted_scored_hours": weighted_scored_hours,
        },
        "feature_contract": {
            "channels_in_concatenation_order": list(FEATURE_CHANNELS),
            "hours_per_channel": WEEK_HOURS,
            "dimension": len(FEATURE_CHANNELS) * WEEK_HOURS,
            "scaling_population": "first_8736_hours",
            "scales": [
                {
                    "channel": scale.channel,
                    "mean": scale.mean,
                    "population_std": scale.population_std,
                }
                for scale in plan.feature_scales
            ],
            "distance": "squared_euclidean_on_channelwise_z_scores",
            "price_feature_included": False,
        },
        "selection_contract": {
            "algorithm": "deterministic_pam_build_swap_plus_forced_extremes",
            "distance_tolerance": DISTANCE_TOLERANCE,
            "base_medoid_count": BASE_MEDOID_COUNT,
            "base_medoid_week_indices": [item + 1 for item in plan.base_medoids],
            "peak_heat_low_wind_extreme_week_index": (
                plan.peak_heat_extreme + 1
            ),
            "high_vre_low_absorption_extreme_week_index": (
                plan.high_vre_extreme + 1
            ),
            "diversity_fill_week_indices": [
                item + 1 for item in plan.diversity_fills
            ],
            "final_feature_distance_objective": (
                plan.final_feature_distance_objective
            ),
            "assignment_tie_break": "lowest_source_week_index",
            "surplus_pressure_proxy": {
                "formula": (
                    "max(0,min_heat_constrained_net_chp+wind_available+"
                    "pv_available-pcc_capacity)"
                ),
                "wind_capacity_mw": WIND_CAPACITY_MW,
                "pv_capacity_mw": PV_CAPACITY_MW,
                "pcc_capacity_mw": PCC_CAPACITY_MW,
                "chp_basis": "two_locked_yangling_units_with_auxiliary_rates",
                "selection_proxy_not_realized_curtailment": True,
            },
        },
        "representatives": representative_payload,
        "aggregate_reconstruction_diagnostics": _aggregate_diagnostics(
            plan,
            period_rows,
        ),
        "boundary_handoff": {
            "optimization_run_in_d36": False,
            "d37_required": True,
            "representative_weeks_are_independent_cyclic_blocks": True,
            "tail_has_24h_unscored_warmup_and_48h_scored_segment": True,
            "cross_block_chronological_state_transfer_allowed": False,
        },
        "audit": {
            "passed": (
                len(assignment_rows) == COMPLETE_WEEK_COUNT
                and len(plan.representatives) == REPRESENTATIVE_WEEK_COUNT
                and len(set(plan.representatives)) == REPRESENTATIVE_WEEK_COUNT
                and sum(plan.representative_weights) == COMPLETE_WEEK_COUNT
                and all(weight >= 1 for weight in plan.representative_weights)
                and len(period_rows) == 1_080
                and len(scored_rows) == 1_056
                and math.isclose(
                    weighted_scored_hours,
                    YEAR_HOURS,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            ),
            "all_52_weeks_assigned_once": len(assignment_rows)
            == COMPLETE_WEEK_COUNT,
            "representative_weights_sum": sum(plan.representative_weights),
            "each_representative_weight_at_least_one": all(
                weight >= 1 for weight in plan.representative_weights
            ),
            "forced_extreme_roles_present": (
                "peak_heat_low_wind_extreme"
                in plan.roles_by_week[plan.peak_heat_extreme]
                and "high_vre_low_absorption_extreme"
                in plan.roles_by_week[plan.high_vre_extreme]
            ),
            "canonical_line_endings": "LF",
        },
        "canonical_files": {
            ASSIGNMENTS_NAME: _sha256(assignments_path),
            PERIODS_NAME: _sha256(periods_path),
        },
    }
    if manifest["audit"]["passed"] is not True:
        raise AssertionError("E0-D-36 structural audit failed")
    _write_json(output_dir / MANIFEST_NAME, manifest)
    return manifest


def build_bundle(heat_path: Path, vre_path: Path, output_dir: Path) -> dict:
    started = perf_counter()
    rows = load_e0d17_inputs(heat_path, vre_path)
    plan = build_representative_week_plan(rows)
    manifest = export_representative_week_plan(plan, output_dir)
    execution = {
        "schema_id": f"{SCHEMA_ID}.execution",
        "generated_at": datetime.now().astimezone().isoformat(),
        "runtime_seconds": perf_counter() - started,
        "python_version": sys.version,
        "platform": platform.platform(),
        "source_paths": {
            "heat": str(heat_path),
            "vre": str(vre_path),
        },
        "source_hashes_verified": {
            "heat": _sha256(heat_path) == FORMAL_HEAT_SHA256,
            "vre": _sha256(vre_path) == LEGACY_VRE_SHA256,
        },
        "canonical_manifest_sha256": _sha256(output_dir / MANIFEST_NAME),
    }
    _write_json(output_dir / EXECUTION_NAME, execution)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heat-path", type=Path, required=True)
    parser.add_argument("--vre-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(
        json.dumps(
            build_bundle(args.heat_path, args.vre_path, args.output_dir),
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
