"""Deterministic certificate bundle for the E0-D-32 negative screen."""

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
from tes_bess_boundary.d32_joint_block_envelope import (
    D32_BLOCK_HOURS,
    D32_BOUND_SAFETY_MARGIN_MWH,
    D32_MATERIALITY_THRESHOLD_FRACTION,
    D32_PROBE_SCHEMA,
    D32_SCREEN_SCHEMA,
)
from tes_bess_boundary.e0d17_exploration import (
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
)


D32_BUNDLE_SCHEMA = "tes_bess_boundary.e0d32_joint_block_envelope_screening.v1"
CANONICAL_FLOAT_DECIMALS = 9
EXPECTED_SCREENS = {
    "screen_24h.json": ("winter_day_20240101", 24, 1),
    "screen_336h.json": ("winter_fortnight_20240101", 336, 14),
}
EXPECTED_EQUIVALENCE_PROBE = "24h.json"


@dataclass(frozen=True)
class D32ScreeningRecord:
    window_id: str
    hours: int
    block_hours: int
    block_count: int
    finite_block_dual_count: int
    optimal_block_count: int
    time_limited_block_count: int
    all_known_witness_blocks_within_bounds: bool
    summed_protected_block_upper_bound_mwh: float
    reference_d30_lower_bound_mwh: float
    reference_d30_upper_bound_mwh: float
    retained_strict_global_lower_bound_mwh: float
    retained_strict_global_upper_bound_mwh: float
    upper_bound_improvement_fraction: float
    materiality_threshold_fraction: float
    materiality_gate_passed: bool
    global_probe_launched: bool
    exact_24h_equivalence_gate_passed: bool
    feasible_set_changed_for_integer_solutions: bool
    global_dual_is_valid_l1_upper_bound: bool
    actual_price_path_assigned: bool
    formal_tac: bool
    e1_ready: bool
    scientific_status: str


@dataclass(frozen=True)
class D32BundleExport:
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
    d30_locks: tuple[str, str] | None = None
    for filename, (window_id, hours, block_count) in EXPECTED_SCREENS.items():
        path = source / filename
        if not path.is_file():
            raise ValueError(f"D32 bundle is missing {filename}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload.get("schema") != D32_SCREEN_SCHEMA
            or payload.get("window_id") != window_id
            or int(payload.get("hours", 0)) != hours
            or int(payload.get("block_hours", 0)) != D32_BLOCK_HOURS
            or int(payload.get("block_count", 0)) != block_count
        ):
            raise ValueError(f"D32 screen identity mismatch: {filename}")
        if any(
            payload.get(key) is not False
            for key in (
                "feasible_set_changed_for_integer_solutions",
                "actual_price_path_assigned",
                "formal_tac",
                "e1_ready",
            )
        ):
            raise ValueError(f"D32 screen crosses its scientific boundary: {filename}")
        if (
            payload.get("all_block_duals_finite") is not True
            or payload.get("all_known_witness_blocks_within_bounds") is not True
            or payload.get("intertemporal_constraints_retained") is not True
            or payload.get("annual_service_and_admissibility_retained") is not True
            or payload.get("primary_integer_domains_relaxed") is not True
            or payload.get("block_sign_binaries_retained") is not True
        ):
            raise ValueError(f"D32 screen certificate is incomplete: {filename}")
        if not math.isclose(
            _finite(
                payload,
                "materiality_threshold_fraction",
                label=filename,
            ),
            D32_MATERIALITY_THRESHOLD_FRACTION,
            rel_tol=0.0,
            abs_tol=0.0,
        ):
            raise ValueError(f"D32 materiality threshold mismatch: {filename}")
        blocks = payload.get("block_results")
        if not isinstance(blocks, list) or len(blocks) != block_count:
            raise ValueError(f"D32 block list is incomplete: {filename}")
        expected_start = 0
        protected_sum = 0.0
        for index, block in enumerate(blocks):
            if not isinstance(block, dict):
                raise ValueError(f"D32 block is malformed: {filename}")
            start = int(block.get("start_period", -1))
            stop = int(block.get("stop_period", -1))
            protected = _finite(
                block,
                "protected_dual_bound_mwh",
                label=f"{filename} block {index}",
            )
            dual = _finite(
                block,
                "dual_bound_mwh",
                label=f"{filename} block {index}",
            )
            if (
                int(block.get("block_index", -1)) != index
                or start != expected_start
                or stop - start != D32_BLOCK_HOURS
                or int(block.get("active_sign_binary_count", 0)) != D32_BLOCK_HOURS
                or block.get("bound_certificate_complete") is not True
                or block.get("known_witness_within_bound") is not True
                or not math.isclose(
                    protected,
                    dual + D32_BOUND_SAFETY_MARGIN_MWH,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            ):
                raise ValueError(f"D32 block audit failed: {filename} block {index}")
            expected_start = stop
            protected_sum += protected
        if expected_start != hours:
            raise ValueError(f"D32 blocks do not partition {filename}")
        if not math.isclose(
            protected_sum,
            _finite(
                payload,
                "summed_protected_block_upper_bound_mwh",
                label=filename,
            ),
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError(f"D32 block sum mismatch: {filename}")
        locks = (
            str(payload.get("reference_d30_csv_sha256")),
            str(payload.get("reference_d30_manifest_sha256")),
        )
        if d30_locks is None:
            d30_locks = locks
        elif locks != d30_locks:
            raise ValueError("D32 screens disagree on the D30 source identity")
        screens[filename] = payload
    return screens


def _load_equivalence_probe(
    source: Path,
    screen: dict[str, object],
) -> dict[str, object]:
    path = source / EXPECTED_EQUIVALENCE_PROBE
    if not path.is_file():
        raise ValueError("D32 bundle is missing the 24 h equivalence probe")
    if (source / "336h.json").exists():
        raise ValueError("D32 negative screen must not contain a 336 h global probe")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema") != D32_PROBE_SCHEMA
        or payload.get("window_id") != "winter_day_20240101"
        or int(payload.get("hours", 0)) != 24
        or int(payload.get("block_cut_count", 0)) != 1
        or payload.get("d32_screen_sha256") != _sha256(source / "screen_24h.json")
    ):
        raise ValueError("D32 24 h probe identity mismatch")
    for key in (
        "reference_d30_csv_sha256",
        "reference_d30_manifest_sha256",
        "reference_d31_screen_sha256",
    ):
        if payload.get(key) != screen.get(key):
            raise ValueError(f"D32 24 h source lock mismatch: {key}")
    if (
        payload.get("exact_global_maximum") is not True
        or payload.get("witness_dominance_passed") is not True
        or payload.get("all_known_witness_blocks_within_bounds") is not True
        or payload.get("global_dual_is_valid_l1_upper_bound") is not True
        or payload.get("primary_integer_patterns_reopened") is not True
        or payload.get("sign_binaries_reopened") is not True
        or payload.get("feasible_set_changed_for_integer_solutions") is not False
    ):
        raise ValueError("D32 24 h equivalence gate failed")
    if any(
        payload.get(key) is not False
        for key in ("actual_price_path_assigned", "formal_tac", "e1_ready")
    ):
        raise ValueError("D32 24 h probe crosses its scientific boundary")
    if _finite(
        payload,
        "maximum_positive_normalized_constraint_residual",
        label="24h.json",
    ) > STRICT_FEASIBILITY_TOLERANCE:
        raise ValueError("D32 24 h strict feasibility failed")
    if abs(
        _finite(
            payload,
            "auxiliary_objective_mismatch_mwh",
            label="24h.json",
        )
    ) > D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH:
        raise ValueError("D32 24 h objective recomputation failed")
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
        raise ValueError("D32 24 h probe does not preserve the D30 interval")
    return payload


def _records(
    screens: dict[str, dict[str, object]],
    probe: dict[str, object],
) -> tuple[D32ScreeningRecord, ...]:
    records: list[D32ScreeningRecord] = []
    for filename, payload in screens.items():
        hours = int(payload["hours"])
        blocks = payload["block_results"]
        assert isinstance(blocks, list)
        terminations = [str(block["termination"]) for block in blocks]
        gate = payload.get("materiality_gate_passed") is True
        if hours == 336 and gate:
            raise ValueError("D32 336 h screen unexpectedly passes the negative gate")
        reference_upper = _finite(
            payload, "reference_d30_upper_bound_mwh", label=filename
        )
        retained_upper = _finite(
            payload, "strict_partition_upper_bound_mwh", label=filename
        )
        if hours == 336 and not math.isclose(
            retained_upper, reference_upper, rel_tol=0.0, abs_tol=1e-6
        ):
            raise ValueError("D32 336 h negative screen must retain D30")
        exact_gate = hours == 24 and probe.get("exact_global_maximum") is True
        records.append(
            D32ScreeningRecord(
                window_id=str(payload["window_id"]),
                hours=hours,
                block_hours=int(payload["block_hours"]),
                block_count=len(blocks),
                finite_block_dual_count=sum(
                    1 for block in blocks if block["bound_certificate_complete"] is True
                ),
                optimal_block_count=terminations.count("optimal"),
                time_limited_block_count=terminations.count("maxtimelimit"),
                all_known_witness_blocks_within_bounds=True,
                summed_protected_block_upper_bound_mwh=_finite(
                    payload,
                    "summed_protected_block_upper_bound_mwh",
                    label=filename,
                ),
                reference_d30_lower_bound_mwh=_finite(
                    payload, "reference_d30_lower_bound_mwh", label=filename
                ),
                reference_d30_upper_bound_mwh=reference_upper,
                retained_strict_global_lower_bound_mwh=_finite(
                    payload, "strict_partition_lower_bound_mwh", label=filename
                ),
                retained_strict_global_upper_bound_mwh=retained_upper,
                upper_bound_improvement_fraction=_finite(
                    payload, "upper_bound_improvement_fraction", label=filename
                ),
                materiality_threshold_fraction=D32_MATERIALITY_THRESHOLD_FRACTION,
                materiality_gate_passed=gate,
                global_probe_launched=hours == 24,
                exact_24h_equivalence_gate_passed=exact_gate,
                feasible_set_changed_for_integer_solutions=False,
                global_dual_is_valid_l1_upper_bound=(
                    probe.get("global_dual_is_valid_l1_upper_bound") is True
                    if hours == 24
                    else True
                ),
                actual_price_path_assigned=False,
                formal_tac=False,
                e1_ready=False,
                scientific_status=(
                    "exact_24h_equivalence_retained"
                    if hours == 24
                    else "negative_screen_retains_d30_no_336h_global_probe"
                ),
            )
        )
    return tuple(records)


def _canonical(value: object) -> object:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:.{CANONICAL_FLOAT_DECIMALS}f}"
    return value


def write_d32_bundle(
    source_dir: str | Path,
    output_dir: str | Path,
) -> D32BundleExport:
    source = Path(source_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    screens = _load_screens(source)
    probe = _load_equivalence_probe(source, screens["screen_24h.json"])
    records = _records(screens, probe)
    csv_path = output / "e0d32_joint_block_envelope_screening.csv"
    fieldnames = tuple(asdict(records[0]).keys())
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({key: _canonical(value) for key, value in asdict(record).items()})
    execution_path = output / "execution.json"
    execution = {
        "schema": "tes_bess_boundary.e0d32_joint_block_envelope_execution.v1",
        "canonical": False,
        "screens": {
            filename: {
                "workers": payload["workers"],
                "per_block_time_limit_seconds": payload[
                    "per_block_time_limit_seconds"
                ],
                "block_runtime_seconds": [
                    block["runtime_seconds"] for block in payload["block_results"]
                ],
                "block_termination": [
                    block["termination"] for block in payload["block_results"]
                ],
            }
            for filename, payload in screens.items()
        },
        "equivalence_probe": {
            "runtime_seconds": probe["runtime_seconds"],
            "threads": probe["threads"],
            "time_limit_seconds": probe["time_limit_seconds"],
            "termination": probe["termination"],
        },
    }
    execution_path.write_text(
        json.dumps(execution, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    manifest_path = output / "manifest.json"
    manifest = {
        "schema": D32_BUNDLE_SCHEMA,
        "canonical": True,
        "method_contract": {
            "block_hours": D32_BLOCK_HOURS,
            "block_bound_safety_margin_mwh": D32_BOUND_SAFETY_MARGIN_MWH,
            "materiality_threshold_fraction": D32_MATERIALITY_THRESHOLD_FRACTION,
            "primary_integer_domains_relaxed_in_block_screens": True,
            "block_sign_binaries_retained": True,
            "full_intertemporal_paths_retained": True,
            "sum_of_block_duals_is_valid_global_l1_upper_bound": True,
            "global_probe_336h_launched": False,
        },
        "locked_inputs": {
            "formal_heat_sha256": FORMAL_HEAT_SHA256,
            "legacy_vre_sha256": LEGACY_VRE_SHA256,
            "d19_csv_sha256": E0D19_CSV_SHA256,
            "d19_manifest_sha256": E0D19_MANIFEST_SHA256,
            "d22_trace_sha256": E0D22_TRACE_SHA256,
            "d22_exposure_sha256": E0D22_EXPOSURE_SHA256,
            "d22_manifest_sha256": E0D22_MANIFEST_SHA256,
            "d30_csv_sha256": screens["screen_24h.json"][
                "reference_d30_csv_sha256"
            ],
            "d30_manifest_sha256": screens["screen_24h.json"][
                "reference_d30_manifest_sha256"
            ],
            "d31_screen_24h_sha256": screens["screen_24h.json"][
                "reference_d31_screen_sha256"
            ],
            "d31_screen_336h_sha256": screens["screen_336h.json"][
                "reference_d31_screen_sha256"
            ],
        },
        "raw_inputs": {
            filename: {"sha256": _sha256(source / filename)}
            for filename in (*EXPECTED_SCREENS.keys(), EXPECTED_EQUIVALENCE_PROBE)
        },
        "output": {
            "csv": csv_path.name,
            "csv_sha256": _sha256(csv_path),
            "row_count": len(records),
        },
        "noncanonical_execution": {
            "path": execution_path.name,
            "sha256": _sha256(execution_path),
        },
        "scientific_boundaries": {
            "actual_price_path_assigned": False,
            "formal_tac": False,
            "e1_ready": False,
            "latest_336h_strict_interval_source": "E0-D-30",
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return D32BundleExport(csv_path, manifest_path, execution_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    export = write_d32_bundle(args.source_dir, args.output_dir)
    print(
        json.dumps(
            {
                "csv": str(export.csv_path),
                "manifest": str(export.manifest_path),
                "execution": str(export.execution_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
