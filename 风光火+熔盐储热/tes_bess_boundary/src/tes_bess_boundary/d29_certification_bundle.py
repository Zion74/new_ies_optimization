"""Deterministic exporter for the E0-D-29 bound-tightening probes."""

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
    D29_PROBE_SCHEMA,
)
from tes_bess_boundary.e0d17_exploration import (
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
)


D29_BUNDLE_SCHEMA = "tes_bess_boundary.e0d29_bound_tightening_certificate.v1"
CANONICAL_FLOAT_DECIMALS = 9
D27_CSV_SHA256 = "f3f8b0756fad1bf806aa631c7a6e72e1f83285fa5e45d0ac01307da5e37ee894"
D27_MANIFEST_SHA256 = "2f926e1f0d6b91d395538fe85eb2a3a11ae4f342783e974ef720ecd8fd96b8ab"
EXPECTED_PROBES = {
    "24h.json": ("winter_day_20240101", 24),
    "336h.json": ("winter_fortnight_20240101", 336),
}


@dataclass(frozen=True)
class D29CertificateRecord:
    window_id: str
    hours: int
    per_period_cut_count: int
    aggregate_cut_count: int
    selected_face_witness_mwh: float
    reference_d27_lower_bound_mwh: float
    reference_d27_upper_bound_mwh: float
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
    maximum_positive_normalized_constraint_residual: float
    auxiliary_objective_mismatch_mwh: float
    feasible_set_changed_for_integer_solutions: bool
    primary_integer_patterns_reopened: bool
    sign_binaries_reopened: bool
    global_dual_is_valid_l1_upper_bound: bool
    actual_price_path_assigned: bool
    formal_tac: bool
    e1_ready: bool
    scientific_status: str


@dataclass(frozen=True)
class D29BundleExport:
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


def _load_probes(probe_dir: str | Path) -> dict[str, dict[str, object]]:
    source = Path(probe_dir)
    probes: dict[str, dict[str, object]] = {}
    for filename, (window_id, hours) in EXPECTED_PROBES.items():
        path = source / filename
        if not path.is_file():
            raise ValueError(f"D29 bundle is missing {filename}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != D29_PROBE_SCHEMA:
            raise ValueError(f"D29 probe schema mismatch: {filename}")
        if payload.get("window_id") != window_id or int(payload.get("hours", 0)) != hours:
            raise ValueError(f"D29 probe identity mismatch: {filename}")
        if payload.get("reference_d27_csv_sha256") != D27_CSV_SHA256:
            raise ValueError(f"D29 D27 CSV source lock mismatch: {filename}")
        if payload.get("reference_d27_manifest_sha256") != D27_MANIFEST_SHA256:
            raise ValueError(f"D29 D27 manifest source lock mismatch: {filename}")
        if payload.get("witness_dominance_passed") is not True:
            raise ValueError(f"D29 witness dominance failed: {filename}")
        if payload.get("global_dual_is_valid_l1_upper_bound") is not True:
            raise ValueError(f"D29 global dual is incomplete: {filename}")
        if any(
            payload.get(key) is not False
            for key in ("actual_price_path_assigned", "formal_tac", "e1_ready")
        ):
            raise ValueError(f"D29 probe crosses its scientific boundary: {filename}")
        residual = _finite(
            payload,
            "maximum_positive_normalized_constraint_residual",
            label=filename,
        )
        if residual > STRICT_FEASIBILITY_TOLERANCE:
            raise ValueError(f"D29 strict feasibility failed: {filename}")
        mismatch = _finite(
            payload,
            "auxiliary_objective_mismatch_mwh",
            label=filename,
        )
        if abs(mismatch) > D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH:
            raise ValueError(f"D29 objective recomputation failed: {filename}")
        cut_audit = payload.get("cut_audit")
        if not isinstance(cut_audit, dict):
            raise ValueError(f"D29 cut audit is absent: {filename}")
        if (
            int(cut_audit.get("periods", 0)) != hours
            or int(cut_audit.get("per_period_cut_count", 0)) != 4 * hours
            or int(cut_audit.get("aggregate_cut_count", 0)) != 5
            or cut_audit.get("feasible_set_changed_for_integer_solutions") is not False
            or cut_audit.get("primary_integer_patterns_reopened") is not True
            or cut_audit.get("sign_binaries_reopened") is not True
        ):
            raise ValueError(f"D29 cut audit is inconsistent: {filename}")
        reference_lower = _finite(
            payload, "reference_d27_lower_bound_mwh", label=filename
        )
        reference_upper = _finite(
            payload, "reference_d27_upper_bound_mwh", label=filename
        )
        strict_lower = _finite(
            payload, "strict_global_lower_bound_mwh", label=filename
        )
        strict_upper = _finite(
            payload, "strict_global_upper_bound_mwh", label=filename
        )
        dual = _finite(payload, "dual_bound_mwh", label=filename)
        if strict_lower + KNOWN_WITNESS_TOLERANCE_MWH < reference_lower:
            raise ValueError(f"D29 loses the D27 lower bound: {filename}")
        if strict_upper > reference_upper + KNOWN_WITNESS_TOLERANCE_MWH:
            raise ValueError(f"D29 loses the D27 upper bound: {filename}")
        if strict_upper > dual + KNOWN_WITNESS_TOLERANCE_MWH:
            raise ValueError(f"D29 strict upper exceeds its global dual: {filename}")
        if strict_upper + KNOWN_WITNESS_TOLERANCE_MWH < strict_lower:
            raise ValueError(f"D29 strict interval is reversed: {filename}")
        probes[filename] = payload
    return probes


def _records(probes: dict[str, dict[str, object]]) -> tuple[D29CertificateRecord, ...]:
    records: list[D29CertificateRecord] = []
    for filename in EXPECTED_PROBES:
        payload = probes[filename]
        cut_audit = payload["cut_audit"]
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
        records.append(
            D29CertificateRecord(
                window_id=str(payload["window_id"]),
                hours=int(payload["hours"]),
                per_period_cut_count=int(cut_audit["per_period_cut_count"]),
                aggregate_cut_count=int(cut_audit["aggregate_cut_count"]),
                selected_face_witness_mwh=_finite(
                    payload, "selected_face_witness_mwh", label=filename
                ),
                reference_d27_lower_bound_mwh=_finite(
                    payload, "reference_d27_lower_bound_mwh", label=filename
                ),
                reference_d27_upper_bound_mwh=_finite(
                    payload, "reference_d27_upper_bound_mwh", label=filename
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
                    payload,
                    "global_upper_bound_improvement_fraction",
                    label=filename,
                ),
                global_upper_bound_improved=improved,
                exact_global_maximum=exact,
                maximum_positive_normalized_constraint_residual=_finite(
                    payload,
                    "maximum_positive_normalized_constraint_residual",
                    label=filename,
                ),
                auxiliary_objective_mismatch_mwh=_finite(
                    payload, "auxiliary_objective_mismatch_mwh", label=filename
                ),
                feasible_set_changed_for_integer_solutions=False,
                primary_integer_patterns_reopened=True,
                sign_binaries_reopened=True,
                global_dual_is_valid_l1_upper_bound=True,
                actual_price_path_assigned=False,
                formal_tac=False,
                e1_ready=False,
                scientific_status=status,
            )
        )
    return tuple(records)


def _csv_value(value: object) -> object:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.{CANONICAL_FLOAT_DECIMALS}f}"
    return value


def write_bundle(probe_dir: str | Path, output_dir: str | Path) -> D29BundleExport:
    probes = _load_probes(probe_dir)
    records = _records(probes)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    csv_path = destination / "e0d29_bound_tightening_certificate.csv"
    manifest_path = destination / "manifest.json"
    execution_path = destination / "execution.json"
    fields = tuple(asdict(records[0]))
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow(
                {key: _csv_value(value) for key, value in asdict(record).items()}
            )
    execution_path.write_text(
        json.dumps(probes, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    source_dir = Path(__file__).resolve().parent
    manifest = {
        "schema": D29_BUNDLE_SCHEMA,
        "scientific_scope": "global_l1_bound_tightening_not_settlement_or_tac",
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
            filename: _sha256(Path(probe_dir) / filename)
            for filename in EXPECTED_PROBES
        },
        "source_locks": {
            "formal_heat_sha256": FORMAL_HEAT_SHA256,
            "legacy_vre_sha256": LEGACY_VRE_SHA256,
            "d19_csv_sha256": E0D19_CSV_SHA256,
            "d19_manifest_sha256": E0D19_MANIFEST_SHA256,
            "d22_trace_sha256": E0D22_TRACE_SHA256,
            "d22_exposure_sha256": E0D22_EXPOSURE_SHA256,
            "d22_manifest_sha256": E0D22_MANIFEST_SHA256,
            "d27_csv_sha256": D27_CSV_SHA256,
            "d27_manifest_sha256": D27_MANIFEST_SHA256,
        },
        "sources": {
            "d29_export_linked_bound_tightening.py": _sha256(
                source_dir / "d29_export_linked_bound_tightening.py"
            ),
            "d29_certification_bundle.py": _sha256(Path(__file__)),
            "d27_direction_generation.py": _sha256(
                source_dir / "d27_direction_generation.py"
            ),
        },
        "cut_contract": {
            "per_period_cuts": 4,
            "aggregate_cuts": 5,
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
    return D29BundleExport(csv_path, manifest_path, execution_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the E0-D-29 certificate.")
    parser.add_argument("--probe-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    exported = write_bundle(args.probe_dir, args.output_dir)
    print(json.dumps({key: str(value) for key, value in asdict(exported).items()}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
