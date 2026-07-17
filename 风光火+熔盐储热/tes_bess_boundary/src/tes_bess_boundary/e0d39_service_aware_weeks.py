"""Build the pre-registered E0-D-39 service-aware representative weeks.

D39 preserves all six D36 weeks, adds the two largest baseline curtailment
underrepresentation weeks from the frozen D38-R1 diagnostic, and reassigns all
52 weeks with the unchanged D36 feature distance.  This module constructs data
only; it does not solve a planning model.
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
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Sequence

from tes_bess_boundary.e0d17_exploration import (
    E0D17InputRow,
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
    load_e0d17_inputs,
)
from tes_bess_boundary.e0d36_representative_weeks import (
    COMPLETE_WEEK_COUNT,
    COMPLETE_WEEK_HOURS,
    DATA_SCOPE,
    DISTANCE_TOLERANCE,
    FEATURE_CHANNELS,
    TAIL_SCORED_HOURS,
    TAIL_WARMUP_HOURS,
    WEEK_HOURS,
    YEAR_HOURS,
    FeatureScale,
    WeekMetric,
    _aggregate_diagnostics,
    _assign,
    _assignment_rows,
    _distance_matrix,
    _feature_vectors,
    _period_payload,
    _write_csv,
    _write_json,
    build_representative_week_plan,
)
from tes_bess_boundary import e0d36_representative_weeks as d36_module


SCHEMA_ID = "tes_bess_boundary.e0d39_service_aware_representative_weeks.v1"
CONTRACT_PATH = (
    "docs/03_sci_paper/"
    "e0_d39_service_aware_representative_week_refinement_contract.md"
)
ASSIGNMENTS_NAME = "e0d39_week_assignments.csv"
PERIODS_NAME = "e0d39_representative_periods.csv"
MANIFEST_NAME = "manifest.json"
EXECUTION_NAME = "execution.json"

LOCKED_D36_REPRESENTATIVE_WEEKS = (4, 5, 8, 29, 39, 48)
LOCKED_ADDED_WEEKS_RANKED = (49, 16)
LOCKED_D39_REPRESENTATIVE_WEEKS = (4, 5, 8, 16, 29, 39, 48, 49)
REPRESENTATIVE_WEEK_COUNT = 8
MODEL_PERIOD_COUNT = 1_416
SCORED_SOURCE_ROW_COUNT = 1_392

D36_ASSIGNMENTS_SHA256 = (
    "31c7daae3faa5ffa91f3e5b31ad75fc666cf9f3952bac399352ec832607488a3"
)
D36_PERIODS_SHA256 = (
    "02b168d6b4169101c1d601a548c7a475d8aea8a8a280de5f52fcaaf6ec09aaa9"
)
D38_FAILURE_DIAGNOSTIC_SHA256 = (
    "3ea98ef46b72705617a3dc436c57b158f7819aa8e358c8d85448e66f5bc46329"
)
REFINEMENT_ROLE = "d38_baseline_top2_curtailment_underrepresentation"


@dataclass(frozen=True)
class ServiceAwareRepresentativeWeekPlan:
    rows: tuple[E0D17InputRow, ...]
    feature_scales: tuple[FeatureScale, ...]
    week_metrics: tuple[WeekMetric, ...]
    original_representatives: tuple[int, ...]
    added_weeks_ranked: tuple[int, ...]
    representatives: tuple[int, ...]
    roles_by_week: tuple[tuple[str, ...], ...]
    assignments: tuple[int, ...]
    assignment_distance_squared: tuple[float, ...]
    representative_weights: tuple[int, ...]
    final_feature_distance_objective: float
    formal_locked: bool

    def weight_for(self, representative: int) -> int:
        position = self.representatives.index(representative)
        return self.representative_weights[position]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def constructor_code_hashes() -> dict[str, str]:
    return {
        "d39_code_sha256": _sha256(Path(__file__)),
        "d36_code_sha256": _sha256(Path(d36_module.__file__)),
    }


def _validated_weekly_diagnostics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("schema_id") != (
        "tes_bess_boundary.e0d38_weekly_failure_diagnostic.v1"
    ):
        raise ValueError("D39 requires the frozen D38 weekly diagnostic schema")
    if payload.get("status") != "complete":
        raise ValueError("D38 weekly diagnostic must be complete")
    state = payload.get("state")
    if not isinstance(state, dict) or state.get("state_id") != "baseline":
        raise ValueError("D39 refinement requires the baseline diagnostic")
    rows = payload.get("weekly_diagnostics")
    if not isinstance(rows, list) or len(rows) != COMPLETE_WEEK_COUNT:
        raise ValueError("weekly_diagnostics must contain all 52 weeks")

    checked: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each weekly diagnostic must be an object")
        week = int(row["original_week_index"])
        underrepresentation = float(row["curtailment_underrepresentation_mwh"])
        if week not in range(1, COMPLETE_WEEK_COUNT + 1) or week in seen:
            raise ValueError("weekly diagnostic indices must uniquely cover 1..52")
        if not math.isfinite(underrepresentation):
            raise ValueError("weekly underrepresentation must be finite")
        seen.add(week)
        checked.append(
            {
                **row,
                "original_week_index": week,
                "curtailment_underrepresentation_mwh": underrepresentation,
            }
        )
    if seen != set(range(1, COMPLETE_WEEK_COUNT + 1)):
        raise ValueError("weekly diagnostic indices must uniquely cover 1..52")
    return checked


def select_additional_weeks(
    diagnostic: dict[str, Any],
    original_representatives: Sequence[int],
) -> tuple[int, int]:
    """Select the top two non-D36 weeks using the frozen D39 ranking."""

    original = {int(item) for item in original_representatives}
    if len(original) != 6:
        raise ValueError("D39 requires exactly six original representatives")
    ranked = sorted(
        _validated_weekly_diagnostics(diagnostic),
        key=lambda row: (
            -row["curtailment_underrepresentation_mwh"],
            row["original_week_index"],
        ),
    )
    selected = tuple(
        row["original_week_index"]
        for row in ranked
        if row["original_week_index"] not in original
    )[:2]
    if len(selected) != 2:
        raise AssertionError("D39 could not select two non-D36 weeks")
    return selected


def build_service_aware_plan(
    rows: Sequence[E0D17InputRow],
    diagnostic: dict[str, Any],
    *,
    require_formal_lock: bool = False,
) -> ServiceAwareRepresentativeWeekPlan:
    d36_plan = build_representative_week_plan(rows)
    original_one_based = tuple(item + 1 for item in d36_plan.representatives)
    if require_formal_lock and original_one_based != LOCKED_D36_REPRESENTATIVE_WEEKS:
        raise ValueError(
            "formal D39 build requires locked D36 representatives "
            f"{LOCKED_D36_REPRESENTATIVE_WEEKS}, received {original_one_based}"
        )
    added_one_based = select_additional_weeks(diagnostic, original_one_based)
    if require_formal_lock and added_one_based != LOCKED_ADDED_WEEKS_RANKED:
        raise ValueError(
            "formal D39 diagnostic must select weeks "
            f"{LOCKED_ADDED_WEEKS_RANKED}, received {added_one_based}"
        )

    scales, features = _feature_vectors(d36_plan.rows)
    if scales != d36_plan.feature_scales:
        raise AssertionError("D39 feature scales diverged from D36")
    distances = _distance_matrix(features)
    representatives = tuple(
        sorted((*d36_plan.representatives, *(item - 1 for item in added_one_based)))
    )
    assignments, assignment_distances, weights = _assign(
        distances,
        representatives,
    )

    roles = [list(item) for item in d36_plan.roles_by_week]
    for week in added_one_based:
        roles[week - 1].append(REFINEMENT_ROLE)
    plan = ServiceAwareRepresentativeWeekPlan(
        rows=d36_plan.rows,
        feature_scales=scales,
        week_metrics=d36_plan.week_metrics,
        original_representatives=d36_plan.representatives,
        added_weeks_ranked=tuple(item - 1 for item in added_one_based),
        representatives=representatives,
        roles_by_week=tuple(tuple(item) for item in roles),
        assignments=assignments,
        assignment_distance_squared=assignment_distances,
        representative_weights=weights,
        final_feature_distance_objective=math.fsum(assignment_distances),
        formal_locked=require_formal_lock,
    )
    if len(plan.representatives) != REPRESENTATIVE_WEEK_COUNT:
        raise AssertionError("D39 must contain exactly eight representative weeks")
    if sum(plan.representative_weights) != COMPLETE_WEEK_COUNT:
        raise AssertionError("D39 representative weights must sum to 52")
    if min(plan.representative_weights) < 1:
        raise AssertionError("every D39 representative must self-assign")
    if require_formal_lock and tuple(
        item + 1 for item in plan.representatives
    ) != LOCKED_D39_REPRESENTATIVE_WEEKS:
        raise AssertionError("formal D39 representative set diverged from contract")
    return plan


def period_rows(plan: ServiceAwareRepresentativeWeekPlan) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
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
    for offset, source_index in enumerate(
        range(tail_start, YEAR_HOURS),
        start=1,
    ):
        scored = source_index >= COMPLETE_WEEK_HOURS
        output.append(
            _period_payload(
                model_period=model_period,
                block_id="year_end_tail",
                block_kind="tail_with_warmup",
                block_order=len(plan.representatives) + 1,
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


def _tail_matches_d36(
    generated_rows: Sequence[dict[str, Any]],
    d36_periods_path: Path | None,
) -> bool:
    if d36_periods_path is None:
        return True
    d36_tail = [
        row for row in _read_csv(d36_periods_path) if row["block_id"] == "year_end_tail"
    ]
    d39_tail = [row for row in generated_rows if row["block_id"] == "year_end_tail"]
    if len(d36_tail) != 72 or len(d39_tail) != 72:
        return False
    ignored = {"model_period", "block_order"}
    fields = tuple(key for key in d39_tail[0] if key not in ignored)
    return all(
        all(str(new[field]) == old[field] for field in fields)
        for new, old in zip(d39_tail, d36_tail, strict=True)
    )


def export_service_aware_plan(
    plan: ServiceAwareRepresentativeWeekPlan,
    output_dir: Path,
    *,
    source_artifacts: dict[str, str] | None = None,
    d36_periods_path: Path | None = None,
) -> dict[str, Any]:
    assignments = _assignment_rows(plan)  # D36 canonical columns, new weights.
    periods = period_rows(plan)
    output_dir.mkdir(parents=True, exist_ok=True)
    assignments_path = output_dir / ASSIGNMENTS_NAME
    periods_path = output_dir / PERIODS_NAME
    _write_csv(assignments_path, assignments)
    _write_csv(periods_path, periods)

    scored = tuple(row for row in periods if row["scored"] == "true")
    weighted_hours = math.fsum(float(row["annual_weight"]) for row in scored)
    representatives = []
    for week, weight in zip(
        plan.representatives,
        plan.representative_weights,
        strict=True,
    ):
        metric = plan.week_metrics[week]
        representatives.append(
            {
                "week_index": week + 1,
                "start": metric.start.isoformat(),
                "end": metric.end.isoformat(),
                "roles": list(plan.roles_by_week[week]),
                "weight_weeks": weight,
            }
        )

    final_one_based = tuple(item + 1 for item in plan.representatives)
    tail_matches = _tail_matches_d36(periods, d36_periods_path)
    audit_passed = (
        len(assignments) == COMPLETE_WEEK_COUNT
        and len(set(plan.assignments)) == REPRESENTATIVE_WEEK_COUNT
        and sum(plan.representative_weights) == COMPLETE_WEEK_COUNT
        and min(plan.representative_weights) >= 1
        and len(periods) == MODEL_PERIOD_COUNT
        and len(scored) == SCORED_SOURCE_ROW_COUNT
        and math.isclose(weighted_hours, YEAR_HOURS, rel_tol=0.0, abs_tol=1e-9)
        and tail_matches
        and (
            not plan.formal_locked
            or final_one_based == LOCKED_D39_REPRESENTATIVE_WEEKS
        )
    )
    manifest: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "contract": CONTRACT_PATH,
        "claim_scope": (
            "service_aware_representative_week_refinement_"
            "not_technology_comparison_not_formal_project_tac"
        ),
        "formal_project_tac_ready": False,
        "source_data": {
            "scope": DATA_SCOPE,
            "formal_heat_sha256": FORMAL_HEAT_SHA256,
            "legacy_vre_sha256": LEGACY_VRE_SHA256,
            "hour_count": YEAR_HOURS,
            "source_artifacts": source_artifacts or {},
        },
        "calendar_contract": {
            "complete_week_count": COMPLETE_WEEK_COUNT,
            "representative_week_count": REPRESENTATIVE_WEEK_COUNT,
            "tail_warmup_hours": TAIL_WARMUP_HOURS,
            "tail_scored_hours": TAIL_SCORED_HOURS,
            "model_period_count": len(periods),
            "scored_source_row_count": len(scored),
            "weighted_scored_hours": weighted_hours,
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
            "assignment_tie_break": "lowest_representative_week_index",
        },
        "selection_contract": {
            "algorithm": "retain_d36_plus_d38_baseline_top2_underrepresentation",
            "original_d36_week_indices": [
                item + 1 for item in plan.original_representatives
            ],
            "added_week_indices_ranked": [
                item + 1 for item in plan.added_weeks_ranked
            ],
            "final_week_indices_sorted": list(final_one_based),
            "distance_tolerance": DISTANCE_TOLERANCE,
            "all_52_weeks_reassigned": True,
            "final_feature_distance_objective": (
                plan.final_feature_distance_objective
            ),
        },
        "representatives": representatives,
        "aggregate_reconstruction_diagnostics": _aggregate_diagnostics(
            plan,
            periods,
        ),
        "boundary_handoff": {
            "optimization_run_in_d39_gate_a": False,
            "representative_weeks_are_independent_cyclic_blocks": True,
            "tail_has_24h_unscored_warmup_and_48h_scored_segment": True,
            "cross_block_chronological_state_transfer_allowed": False,
        },
        "audit": {
            "passed": audit_passed,
            "all_52_weeks_assigned_once": len(assignments) == COMPLETE_WEEK_COUNT,
            "representative_weights_sum": sum(plan.representative_weights),
            "each_representative_weight_at_least_one": (
                min(plan.representative_weights) >= 1
            ),
            "d36_tail_fields_unchanged": tail_matches,
            "canonical_line_endings": "LF",
        },
        "canonical_files": {
            ASSIGNMENTS_NAME: _sha256(assignments_path),
            PERIODS_NAME: _sha256(periods_path),
        },
    }
    if not audit_passed:
        raise AssertionError("E0-D-39 Gate A structural audit failed")
    _write_json(output_dir / MANIFEST_NAME, manifest)
    return manifest


def _verify_formal_inputs(
    heat_path: Path,
    vre_path: Path,
    d36_assignments_path: Path,
    d36_periods_path: Path,
    diagnostic_path: Path,
) -> dict[str, str]:
    expected = {
        "formal_heat_sha256": FORMAL_HEAT_SHA256,
        "legacy_vre_sha256": LEGACY_VRE_SHA256,
        "d36_assignments_sha256": D36_ASSIGNMENTS_SHA256,
        "d36_periods_sha256": D36_PERIODS_SHA256,
        "d38_failure_diagnostic_sha256": D38_FAILURE_DIAGNOSTIC_SHA256,
    }
    actual = {
        "formal_heat_sha256": _sha256(heat_path),
        "legacy_vre_sha256": _sha256(vre_path),
        "d36_assignments_sha256": _sha256(d36_assignments_path),
        "d36_periods_sha256": _sha256(d36_periods_path),
        "d38_failure_diagnostic_sha256": _sha256(diagnostic_path),
    }
    if actual != expected:
        raise ValueError(f"formal D39 input hash mismatch: {actual}")
    d36_representatives = tuple(
        sorted(
            {
                int(row["assigned_representative_week_index"])
                for row in _read_csv(d36_assignments_path)
            }
        )
    )
    if d36_representatives != LOCKED_D36_REPRESENTATIVE_WEEKS:
        raise ValueError("D36 assignments do not contain the locked six weeks")
    return actual


def build_bundle(
    heat_path: Path,
    vre_path: Path,
    d36_assignments_path: Path,
    d36_periods_path: Path,
    diagnostic_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    started = perf_counter()
    source_artifacts = _verify_formal_inputs(
        heat_path,
        vre_path,
        d36_assignments_path,
        d36_periods_path,
        diagnostic_path,
    )
    source_artifacts.update(constructor_code_hashes())
    diagnostic = _read_json(diagnostic_path)
    plan = build_service_aware_plan(
        load_e0d17_inputs(heat_path, vre_path),
        diagnostic,
        require_formal_lock=True,
    )
    manifest = export_service_aware_plan(
        plan,
        output_dir,
        source_artifacts=source_artifacts,
        d36_periods_path=d36_periods_path,
    )
    execution = {
        "schema_id": f"{SCHEMA_ID}.execution",
        "generated_at": datetime.now().astimezone().isoformat(),
        "runtime_seconds": perf_counter() - started,
        "python_version": sys.version,
        "platform": platform.platform(),
        "source_paths": {
            "heat": str(heat_path),
            "vre": str(vre_path),
            "d36_assignments": str(d36_assignments_path),
            "d36_periods": str(d36_periods_path),
            "d38_failure_diagnostic": str(diagnostic_path),
        },
        "canonical_manifest_sha256": _sha256(output_dir / MANIFEST_NAME),
    }
    _write_json(output_dir / EXECUTION_NAME, execution)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heat-path", type=Path, required=True)
    parser.add_argument("--vre-path", type=Path, required=True)
    parser.add_argument("--d36-assignments-path", type=Path, required=True)
    parser.add_argument("--d36-periods-path", type=Path, required=True)
    parser.add_argument("--diagnostic-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(
        json.dumps(
            build_bundle(
                args.heat_path,
                args.vre_path,
                args.d36_assignments_path,
                args.d36_periods_path,
                args.diagnostic_path,
                args.output_dir,
            ),
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
