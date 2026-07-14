"""Deterministic exporter for the E0-D-31 intertemporal OBBT screen."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Sequence

from tes_bess_boundary.alternative_dispatch_envelope import (
    E0D19_CSV_SHA256,
    E0D19_MANIFEST_SHA256,
    E0D22_EXPOSURE_SHA256,
    E0D22_MANIFEST_SHA256,
    E0D22_TRACE_SHA256,
)
from tes_bess_boundary.d26_numerical_certification import (
    KNOWN_WITNESS_TOLERANCE_MWH,
    STRICT_FEASIBILITY_TOLERANCE,
)
from tes_bess_boundary.d29_export_linked_bound_tightening import (
    D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH,
)
from tes_bess_boundary.d31_intertemporal_obbt import (
    D31_PROBE_SCHEMA,
    D31_SCREEN_SCHEMA,
)
from tes_bess_boundary.e0d17_exploration import (
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
)


D31_BUNDLE_SCHEMA = "tes_bess_boundary.e0d31_intertemporal_obbt_screening.v1"
CANONICAL_FLOAT_DECIMALS = 9
GLOBAL_PROBE_MATERIALITY_THRESHOLD_FRACTION = 0.01
EXPECTED_SCREENS = {
    "screen_24h.json": ("winter_day_20240101", 24),
    "screen_336h.json": ("winter_fortnight_20240101", 336),
}
EXPECTED_PROBE = "24h.json"


@dataclass(frozen=True)
class D31ScreeningRecord:
    window_id: str
    hours: int
    workers: int
    lp_solve_count: int
    optimal_lp_solve_count: int
    known_d19_witness_within_bounds: bool
    d30_mean_positive_sign_width_mw: float
    d30_mean_negative_sign_width_mw: float
    d31_mean_positive_sign_width_mw: float
    d31_mean_negative_sign_width_mw: float
    positive_width_reduction_vs_d30_fraction: float
    negative_width_reduction_vs_d30_fraction: float
    screening_metric_fraction: float
    global_probe_materiality_threshold_fraction: float
    global_probe_launched: bool
    exact_24h_equivalence_gate_passed: bool
    retained_strict_global_lower_bound_mwh: float
    retained_strict_global_upper_bound_mwh: float
    global_dual_is_valid_l1_upper_bound: bool
    feasible_set_changed_for_integer_solutions: bool
    all_integer_domains_relaxed: bool
    intertemporal_constraints_retained: bool
    actual_price_path_assigned: bool
    formal_tac: bool
    e1_ready: bool
    scientific_status: str


@dataclass(frozen=True)
class D31BundleExport:
    csv_path: Path
    manifest_path: Path
    execution_path: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(payload: dict[str, object], key: str, *, label: str) -> float:
    try:
        value = float(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} has no finite {key}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label} has no finite {key}")
    return value


def _load_screens(source: Path) -> dict[str, dict[str, object]]:
    screens: dict[str, dict[str, object]] = {}
    reference_locks: tuple[str, str] | None = None
    for filename, (window_id, hours) in EXPECTED_SCREENS.items():
        path = source / filename
        if not path.is_file():
            raise ValueError(f"D31 bundle is missing {filename}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != D31_SCREEN_SCHEMA:
            raise ValueError(f"D31 screen schema mismatch: {filename}")
        if payload.get("window_id") != window_id or int(payload.get("hours", 0)) != hours:
            raise ValueError(f"D31 screen identity mismatch: {filename}")
        if payload.get("known_d19_witness_within_bounds") is not True:
            raise ValueError(f"D31 screen excludes the D19 witness: {filename}")
        if any(
            payload.get(key) is not False
            for key in ("actual_price_path_assigned", "formal_tac", "e1_ready")
        ):
            raise ValueError(f"D31 screen crosses its scientific boundary: {filename}")
        locks = (
            str(payload.get("reference_d30_csv_sha256")),
            str(payload.get("reference_d30_manifest_sha256")),
        )
        if reference_locks is None:
            reference_locks = locks
        elif locks != reference_locks:
            raise ValueError("D31 screens disagree on the D30 certificate identity")
        audit = payload.get("bound_audit")
        comparator = payload.get("comparator")
        candidate = payload.get("candidate")
        if not all(isinstance(item, dict) for item in (audit, comparator, candidate)):
            raise ValueError(f"D31 screen audit is incomplete: {filename}")
        assert isinstance(audit, dict)
        assert isinstance(comparator, dict)
        assert isinstance(candidate, dict)
        if (
            int(audit.get("periods", 0)) != hours
            or int(audit.get("per_period_cut_count", 0)) != 6 * hours
            or audit.get("feasible_set_changed_for_integer_solutions") is not False
            or audit.get("all_integer_domains_relaxed") is not True
            or audit.get("intertemporal_constraints_retained") is not True
            or audit.get("annual_service_and_admissibility_retained") is not True
            or int(comparator.get("lp_solve_count", 0)) != 2 * hours
            or int(candidate.get("lp_solve_count", 0)) != 2 * hours
            or int(comparator.get("optimal_lp_solve_count", 0)) != 2 * hours
            or int(candidate.get("optimal_lp_solve_count", 0)) != 2 * hours
        ):
            raise ValueError(f"D31 screen audit is inconsistent: {filename}")
        reference_lower = _finite(
            payload, "reference_d30_lower_bound_mwh", label=filename
        )
        reference_upper = _finite(
            payload, "reference_d30_upper_bound_mwh", label=filename
        )
        if reference_upper + KNOWN_WITNESS_TOLERANCE_MWH < reference_lower:
            raise ValueError(f"D31 screen D30 interval is reversed: {filename}")
        screens[filename] = payload
    return screens


def _load_24h_probe(
    source: Path,
    screen: dict[str, object],
) -> dict[str, object]:
    path = source / EXPECTED_PROBE
    if not path.is_file():
        raise ValueError("D31 bundle is missing the 24 h equivalence probe")
    if (source / "336h.json").exists():
        raise ValueError("D31 negative screen must not contain a 336 h global probe")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema") != D31_PROBE_SCHEMA
        or payload.get("window_id") != "winter_day_20240101"
        or int(payload.get("hours", 0)) != 24
    ):
        raise ValueError("D31 24 h probe identity mismatch")
    if payload.get("d31_screen_sha256") != _sha256(source / "screen_24h.json"):
        raise ValueError("D31 24 h screen/probe hash mismatch")
    for key in (
        "reference_d30_csv_sha256",
        "reference_d30_manifest_sha256",
        "reference_d30_screen_sha256",
    ):
        if payload.get(key) != screen.get(key):
            raise ValueError(f"D31 24 h source lock mismatch: {key}")
    if (
        payload.get("exact_global_maximum") is not True
        or payload.get("known_witness_within_bounds") is not True
        or payload.get("witness_dominance_passed") is not True
        or payload.get("global_dual_is_valid_l1_upper_bound") is not True
    ):
        raise ValueError("D31 24 h equivalence gate failed")
    if not math.isclose(
        _finite(
            payload,
            "witness_dominance_tolerance_mwh",
            label="24h.json",
        ),
        D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH,
        rel_tol=0.0,
        abs_tol=0.0,
    ):
        raise ValueError("D31 24 h witness tolerance contract mismatch")
    if any(
        payload.get(key) is not False
        for key in ("actual_price_path_assigned", "formal_tac", "e1_ready")
    ):
        raise ValueError("D31 24 h probe crosses its scientific boundary")
    residual = _finite(
        payload,
        "maximum_positive_normalized_constraint_residual",
        label="24h.json",
    )
    mismatch = _finite(
        payload,
        "auxiliary_objective_mismatch_mwh",
        label="24h.json",
    )
    if residual > STRICT_FEASIBILITY_TOLERANCE:
        raise ValueError("D31 24 h strict feasibility failed")
    if abs(mismatch) > D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH:
        raise ValueError("D31 24 h objective recomputation failed")
    lower = _finite(payload, "strict_global_lower_bound_mwh", label="24h.json")
    upper = _finite(payload, "strict_global_upper_bound_mwh", label="24h.json")
    reference_lower = _finite(
        payload, "reference_d30_lower_bound_mwh", label="24h.json"
    )
    reference_upper = _finite(
        payload, "reference_d30_upper_bound_mwh", label="24h.json"
    )
    if max(abs(lower - reference_lower), abs(upper - reference_upper)) > (
        KNOWN_WITNESS_TOLERANCE_MWH
    ):
        raise ValueError("D31 24 h gate does not retain the exact D30 interval")
    return payload


def _records(
    screens: dict[str, dict[str, object]],
    probe: dict[str, object],
) -> tuple[D31ScreeningRecord, ...]:
    records: list[D31ScreeningRecord] = []
    for filename, payload in screens.items():
        hours = int(payload["hours"])
        audit = payload["bound_audit"]
        comparator = payload["comparator"]
        candidate = payload["candidate"]
        assert isinstance(audit, dict)
        assert isinstance(comparator, dict)
        assert isinstance(candidate, dict)
        positive = _finite(
            audit,
            "positive_width_reduction_vs_d30_fraction",
            label=filename,
        )
        negative = _finite(
            audit,
            "negative_width_reduction_vs_d30_fraction",
            label=filename,
        )
        metric = max(positive, negative)
        launched = hours == 24
        if hours == 336 and metric >= GLOBAL_PROBE_MATERIALITY_THRESHOLD_FRACTION:
            raise ValueError("D31 336 h screen passes the gate but has no global probe")
        if hours == 24:
            lower = _finite(
                probe, "strict_global_lower_bound_mwh", label="24h.json"
            )
            upper = _finite(
                probe, "strict_global_upper_bound_mwh", label="24h.json"
            )
            exact_gate = True
            global_dual = True
            status = "exact_24h_equivalence_gate_passed_not_formal_tac"
        else:
            lower = _finite(
                payload, "reference_d30_lower_bound_mwh", label=filename
            )
            upper = _finite(
                payload, "reference_d30_upper_bound_mwh", label=filename
            )
            exact_gate = False
            global_dual = True
            status = (
                "negative_obbt_screen_336h_global_probe_not_launched_"
                "d30_interval_retained"
            )
        records.append(
            D31ScreeningRecord(
                window_id=str(payload["window_id"]),
                hours=hours,
                workers=int(payload["workers"]),
                lp_solve_count=int(comparator["lp_solve_count"])
                + int(candidate["lp_solve_count"]),
                optimal_lp_solve_count=int(comparator["optimal_lp_solve_count"])
                + int(candidate["optimal_lp_solve_count"]),
                known_d19_witness_within_bounds=True,
                d30_mean_positive_sign_width_mw=_finite(
                    audit, "d30_mean_positive_sign_width_mw", label=filename
                ),
                d30_mean_negative_sign_width_mw=_finite(
                    audit, "d30_mean_negative_sign_width_mw", label=filename
                ),
                d31_mean_positive_sign_width_mw=_finite(
                    audit, "d31_mean_positive_sign_width_mw", label=filename
                ),
                d31_mean_negative_sign_width_mw=_finite(
                    audit, "d31_mean_negative_sign_width_mw", label=filename
                ),
                positive_width_reduction_vs_d30_fraction=positive,
                negative_width_reduction_vs_d30_fraction=negative,
                screening_metric_fraction=metric,
                global_probe_materiality_threshold_fraction=(
                    GLOBAL_PROBE_MATERIALITY_THRESHOLD_FRACTION
                ),
                global_probe_launched=launched,
                exact_24h_equivalence_gate_passed=exact_gate,
                retained_strict_global_lower_bound_mwh=lower,
                retained_strict_global_upper_bound_mwh=upper,
                global_dual_is_valid_l1_upper_bound=global_dual,
                feasible_set_changed_for_integer_solutions=False,
                all_integer_domains_relaxed=True,
                intertemporal_constraints_retained=True,
                actual_price_path_assigned=False,
                formal_tac=False,
                e1_ready=False,
                scientific_status=status,
            )
        )
    return tuple(records)


def _csv_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.{CANONICAL_FLOAT_DECIMALS}f}"
    return str(value)


def write_bundle(probe_dir: str | Path, output_dir: str | Path) -> D31BundleExport:
    source = Path(probe_dir)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    screens = _load_screens(source)
    probe = _load_24h_probe(source, screens["screen_24h.json"])
    records = _records(screens, probe)
    csv_path = destination / "e0d31_intertemporal_obbt_screening.csv"
    fieldnames = tuple(asdict(records[0]))
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow(
                {key: _csv_value(value) for key, value in asdict(record).items()}
            )

    execution_path = destination / "execution.json"
    execution = {
        "canonical": False,
        "screens": {
            payload["window_id"]: {
                "wall_runtime_seconds": payload["wall_runtime_seconds"],
                "workers": payload["workers"],
                "comparator_workers": payload["comparator_workers"],
                "candidate_workers": payload["candidate_workers"],
                "comparator_solver_runtime_seconds": payload["comparator"][
                    "solver_runtime_seconds"
                ],
                "candidate_solver_runtime_seconds": payload["candidate"][
                    "solver_runtime_seconds"
                ],
                "comparator_solver_retry_count": payload["comparator"][
                    "solver_retry_count"
                ],
                "candidate_solver_retry_count": payload["candidate"][
                    "solver_retry_count"
                ],
            }
            for payload in screens.values()
        },
        "equivalence_probe_24h": {
            "runtime_seconds": probe["runtime_seconds"],
            "time_limit_seconds": probe["time_limit_seconds"],
            "threads": probe["threads"],
        },
        "global_probe_336h_launched": False,
    }
    execution_path.write_text(
        json.dumps(execution, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    source_dir = Path(__file__).resolve().parent
    first_screen = screens["screen_24h.json"]
    manifest_path = destination / "manifest.json"
    manifest = {
        "schema": D31_BUNDLE_SCHEMA,
        "scientific_scope": (
            "intertemporal_continuous_relaxation_obbt_screening_"
            "not_settlement_or_tac"
        ),
        "screening_gate": {
            "metric": "max_positive_or_negative_mean_sign_width_reduction_vs_d30",
            "threshold_fraction": GLOBAL_PROBE_MATERIALITY_THRESHOLD_FRACTION,
            "adopted_after_obbt_screen_before_any_336h_global_probe": True,
            "preregistered_before_obbt_results": False,
            "global_probe_336h_launched": False,
        },
        "output": {
            "csv": csv_path.name,
            "csv_sha256": _sha256(csv_path),
            "rows": len(records),
            "float_decimals": CANONICAL_FLOAT_DECIMALS,
        },
        "execution_sidecar": {
            "file": execution_path.name,
            "sha256": _sha256(execution_path),
            "canonical": False,
        },
        "screens": {
            filename: _sha256(source / filename) for filename in EXPECTED_SCREENS
        },
        "probes": {EXPECTED_PROBE: _sha256(source / EXPECTED_PROBE)},
        "source_locks": {
            "formal_heat_sha256": FORMAL_HEAT_SHA256,
            "legacy_vre_sha256": LEGACY_VRE_SHA256,
            "d19_csv_sha256": E0D19_CSV_SHA256,
            "d19_manifest_sha256": E0D19_MANIFEST_SHA256,
            "d22_trace_sha256": E0D22_TRACE_SHA256,
            "d22_exposure_sha256": E0D22_EXPOSURE_SHA256,
            "d22_manifest_sha256": E0D22_MANIFEST_SHA256,
            "d30_csv_sha256": first_screen["reference_d30_csv_sha256"],
            "d30_manifest_sha256": first_screen["reference_d30_manifest_sha256"],
        },
        "sources": {
            "d31_intertemporal_obbt.py": _sha256(
                source_dir / "d31_intertemporal_obbt.py"
            ),
            "d31_screening_bundle.py": _sha256(Path(__file__)),
        },
        "relaxation_contract": {
            "all_integer_domains_relaxed": True,
            "intertemporal_constraints_retained": True,
            "annual_service_and_admissibility_retained": True,
            "feasible_set_changed_for_integer_solutions": False,
            "primary_integer_patterns_reopened": True,
            "sign_binaries_reopened": True,
        },
        "scientific_boundary": {
            "latest_336h_global_bound_source": "E0-D-30",
            "global_dual_is_valid_l1_upper_bound": True,
            "actual_price_path_assigned": False,
            "formal_tac": False,
            "e1_ready": False,
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return D31BundleExport(csv_path, manifest_path, execution_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the E0-D-31 screening bundle.")
    parser.add_argument("--probe-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    result = write_bundle(args.probe_dir, args.output_dir)
    print(result.csv_path)
    print(result.manifest_path)
    print(result.execution_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
