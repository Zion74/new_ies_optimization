"""Deterministic exporter for the E0-D-27 numerical certificate."""

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
from tes_bess_boundary.d27_direction_generation import D27_DIRECTION_SCHEMA
from tes_bess_boundary.e0d17_exploration import (
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
)


D27_BUNDLE_SCHEMA = "tes_bess_boundary.e0d27_numerical_certificate.v1"
CANONICAL_FLOAT_DECIMALS = 9
EXPECTED_PROBES = {
    "24h_final.json": (24, True, True),
    "336h_support_final.json": (336, True, False),
    "336h_global.json": (336, False, True),
}


@dataclass(frozen=True)
class D27MaximumRecord:
    window_id: str
    hours: int
    selected_face_witness_mwh: float
    support_primal_mwh: float
    support_dual_mwh: float
    support_relative_gap: float
    support_termination: str
    support_sign_fixed_point: bool
    support_dual_is_global_l1_upper_bound: bool
    global_primal_mwh: float
    global_dual_mwh: float
    global_relative_gap: float
    global_termination: str
    global_bound_certificate_complete: bool
    strict_global_lower_bound_mwh: float
    strict_global_upper_bound_mwh: float
    exact_global_maximum: bool
    maximum_positive_normalized_constraint_residual: float
    maximum_auxiliary_objective_mismatch_mwh: float
    actual_price_path_assigned: bool
    formal_tac: bool
    e1_ready: bool
    scientific_status: str


@dataclass(frozen=True)
class D27BundleExport:
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
    for name, (hours, require_support, require_global) in EXPECTED_PROBES.items():
        path = source / name
        if not path.is_file():
            raise ValueError(f"D27 bundle is missing {name}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != D27_DIRECTION_SCHEMA:
            raise ValueError(f"D27 probe schema mismatch: {name}")
        if int(payload.get("hours", 0)) != hours:
            raise ValueError(f"D27 probe horizon mismatch: {name}")
        if payload.get("support_dual_is_global_l1_upper_bound") is not False:
            raise ValueError(f"D27 support dual crosses the global boundary: {name}")
        if any(
            payload.get(key) is not False
            for key in ("actual_price_path_assigned", "formal_tac", "e1_ready")
        ):
            raise ValueError(f"D27 probe crosses its scientific boundary: {name}")

        iterations = payload.get("iterations")
        if not isinstance(iterations, list):
            raise ValueError(f"D27 probe has invalid iterations: {name}")
        if require_support:
            if len(iterations) < 1 or payload.get("fixed_point_reached") is not True:
                raise ValueError(f"D27 support direction is not stable: {name}")
            final_iteration = iterations[-1]
            if final_iteration.get("sign_pattern_stable") is not True:
                raise ValueError(f"D27 support direction is not stable: {name}")
            residual = _finite_number(
                final_iteration,
                "maximum_positive_normalized_constraint_residual",
                label=name,
            )
            if residual > STRICT_FEASIBILITY_TOLERANCE:
                raise ValueError(f"D27 support solve violates strict feasibility: {name}")
            mismatch = _finite_number(
                final_iteration, "l1_minus_support_mwh", label=name
            )
            if abs(mismatch) > 1e-6:
                raise ValueError(f"D27 support solve failed L1 recomputation: {name}")
        elif iterations:
            raise ValueError(f"D27 global-only probe unexpectedly ran support: {name}")

        global_result = payload.get("disaggregated_global")
        if require_global:
            if not isinstance(global_result, dict):
                raise ValueError(f"D27 probe has no global result: {name}")
            if (
                global_result.get("sign_formulation")
                != "positive_negative_disaggregation_single_binary"
                or global_result.get("dual_is_global_l1_upper_bound") is not True
                or global_result.get("primary_integer_patterns_reopened") is not True
                or global_result.get("witness_dominance_passed") is not True
            ):
                raise ValueError(f"D27 global formulation boundary mismatch: {name}")
            residual = _finite_number(
                global_result,
                "maximum_positive_normalized_constraint_residual",
                label=name,
            )
            if residual > STRICT_FEASIBILITY_TOLERANCE:
                raise ValueError(f"D27 global solve violates strict feasibility: {name}")
            mismatch = _finite_number(
                global_result, "auxiliary_objective_mismatch_mwh", label=name
            )
            if abs(mismatch) > 1e-6:
                raise ValueError(f"D27 global solve failed L1 recomputation: {name}")
            primal = _finite_number(
                global_result, "primal_bound_mwh", label=name
            )
            dual = _finite_number(global_result, "dual_bound_mwh", label=name)
            if global_result.get("bound_certificate_complete") is not True:
                raise ValueError(f"D27 global solve has no finite bound: {name}")
            if dual + KNOWN_WITNESS_TOLERANCE_MWH < primal:
                raise ValueError(f"D27 global bound is below its incumbent: {name}")
        elif global_result is not None:
            raise ValueError(f"D27 support-only probe unexpectedly ran global: {name}")
        probes[name] = payload
    return probes


def _support_fields(
    payload: dict[str, object], *, label: str
) -> tuple[dict[str, object], float]:
    iteration = payload["iterations"][-1]
    best = _finite_number(
        payload, "best_feasible_l1_redistribution_mwh", label=label
    )
    primal = _finite_number(iteration, "support_primal_mwh", label=label)
    if best + KNOWN_WITNESS_TOLERANCE_MWH < primal:
        raise ValueError(f"D27 support result lost its feasible L1 witness: {label}")
    return iteration, best


def _record(
    support_probe: dict[str, object],
    global_probe: dict[str, object],
    *,
    label: str,
) -> D27MaximumRecord:
    support, support_best = _support_fields(support_probe, label=label)
    global_result = global_probe["disaggregated_global"]
    global_primal = _finite_number(
        global_result, "primal_bound_mwh", label=label
    )
    global_dual = _finite_number(global_result, "dual_bound_mwh", label=label)
    lower = max(support_best, global_primal)
    if global_dual + KNOWN_WITNESS_TOLERANCE_MWH < lower:
        raise ValueError(f"D27 global solve does not dominate support witness: {label}")
    gap = _finite_number(global_result, "relative_gap", label=label)
    exact = (
        global_result.get("termination") == "optimal"
        and gap <= 1e-9
        and math.isclose(
            lower,
            global_dual,
            rel_tol=0.0,
            abs_tol=KNOWN_WITNESS_TOLERANCE_MWH,
        )
    )
    residual = max(
        _finite_number(
            support,
            "maximum_positive_normalized_constraint_residual",
            label=label,
        ),
        _finite_number(
            global_result,
            "maximum_positive_normalized_constraint_residual",
            label=label,
        ),
    )
    return D27MaximumRecord(
        window_id=str(support_probe["window_id"]),
        hours=int(support_probe["hours"]),
        selected_face_witness_mwh=_finite_number(
            support_probe, "selected_face_witness_mwh", label=label
        ),
        support_primal_mwh=_finite_number(
            support, "support_primal_mwh", label=label
        ),
        support_dual_mwh=_finite_number(support, "support_dual_mwh", label=label),
        support_relative_gap=_finite_number(
            support, "support_relative_gap", label=label
        ),
        support_termination=str(support["termination"]),
        support_sign_fixed_point=bool(support_probe["fixed_point_reached"]),
        support_dual_is_global_l1_upper_bound=False,
        global_primal_mwh=global_primal,
        global_dual_mwh=global_dual,
        global_relative_gap=gap,
        global_termination=str(global_result["termination"]),
        global_bound_certificate_complete=bool(
            global_result["bound_certificate_complete"]
        ),
        strict_global_lower_bound_mwh=lower,
        strict_global_upper_bound_mwh=global_dual,
        exact_global_maximum=exact,
        maximum_positive_normalized_constraint_residual=residual,
        maximum_auxiliary_objective_mismatch_mwh=abs(
            _finite_number(
                global_result, "auxiliary_objective_mismatch_mwh", label=label
            )
        ),
        actual_price_path_assigned=False,
        formal_tac=False,
        e1_ready=False,
        scientific_status=(
            "exact_strict_global_maximum_not_formal_tac"
            if exact
            else "bounded_strict_global_maximum_not_formal_tac"
        ),
    )


def _records(probes: dict[str, dict[str, object]]) -> tuple[D27MaximumRecord, ...]:
    record_24 = _record(
        probes["24h_final.json"], probes["24h_final.json"], label="24h"
    )
    record_336 = _record(
        probes["336h_support_final.json"],
        probes["336h_global.json"],
        label="336h",
    )
    return record_24, record_336


def _csv_value(value: object) -> object:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.{CANONICAL_FLOAT_DECIMALS}f}"
    if value is None:
        return ""
    return value


def write_bundle(
    probe_dir: str | Path, output_dir: str | Path
) -> D27BundleExport:
    probes = _load_probes(probe_dir)
    records = _records(probes)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    csv_path = destination / "e0d27_numerical_certificate.csv"
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
    execution = {name: probes[name] for name in EXPECTED_PROBES}
    execution_path.write_text(
        json.dumps(execution, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    source_dir = Path(__file__).resolve().parent
    manifest = {
        "schema": D27_BUNDLE_SCHEMA,
        "scientific_scope": "strict_global_l1_maximum_not_price_not_tac_not_e1",
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
            "strict_feasibility_tolerance": STRICT_FEASIBILITY_TOLERANCE,
            "support_dual_is_global_l1_upper_bound": False,
            "global_formulation": "positive_negative_disaggregation_single_binary",
            "primary_integer_patterns_reopened": True,
            "witness_dominance_required": True,
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
            "d27_direction_generation.py": _sha256(
                source_dir / "d27_direction_generation.py"
            ),
            "d27_certification_bundle.py": _sha256(Path(__file__)),
            "alternative_dispatch_envelope.py": _sha256(
                source_dir / "alternative_dispatch_envelope.py"
            ),
        },
        "scientific_boundary": {
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
    return D27BundleExport(csv_path, manifest_path, execution_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the E0-D-27 bundle.")
    parser.add_argument("--probe-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    exported = write_bundle(args.probe_dir, args.output_dir)
    print(json.dumps({key: str(value) for key, value in asdict(exported).items()}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
