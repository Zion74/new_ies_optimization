"""Export-linked valid inequalities for the open 336 h global L1 bound.

E0-D-29 preserves the D19 admissible dispatch set and the exact D27
positive/negative sign formulation.  It adds inequalities linking each
positive or negative PCC difference to the export and unused PCC headroom of
the two architectures.  The cuts remove fractional sign artefacts without
fixing any primary or sign binary.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter
from typing import Sequence

from tes_bess_boundary.alternative_dispatch_envelope import (
    RedistributionDirection,
    _seed_joint_model,
    _solve_d19_selected_model,
    build_joint_redistribution_model,
    load_e0d23_source_rows,
)
from tes_bess_boundary.d26_numerical_certification import (
    KNOWN_WITNESS_TOLERANCE_MWH,
    STRICT_FEASIBILITY_TOLERANCE,
    IntegerScope,
    _build_cases,
    _fix_integer_pattern,
    _strict_solve,
    _window_mip_gap,
)
from tes_bess_boundary.d27_certification_bundle import D27_BUNDLE_SCHEMA
from tes_bess_boundary.d27_direction_generation import (
    _replace_big_m_with_disaggregated_sign_formulation,
    _seed_joint_from_joint,
)
from tes_bess_boundary.e0d17_exploration import (
    DEFAULT_WINDOWS,
    E0D17WindowSpec,
    _window_rows,
    load_e0d17_inputs,
)


D29_PROBE_SCHEMA = "tes_bess_boundary.e0d29_export_linked_bound_tightening.v1"
D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH = 1e-4


@dataclass(frozen=True)
class D27MaximumReference:
    window_id: str
    hours: int
    strict_global_lower_bound_mwh: float
    strict_global_upper_bound_mwh: float
    csv_sha256: str
    manifest_sha256: str


@dataclass(frozen=True)
class D29CutAudit:
    periods: int
    per_period_cut_count: int
    aggregate_cut_count: int
    weighted_hours: float
    pcc_capacity_mw: float
    target_export_mwh: float
    capacity_headroom_mwh: float
    primary_integer_patterns_reopened: bool = True
    sign_binaries_reopened: bool = True
    feasible_set_changed_for_integer_solutions: bool = False


@dataclass(frozen=True)
class D29GlobalProbe:
    schema: str
    window_id: str
    hours: int
    threads: int
    time_limit_seconds: float
    reference_d27_lower_bound_mwh: float
    reference_d27_upper_bound_mwh: float
    reference_d27_csv_sha256: str
    reference_d27_manifest_sha256: str
    selected_face_witness_mwh: float
    selected_face_termination: str
    selected_face_bound_certificate_complete: bool
    cut_audit: D29CutAudit
    termination: str
    runtime_seconds: float
    primal_bound_mwh: float
    recomputed_redistribution_mwh: float
    dual_bound_mwh: float | None
    relative_gap: float | None
    bound_certificate_complete: bool
    witness_dominance_passed: bool
    maximum_positive_normalized_constraint_residual: float
    auxiliary_objective_mismatch_mwh: float
    strict_global_lower_bound_mwh: float
    strict_global_upper_bound_mwh: float
    global_upper_bound_improvement_mwh: float
    global_upper_bound_improvement_fraction: float
    global_upper_bound_improved: bool
    exact_global_maximum: bool
    global_dual_is_valid_l1_upper_bound: bool
    actual_price_path_assigned: bool = False
    formal_tac: bool = False
    e1_ready: bool = False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_float(row: dict[str, str], key: str, *, label: str) -> float:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} has no finite {key}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label} has no finite {key}")
    return value


def load_d27_maximum_reference(
    source_dir: str | Path,
    *,
    window_id: str,
) -> D27MaximumReference:
    """Load one hash-verified D27 maximum interval."""

    source = Path(source_dir)
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("D29 is missing the D27 manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != D27_BUNDLE_SCHEMA:
        raise ValueError("D29 D27 manifest schema mismatch")
    output = manifest.get("output")
    if not isinstance(output, dict):
        raise ValueError("D29 D27 manifest has no output contract")
    csv_name = output.get("csv")
    expected_hash = output.get("csv_sha256")
    if not isinstance(csv_name, str) or not isinstance(expected_hash, str):
        raise ValueError("D29 D27 output contract is incomplete")
    csv_path = source / csv_name
    if not csv_path.is_file() or _sha256(csv_path) != expected_hash:
        raise ValueError("D29 D27 certificate hash mismatch")
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = tuple(csv.DictReader(handle))
    matches = tuple(row for row in rows if row.get("window_id") == window_id)
    if len(matches) != 1:
        raise ValueError(f"D29 needs exactly one D27 row for {window_id}")
    row = matches[0]
    if row.get("support_dual_is_global_l1_upper_bound") != "false":
        raise ValueError("D29 D27 support/global boundary mismatch")
    lower = _finite_float(row, "strict_global_lower_bound_mwh", label=window_id)
    upper = _finite_float(row, "strict_global_upper_bound_mwh", label=window_id)
    if upper + KNOWN_WITNESS_TOLERANCE_MWH < lower:
        raise ValueError("D29 D27 reference interval is reversed")
    return D27MaximumReference(
        window_id=window_id,
        hours=int(row["hours"]),
        strict_global_lower_bound_mwh=lower,
        strict_global_upper_bound_mwh=upper,
        csv_sha256=expected_hash,
        manifest_sha256=_sha256(manifest_path),
    )


def add_export_linked_sign_cuts(
    model: object,
    *,
    pcc_capacity_mw: float,
    annual_weights: Sequence[float],
    dt_hours: float,
    target_export_mwh: float,
) -> D29CutAudit:
    """Add valid export/headroom inequalities to the D27 sign model."""

    from pyomo.environ import Constraint

    periods = tuple(model.redistribution_periods)
    weights = tuple(float(weight) for weight in annual_weights)
    if len(periods) == 0 or len(weights) != len(periods):
        raise ValueError("D29 weights do not match the redistribution horizon")
    if any(not math.isfinite(weight) or weight <= 0.0 for weight in weights):
        raise ValueError("D29 annual weights must be finite and positive")
    if not math.isfinite(dt_hours) or dt_hours <= 0.0:
        raise ValueError("D29 dt_hours must be finite and positive")
    if not math.isfinite(pcc_capacity_mw) or pcc_capacity_mw <= 0.0:
        raise ValueError("D29 PCC capacity must be finite and positive")
    if not math.isfinite(target_export_mwh) or target_export_mwh < 0.0:
        raise ValueError("D29 target export must be finite and non-negative")
    required = (
        "d27_delta_positive_mw",
        "d27_delta_negative_mw",
        "delta_nonnegative",
        "comparator",
        "candidate",
    )
    if any(not hasattr(model, name) for name in required):
        raise ValueError("D29 cuts require the D27 disaggregated sign model")
    if hasattr(model, "d29_positive_export_limit"):
        raise ValueError("D29 cuts are already installed")

    weighted_hours = dt_hours * sum(weights)
    capacity_energy = pcc_capacity_mw * weighted_hours
    headroom = capacity_energy - target_export_mwh
    if headroom < -KNOWN_WITNESS_TOLERANCE_MWH:
        raise ValueError("D29 target export exceeds PCC capacity energy")
    headroom = max(0.0, headroom)

    model.d29_positive_export_limit = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.d27_delta_positive_mw[period]
            <= block.candidate.pcc_export[period]
        ),
    )
    model.d29_positive_headroom_limit = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.d27_delta_positive_mw[period]
            <= pcc_capacity_mw - block.comparator.pcc_export[period]
        ),
    )
    model.d29_negative_export_limit = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.d27_delta_negative_mw[period]
            <= block.comparator.pcc_export[period]
        ),
    )
    model.d29_negative_headroom_limit = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.d27_delta_negative_mw[period]
            <= pcc_capacity_mw - block.candidate.pcc_export[period]
        ),
    )
    positive_mass = dt_hours * sum(
        weights[offset] * model.d27_delta_positive_mw[period]
        for offset, period in enumerate(periods)
    )
    negative_mass = dt_hours * sum(
        weights[offset] * model.d27_delta_negative_mw[period]
        for offset, period in enumerate(periods)
    )
    model.d29_signed_mass_balance = Constraint(expr=positive_mass == negative_mass)
    model.d29_positive_export_mass_cap = Constraint(
        expr=positive_mass <= target_export_mwh
    )
    model.d29_negative_export_mass_cap = Constraint(
        expr=negative_mass <= target_export_mwh
    )
    model.d29_positive_headroom_mass_cap = Constraint(expr=positive_mass <= headroom)
    model.d29_negative_headroom_mass_cap = Constraint(expr=negative_mass <= headroom)
    return D29CutAudit(
        periods=len(periods),
        per_period_cut_count=4 * len(periods),
        aggregate_cut_count=5,
        weighted_hours=weighted_hours,
        pcc_capacity_mw=pcc_capacity_mw,
        target_export_mwh=target_export_mwh,
        capacity_headroom_mwh=headroom,
    )


def run_export_linked_bound_probe(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    d19_source_dir: str | Path,
    d22_source_dir: str | Path,
    d27_source_dir: str | Path,
    window: E0D17WindowSpec,
    time_limit_seconds: float,
    threads: int,
    tee: bool = False,
) -> D29GlobalProbe:
    """Solve one reopened global maximum with D29 valid inequalities."""

    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0.0:
        raise ValueError("D29 time limit must be finite and positive")
    if type(threads) is not int or threads <= 0:
        raise ValueError("D29 threads must be a positive integer")
    reference = load_d27_maximum_reference(
        d27_source_dir,
        window_id=window.window_id,
    )
    if reference.hours != window.hours:
        raise ValueError("D29 D27 reference horizon mismatch")

    d19_rows, _ = load_e0d23_source_rows(d19_source_dir, d22_source_dir)
    if window.window_id not in d19_rows:
        raise ValueError(f"D29 window is absent from D19: {window.window_id}")
    inputs = load_e0d17_inputs(heat_path, vre_path)
    rows = _window_rows(inputs, window)
    comparator_case, candidate_case, comparator_cap, candidate_cap, service = (
        _build_cases(rows, d19_rows[window.window_id])
    )

    warm_started = perf_counter()
    comparator_selected = _solve_d19_selected_model(
        comparator_case,
        primary_mip_gap=0.0,
        pcc_service_feasibility_warm_start=False,
    )
    candidate_selected = _solve_d19_selected_model(
        candidate_case,
        primary_mip_gap=_window_mip_gap(window),
        pcc_service_feasibility_warm_start=window.hours > 24,
    )
    warm_runtime = perf_counter() - warm_started

    face_model = build_joint_redistribution_model(
        comparator_case,
        candidate_case,
        comparator_admissibility=comparator_cap,
        candidate_admissibility=candidate_cap,
        direction=RedistributionDirection.MAXIMUM,
    )
    _seed_joint_model(face_model, comparator_selected, candidate_selected)
    fixed_count = _fix_integer_pattern(face_model.comparator, comparator_selected)
    fixed_count += _fix_integer_pattern(face_model.candidate, candidate_selected)
    face_result = _strict_solve(
        face_model,
        comparator_case=comparator_case,
        candidate_case=candidate_case,
        comparator_cap=comparator_cap,
        candidate_cap=candidate_cap,
        pcc_service=service,
        window=window,
        scope=IntegerScope.D19_SELECTED_FACE,
        direction=RedistributionDirection.MAXIMUM,
        fixed_primary_integer_count=fixed_count,
        warm_start_runtime_seconds=warm_runtime,
        time_limit_seconds=min(300.0, time_limit_seconds),
        threads=threads,
        tee=tee,
        allow_incumbent_only=True,
    )

    model = build_joint_redistribution_model(
        comparator_case,
        candidate_case,
        comparator_admissibility=comparator_cap,
        candidate_admissibility=candidate_cap,
        direction=RedistributionDirection.MAXIMUM,
    )
    _seed_joint_from_joint(face_model, model)
    _replace_big_m_with_disaggregated_sign_formulation(
        model,
        pcc_capacity_mw=comparator_case.pcc_export_capacity_mw,
    )
    cut_audit = add_export_linked_sign_cuts(
        model,
        pcc_capacity_mw=comparator_case.pcc_export_capacity_mw,
        annual_weights=comparator_case.economics.horizon.period_weights,
        dt_hours=comparator_case.timeseries.dt_hours,
        target_export_mwh=service.target_export_mwh,
    )
    result = _strict_solve(
        model,
        comparator_case=comparator_case,
        candidate_case=candidate_case,
        comparator_cap=comparator_cap,
        candidate_cap=candidate_cap,
        pcc_service=service,
        window=window,
        scope=IntegerScope.REOPENED,
        direction=RedistributionDirection.MAXIMUM,
        fixed_primary_integer_count=0,
        warm_start_runtime_seconds=warm_runtime,
        time_limit_seconds=time_limit_seconds,
        threads=threads,
        tee=tee,
        conditional_face_warm_start_mwh=face_result.auxiliary_objective_mwh,
        conditional_face_warm_start_runtime_seconds=face_result.runtime_seconds,
        conditional_face_warm_start_termination="d29_selected_face",
        conditional_face_fixed_primary_integer_count=fixed_count,
        allow_incumbent_only=True,
    )
    if result.maximum_positive_normalized_constraint_residual > STRICT_FEASIBILITY_TOLERANCE:
        raise RuntimeError("D29 global incumbent violates strict feasibility")
    if (
        abs(result.auxiliary_objective_mismatch_mwh)
        > D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH
    ):
        raise RuntimeError(
            "D29 global incumbent failed L1 recomputation: "
            f"{result.auxiliary_objective_mismatch_mwh} MWh/a"
        )

    lower = max(
        reference.strict_global_lower_bound_mwh,
        result.recomputed_redistribution_mwh,
    )
    upper = reference.strict_global_upper_bound_mwh
    if result.dual_bound_mwh is not None:
        upper = min(upper, result.dual_bound_mwh)
    improvement = reference.strict_global_upper_bound_mwh - upper
    improvement_fraction = improvement / reference.strict_global_upper_bound_mwh
    exact = upper - lower <= KNOWN_WITNESS_TOLERANCE_MWH
    return D29GlobalProbe(
        schema=D29_PROBE_SCHEMA,
        window_id=window.window_id,
        hours=window.hours,
        threads=threads,
        time_limit_seconds=time_limit_seconds,
        reference_d27_lower_bound_mwh=reference.strict_global_lower_bound_mwh,
        reference_d27_upper_bound_mwh=reference.strict_global_upper_bound_mwh,
        reference_d27_csv_sha256=reference.csv_sha256,
        reference_d27_manifest_sha256=reference.manifest_sha256,
        selected_face_witness_mwh=face_result.auxiliary_objective_mwh,
        selected_face_termination=face_result.termination,
        selected_face_bound_certificate_complete=face_result.bound_certificate_complete,
        cut_audit=cut_audit,
        termination=result.termination,
        runtime_seconds=result.runtime_seconds,
        primal_bound_mwh=result.primal_bound_mwh,
        recomputed_redistribution_mwh=result.recomputed_redistribution_mwh,
        dual_bound_mwh=result.dual_bound_mwh,
        relative_gap=result.relative_gap,
        bound_certificate_complete=result.bound_certificate_complete,
        witness_dominance_passed=(
            result.recomputed_redistribution_mwh + KNOWN_WITNESS_TOLERANCE_MWH
            >= face_result.auxiliary_objective_mwh
        ),
        maximum_positive_normalized_constraint_residual=(
            result.maximum_positive_normalized_constraint_residual
        ),
        auxiliary_objective_mismatch_mwh=result.auxiliary_objective_mismatch_mwh,
        strict_global_lower_bound_mwh=lower,
        strict_global_upper_bound_mwh=upper,
        global_upper_bound_improvement_mwh=improvement,
        global_upper_bound_improvement_fraction=improvement_fraction,
        global_upper_bound_improved=improvement > KNOWN_WITNESS_TOLERANCE_MWH,
        exact_global_maximum=exact,
        global_dual_is_valid_l1_upper_bound=result.bound_certificate_complete,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the E0-D-29 export-linked global-bound probe."
    )
    parser.add_argument("--heat-path", required=True, type=Path)
    parser.add_argument("--vre-path", required=True, type=Path)
    parser.add_argument("--d19-source-dir", required=True, type=Path)
    parser.add_argument("--d22-source-dir", required=True, type=Path)
    parser.add_argument("--d27-source-dir", required=True, type=Path)
    parser.add_argument(
        "--window",
        required=True,
        choices=tuple(window.window_id for window in DEFAULT_WINDOWS),
    )
    parser.add_argument("--time-limit-seconds", required=True, type=float)
    parser.add_argument("--threads", type=int, default=28)
    parser.add_argument("--tee", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    window = next(item for item in DEFAULT_WINDOWS if item.window_id == args.window)
    result = run_export_linked_bound_probe(
        args.heat_path,
        args.vre_path,
        d19_source_dir=args.d19_source_dir,
        d22_source_dir=args.d22_source_dir,
        d27_source_dir=args.d27_source_dir,
        window=window,
        time_limit_seconds=args.time_limit_seconds,
        threads=args.threads,
        tee=args.tee,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.output.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
