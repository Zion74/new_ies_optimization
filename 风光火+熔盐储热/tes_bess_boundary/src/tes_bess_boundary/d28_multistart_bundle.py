"""Deterministic exporter for the two E0-D-28 336 h sign-seed probes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
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
from tes_bess_boundary.d28_multistart_direction import D28_MULTISTART_SCHEMA
from tes_bess_boundary.e0d17_exploration import (
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
)


D28_BUNDLE_SCHEMA = "tes_bess_boundary.e0d28_multistart_screening.v1"
CANONICAL_FLOAT_DECIMALS = 9
EXPECTED_PROBES = {
    "336h_negated.json": "negated",
    "336h_alternating.json": "alternating",
}


@dataclass(frozen=True)
class D28SeedRecord:
    window_id: str
    hours: int
    seed_strategy: str
    shift_periods: int
    seed_positive_sign_count: int
    selected_face_l1_mwh: float
    initial_seed_support_witness_mwh: float
    support_primal_mwh: float
    support_dual_mwh: float
    support_relative_gap: float
    support_termination: str
    feasible_l1_redistribution_mwh: float
    best_feasible_l1_redistribution_mwh: float
    improvement_over_selected_face_mwh: float
    sign_change_count: int
    fixed_point_reached: bool
    maximum_positive_normalized_constraint_residual: float
    l1_minus_support_mwh: float
    support_dual_is_global_l1_upper_bound: bool
    global_l1_bound_generated: bool
    actual_price_path_assigned: bool
    formal_tac: bool
    e1_ready: bool
    scientific_status: str


@dataclass(frozen=True)
class D28BundleExport:
    csv_path: Path
    manifest_path: Path
    execution_path: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_number(payload: dict[str, object], key: str, *, label: str) -> float:
    try:
        number = float(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} has no finite {key}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} has no finite {key}")
    return number


def _load_probes(probe_dir: str | Path) -> dict[str, dict[str, object]]:
    source = Path(probe_dir)
    probes: dict[str, dict[str, object]] = {}
    base_pattern: str | None = None
    selected_face: float | None = None
    for name, strategy in EXPECTED_PROBES.items():
        path = source / name
        if not path.is_file():
            raise ValueError(f"D28 bundle is missing {name}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != D28_MULTISTART_SCHEMA:
            raise ValueError(f"D28 probe schema mismatch: {name}")
        if int(payload.get("hours", 0)) != 336:
            raise ValueError(f"D28 probe horizon mismatch: {name}")
        if payload.get("seed_strategy") != strategy:
            raise ValueError(f"D28 probe strategy mismatch: {name}")
        if (
            payload.get("requested_iterations") != 1
            or payload.get("completed_iterations") != 1
        ):
            raise ValueError(f"D28 probe is not the preregistered screen: {name}")
        if (
            payload.get("support_dual_is_global_l1_upper_bound") is not False
            or payload.get("global_l1_bound_generated") is not False
        ):
            raise ValueError(f"D28 probe crosses the global-bound boundary: {name}")
        if any(
            payload.get(key) is not False
            for key in ("actual_price_path_assigned", "formal_tac", "e1_ready")
        ):
            raise ValueError(f"D28 probe crosses its scientific boundary: {name}")
        iterations = payload.get("iterations")
        if not isinstance(iterations, list) or len(iterations) != 1:
            raise ValueError(f"D28 probe has invalid iterations: {name}")
        record = iterations[0]
        residual = _finite_number(
            record,
            "maximum_positive_normalized_constraint_residual",
            label=name,
        )
        if residual > STRICT_FEASIBILITY_TOLERANCE:
            raise ValueError(f"D28 probe violates strict feasibility: {name}")
        support_primal = _finite_number(
            record, "support_primal_mwh", label=name
        )
        feasible_l1 = _finite_number(
            record, "feasible_l1_redistribution_mwh", label=name
        )
        if feasible_l1 + KNOWN_WITNESS_TOLERANCE_MWH < support_primal:
            raise ValueError(f"D28 support exceeds feasible L1: {name}")
        selected = _finite_number(payload, "selected_face_l1_mwh", label=name)
        best = _finite_number(
            payload, "best_feasible_l1_redistribution_mwh", label=name
        )
        expected_best = max(selected, feasible_l1)
        if not math.isclose(
            best,
            expected_best,
            rel_tol=0.0,
            abs_tol=KNOWN_WITNESS_TOLERANCE_MWH,
        ):
            raise ValueError(f"D28 best witness is inconsistent: {name}")
        improvement = _finite_number(
            payload, "improvement_over_selected_face_mwh", label=name
        )
        if not math.isclose(
            improvement,
            best - selected,
            rel_tol=0.0,
            abs_tol=KNOWN_WITNESS_TOLERANCE_MWH,
        ):
            raise ValueError(f"D28 improvement is inconsistent: {name}")
        pattern = str(payload.get("base_sign_pattern", ""))
        if base_pattern is None:
            base_pattern = pattern
            selected_face = selected
        elif pattern != base_pattern or not math.isclose(
            selected,
            float(selected_face),
            rel_tol=0.0,
            abs_tol=KNOWN_WITNESS_TOLERANCE_MWH,
        ):
            raise ValueError("D28 probes do not share one selected-face baseline")
        if payload.get("seed_sign_pattern") == pattern:
            raise ValueError(f"D28 seed did not leave the base pattern: {name}")
        _finite_number(record, "support_dual_mwh", label=name)
        _finite_number(record, "support_relative_gap", label=name)
        probes[name] = payload
    return probes


def _records(probes: dict[str, dict[str, object]]) -> tuple[D28SeedRecord, ...]:
    output: list[D28SeedRecord] = []
    for name in EXPECTED_PROBES:
        payload = probes[name]
        record = payload["iterations"][0]
        improvement = _finite_number(
            payload, "improvement_over_selected_face_mwh", label=name
        )
        output.append(
            D28SeedRecord(
                window_id=str(payload["window_id"]),
                hours=int(payload["hours"]),
                seed_strategy=str(payload["seed_strategy"]),
                shift_periods=int(payload["shift_periods"]),
                seed_positive_sign_count=int(payload["seed_positive_sign_count"]),
                selected_face_l1_mwh=_finite_number(
                    payload, "selected_face_l1_mwh", label=name
                ),
                initial_seed_support_witness_mwh=_finite_number(
                    payload, "initial_seed_support_witness_mwh", label=name
                ),
                support_primal_mwh=_finite_number(
                    record, "support_primal_mwh", label=name
                ),
                support_dual_mwh=_finite_number(
                    record, "support_dual_mwh", label=name
                ),
                support_relative_gap=_finite_number(
                    record, "support_relative_gap", label=name
                ),
                support_termination=str(record["termination"]),
                feasible_l1_redistribution_mwh=_finite_number(
                    record, "feasible_l1_redistribution_mwh", label=name
                ),
                best_feasible_l1_redistribution_mwh=_finite_number(
                    payload, "best_feasible_l1_redistribution_mwh", label=name
                ),
                improvement_over_selected_face_mwh=improvement,
                sign_change_count=int(record["sign_change_count"]),
                fixed_point_reached=bool(payload["fixed_point_reached"]),
                maximum_positive_normalized_constraint_residual=_finite_number(
                    record,
                    "maximum_positive_normalized_constraint_residual",
                    label=name,
                ),
                l1_minus_support_mwh=_finite_number(
                    record, "l1_minus_support_mwh", label=name
                ),
                support_dual_is_global_l1_upper_bound=False,
                global_l1_bound_generated=False,
                actual_price_path_assigned=False,
                formal_tac=False,
                e1_ready=False,
                scientific_status=(
                    "strict_feasible_witness_improved_not_global_bound"
                    if improvement > KNOWN_WITNESS_TOLERANCE_MWH
                    else "strict_feasible_witness_screen_no_improvement"
                ),
            )
        )
    return tuple(output)


def _csv_value(value: object) -> object:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.{CANONICAL_FLOAT_DECIMALS}f}"
    return value


def write_bundle(
    probe_dir: str | Path, output_dir: str | Path
) -> D28BundleExport:
    probes = _load_probes(probe_dir)
    records = _records(probes)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    csv_path = destination / "e0d28_multistart_screening.csv"
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
        "schema": D28_BUNDLE_SCHEMA,
        "scientific_scope": "multistart_feasible_l1_screen_not_global_bound",
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
            name: _sha256(Path(probe_dir) / name) for name in EXPECTED_PROBES
        },
        "probe_contract": {
            "preregistered_iterations_per_seed": 1,
            "strict_feasibility_tolerance": STRICT_FEASIBILITY_TOLERANCE,
            "support_dual_is_global_l1_upper_bound": False,
            "global_l1_bound_generated": False,
        },
        "source_locks": {
            "formal_heat_sha256": FORMAL_HEAT_SHA256,
            "legacy_vre_sha256": LEGACY_VRE_SHA256,
            "d19_csv_sha256": E0D19_CSV_SHA256,
            "d19_manifest_sha256": E0D19_MANIFEST_SHA256,
            "d22_trace_sha256": E0D22_TRACE_SHA256,
            "d22_exposure_sha256": E0D22_EXPOSURE_SHA256,
            "d22_manifest_sha256": E0D22_MANIFEST_SHA256,
        },
        "sources": {
            "d28_multistart_direction.py": _sha256(
                source_dir / "d28_multistart_direction.py"
            ),
            "d28_multistart_bundle.py": _sha256(Path(__file__)),
            "d27_direction_generation.py": _sha256(
                source_dir / "d27_direction_generation.py"
            ),
        },
        "scientific_boundary": {
            "support_dual_is_global_l1_upper_bound": False,
            "global_l1_bound_generated": False,
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
    return D28BundleExport(csv_path, manifest_path, execution_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the E0-D-28 seed screen.")
    parser.add_argument("--probe-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    exported = write_bundle(args.probe_dir, args.output_dir)
    print(json.dumps({key: str(value) for key, value in asdict(exported).items()}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
