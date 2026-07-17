"""Deterministic exporter for E0-D-30 PCC-bound screens and global probes."""

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
from tes_bess_boundary.d30_physics_service_bound_tightening import (
    D30_PROBE_SCHEMA,
    D30_SCREEN_SCHEMA,
)
from tes_bess_boundary.e0d17_exploration import (
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
)


D30_BUNDLE_SCHEMA = "tes_bess_boundary.e0d30_physics_service_bound_certificate.v1"
CANONICAL_FLOAT_DECIMALS = 9
D29_CSV_SHA256 = "85fe459cebfd6f058d58e76f4358293630c80dfe3229cd5d6c8e366a78e26811"
D29_MANIFEST_SHA256 = (
    "8c3924e49421a68e6179a2eef69eca699ac43392e895f07be357052bf821a11a"
)
EXPECTED_PROBES = {
    "24h.json": ("winter_day_20240101", 24),
    "336h.json": ("winter_fortnight_20240101", 336),
}
EXPECTED_SCREENS = {
    "screen_24h.json": ("winter_day_20240101", 24),
    "screen_336h.json": ("winter_fortnight_20240101", 336),
}


@dataclass(frozen=True)
class D30CertificateRecord:
    window_id: str
    hours: int
    per_period_cut_count: int
    mean_positive_sign_width_mw: float
    mean_negative_sign_width_mw: float
    positive_sign_width_reduction_fraction: float
    negative_sign_width_reduction_fraction: float
    selected_face_witness_mwh: float
    reference_d29_lower_bound_mwh: float
    reference_d29_upper_bound_mwh: float
    primal_bound_mwh: float
    recomputed_redistribution_mwh: float
    dual_bound_mwh: float
    relative_gap: float
    termination: str
    strict_global_lower_bound_mwh: float
    strict_global_upper_bound_mwh: float
    global_upper_bound_improvement_mwh: float
    global_upper_bound_improvement_fraction: float
    global_upper_bound_improved: bool
    exact_global_maximum: bool
    witness_reference_excess_mwh: float
    witness_clamped_to_reference: bool
    dual_reference_deficit_mwh: float
    dual_clamped_to_reference_lower: bool
    maximum_positive_normalized_constraint_residual: float
    auxiliary_objective_mismatch_mwh: float
    known_witness_within_bounds: bool
    feasible_set_changed_for_integer_solutions: bool
    primary_integer_patterns_reopened: bool
    sign_binaries_reopened: bool
    global_dual_is_valid_l1_upper_bound: bool
    actual_price_path_assigned: bool
    formal_tac: bool
    e1_ready: bool
    scientific_status: str


@dataclass(frozen=True)
class D30BundleExport:
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
    for filename, (window_id, hours) in EXPECTED_SCREENS.items():
        path = source / filename
        if not path.is_file():
            raise ValueError(f"D30 bundle is missing {filename}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != D30_SCREEN_SCHEMA:
            raise ValueError(f"D30 screen schema mismatch: {filename}")
        if payload.get("window_id") != window_id or int(payload.get("hours", 0)) != hours:
            raise ValueError(f"D30 screen identity mismatch: {filename}")
        if any(
            payload.get(key) is not False
            for key in ("actual_price_path_assigned", "formal_tac", "e1_ready")
        ):
            raise ValueError(f"D30 screen crosses its scientific boundary: {filename}")
        audit = payload.get("bound_audit")
        if not isinstance(audit, dict):
            raise ValueError(f"D30 screen has no bound audit: {filename}")
        if (
            int(audit.get("periods", 0)) != hours
            or int(audit.get("per_period_cut_count", 0)) != 6 * hours
            or audit.get("feasible_set_changed_for_integer_solutions") is not False
            or audit.get("primary_integer_patterns_reopened") is not True
            or audit.get("sign_binaries_reopened") is not True
        ):
            raise ValueError(f"D30 screen audit is inconsistent: {filename}")
        screens[filename] = payload
    return screens


def _load_probes(
    source: Path,
    screens: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    probes: dict[str, dict[str, object]] = {}
    screen_by_window = {
        str(payload["window_id"]): payload for payload in screens.values()
    }
    for filename, (window_id, hours) in EXPECTED_PROBES.items():
        path = source / filename
        if not path.is_file():
            raise ValueError(f"D30 bundle is missing {filename}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != D30_PROBE_SCHEMA:
            raise ValueError(f"D30 probe schema mismatch: {filename}")
        if payload.get("window_id") != window_id or int(payload.get("hours", 0)) != hours:
            raise ValueError(f"D30 probe identity mismatch: {filename}")
        if payload.get("reference_d29_csv_sha256") != D29_CSV_SHA256:
            raise ValueError(f"D30 D29 CSV source lock mismatch: {filename}")
        if payload.get("reference_d29_manifest_sha256") != D29_MANIFEST_SHA256:
            raise ValueError(f"D30 D29 manifest source lock mismatch: {filename}")
        if payload.get("known_witness_within_bounds") is not True:
            raise ValueError(f"D30 known witness lies outside bounds: {filename}")
        if payload.get("witness_dominance_passed") is not True:
            raise ValueError(f"D30 witness dominance failed: {filename}")
        if payload.get("global_dual_is_valid_l1_upper_bound") is not True:
            raise ValueError(f"D30 global dual is incomplete: {filename}")
        if any(
            payload.get(key) is not False
            for key in ("actual_price_path_assigned", "formal_tac", "e1_ready")
        ):
            raise ValueError(f"D30 probe crosses its scientific boundary: {filename}")
        audit = payload.get("bound_audit")
        if not isinstance(audit, dict) or audit != screen_by_window[window_id].get(
            "bound_audit"
        ):
            raise ValueError(f"D30 screen/probe audit mismatch: {filename}")
        residual = _finite(
            payload,
            "maximum_positive_normalized_constraint_residual",
            label=filename,
        )
        mismatch = _finite(
            payload,
            "auxiliary_objective_mismatch_mwh",
            label=filename,
        )
        if residual > STRICT_FEASIBILITY_TOLERANCE:
            raise ValueError(f"D30 strict feasibility failed: {filename}")
        if abs(mismatch) > D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH:
            raise ValueError(f"D30 objective recomputation failed: {filename}")
        reference_lower = _finite(
            payload, "reference_d29_lower_bound_mwh", label=filename
        )
        reference_upper = _finite(
            payload, "reference_d29_upper_bound_mwh", label=filename
        )
        strict_lower = _finite(
            payload, "strict_global_lower_bound_mwh", label=filename
        )
        strict_upper = _finite(
            payload, "strict_global_upper_bound_mwh", label=filename
        )
        dual = _finite(payload, "dual_bound_mwh", label=filename)
        tolerance = D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH
        if strict_lower + tolerance < reference_lower:
            raise ValueError(f"D30 loses the D29 lower bound: {filename}")
        if strict_upper > reference_upper + tolerance:
            raise ValueError(f"D30 loses the D29 upper bound: {filename}")
        if strict_upper > dual + tolerance:
            raise ValueError(f"D30 strict upper exceeds its global dual: {filename}")
        if strict_upper + tolerance < strict_lower:
            raise ValueError(f"D30 strict interval is reversed: {filename}")
        recomputed = _finite(
            payload, "recomputed_redistribution_mwh", label=filename
        )
        witness_excess = _finite(
            payload, "witness_reference_excess_mwh", label=filename
        )
        if abs(witness_excess - (recomputed - reference_upper)) > (
            KNOWN_WITNESS_TOLERANCE_MWH
        ):
            raise ValueError(f"D30 witness excess audit is malformed: {filename}")
        probes[filename] = payload
    return probes


def _records(probes: dict[str, dict[str, object]]) -> tuple[D30CertificateRecord, ...]:
    records: list[D30CertificateRecord] = []
    for filename in EXPECTED_PROBES:
        payload = probes[filename]
        audit = payload["bound_audit"]
        improved = bool(payload["global_upper_bound_improved"])
        exact = bool(payload["exact_global_maximum"])
        status = (
            "exact_reference_interval_retained_not_formal_tac"
            if exact and not improved
            else (
                "strict_global_upper_bound_tightened_not_formal_tac"
                if improved
                else "strict_global_interval_retained_not_formal_tac"
            )
        )
        dual_deficit = payload.get("dual_reference_deficit_mwh")
        if dual_deficit is None:
            raise ValueError(f"D30 probe has no finite dual deficit audit: {filename}")
        records.append(
            D30CertificateRecord(
                window_id=str(payload["window_id"]),
                hours=int(payload["hours"]),
                per_period_cut_count=int(audit["per_period_cut_count"]),
                mean_positive_sign_width_mw=float(audit["mean_positive_sign_width_mw"]),
                mean_negative_sign_width_mw=float(audit["mean_negative_sign_width_mw"]),
                positive_sign_width_reduction_fraction=float(
                    audit["positive_sign_width_reduction_fraction"]
                ),
                negative_sign_width_reduction_fraction=float(
                    audit["negative_sign_width_reduction_fraction"]
                ),
                selected_face_witness_mwh=_finite(
                    payload, "selected_face_witness_mwh", label=filename
                ),
                reference_d29_lower_bound_mwh=_finite(
                    payload, "reference_d29_lower_bound_mwh", label=filename
                ),
                reference_d29_upper_bound_mwh=_finite(
                    payload, "reference_d29_upper_bound_mwh", label=filename
                ),
                primal_bound_mwh=_finite(payload, "primal_bound_mwh", label=filename),
                recomputed_redistribution_mwh=_finite(
                    payload, "recomputed_redistribution_mwh", label=filename
                ),
                dual_bound_mwh=_finite(payload, "dual_bound_mwh", label=filename),
                relative_gap=_finite(payload, "relative_gap", label=filename),
                termination=str(payload["termination"]),
                strict_global_lower_bound_mwh=_finite(
                    payload, "strict_global_lower_bound_mwh", label=filename
                ),
                strict_global_upper_bound_mwh=_finite(
                    payload, "strict_global_upper_bound_mwh", label=filename
                ),
                global_upper_bound_improvement_mwh=_finite(
                    payload, "global_upper_bound_improvement_mwh", label=filename
                ),
                global_upper_bound_improvement_fraction=_finite(
                    payload, "global_upper_bound_improvement_fraction", label=filename
                ),
                global_upper_bound_improved=improved,
                exact_global_maximum=exact,
                witness_reference_excess_mwh=_finite(
                    payload, "witness_reference_excess_mwh", label=filename
                ),
                witness_clamped_to_reference=bool(
                    payload["witness_clamped_to_reference"]
                ),
                dual_reference_deficit_mwh=float(dual_deficit),
                dual_clamped_to_reference_lower=bool(
                    payload["dual_clamped_to_reference_lower"]
                ),
                maximum_positive_normalized_constraint_residual=_finite(
                    payload,
                    "maximum_positive_normalized_constraint_residual",
                    label=filename,
                ),
                auxiliary_objective_mismatch_mwh=_finite(
                    payload, "auxiliary_objective_mismatch_mwh", label=filename
                ),
                known_witness_within_bounds=bool(
                    payload["known_witness_within_bounds"]
                ),
                feasible_set_changed_for_integer_solutions=bool(
                    audit["feasible_set_changed_for_integer_solutions"]
                ),
                primary_integer_patterns_reopened=bool(
                    audit["primary_integer_patterns_reopened"]
                ),
                sign_binaries_reopened=bool(audit["sign_binaries_reopened"]),
                global_dual_is_valid_l1_upper_bound=bool(
                    payload["global_dual_is_valid_l1_upper_bound"]
                ),
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


def write_bundle(probe_dir: str | Path, output_dir: str | Path) -> D30BundleExport:
    source = Path(probe_dir)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    screens = _load_screens(source)
    probes = _load_probes(source, screens)
    records = _records(probes)
    csv_path = destination / "e0d30_physics_service_bound_certificate.csv"
    fieldnames = tuple(asdict(records[0]))
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow(
                {key: _csv_value(value) for key, value in asdict(record).items()}
            )

    execution_path = destination / "execution.json"
    execution_payload = {
        "canonical": False,
        "windows": {
            payload["window_id"]: {
                "global_runtime_seconds": payload["runtime_seconds"],
                "time_limit_seconds": payload["time_limit_seconds"],
                "threads": payload["threads"],
            }
            for payload in probes.values()
        },
        "screen_runtime_seconds": {
            payload["window_id"]: {
                "comparator_minimum": payload["comparator_raw"]["minimum_runtime_seconds"],
                "comparator_maximum": payload["comparator_raw"]["maximum_runtime_seconds"],
                "candidate_minimum": payload["candidate_raw"]["minimum_runtime_seconds"],
                "candidate_maximum": payload["candidate_raw"]["maximum_runtime_seconds"],
            }
            for payload in screens.values()
        },
    }
    execution_path.write_text(
        json.dumps(execution_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    source_dir = Path(__file__).resolve().parent
    manifest_path = destination / "manifest.json"
    manifest = {
        "schema": D30_BUNDLE_SCHEMA,
        "scientific_scope": "physics_service_global_l1_bound_tightening_not_settlement_or_tac",
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
        "probes": {
            filename: _sha256(source / filename) for filename in EXPECTED_PROBES
        },
        "screens": {
            filename: _sha256(source / filename) for filename in EXPECTED_SCREENS
        },
        "source_locks": {
            "formal_heat_sha256": FORMAL_HEAT_SHA256,
            "legacy_vre_sha256": LEGACY_VRE_SHA256,
            "d19_csv_sha256": E0D19_CSV_SHA256,
            "d19_manifest_sha256": E0D19_MANIFEST_SHA256,
            "d22_trace_sha256": E0D22_TRACE_SHA256,
            "d22_exposure_sha256": E0D22_EXPOSURE_SHA256,
            "d22_manifest_sha256": E0D22_MANIFEST_SHA256,
            "d29_csv_sha256": D29_CSV_SHA256,
            "d29_manifest_sha256": D29_MANIFEST_SHA256,
        },
        "sources": {
            "d30_physics_service_bound_tightening.py": _sha256(
                source_dir / "d30_physics_service_bound_tightening.py"
            ),
            "d30_certification_bundle.py": _sha256(Path(__file__)),
        },
        "cut_contract": {
            "per_period_cuts": 6,
            "feasible_set_changed_for_integer_solutions": False,
            "primary_integer_patterns_reopened": True,
            "sign_binaries_reopened": True,
        },
        "scientific_boundary": {
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
    return D30BundleExport(csv_path, manifest_path, execution_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the E0-D-30 certificate bundle.")
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
