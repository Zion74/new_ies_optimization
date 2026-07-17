"""Deterministic exporter for the eight E0-D-26 numerical probes."""

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
    D26_PROBE_SCHEMA,
    KNOWN_WITNESS_TOLERANCE_MWH,
    STRICT_FEASIBILITY_TOLERANCE,
)
from tes_bess_boundary.e0d17_exploration import (
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
)


D26_BUNDLE_SCHEMA = "tes_bess_boundary.e0d26_numerical_certification.v1"
CANONICAL_FLOAT_DECIMALS = 9
EXPECTED_PROBES = {
    "24h_selected_min.json": (24, "d19_selected_face", "minimum"),
    "24h_selected_max.json": (24, "d19_selected_face", "maximum"),
    "24h_reopened_min.json": (24, "reopened", "minimum"),
    "24h_reopened_max.json": (24, "reopened", "maximum"),
    "336h_selected_min.json": (336, "d19_selected_face", "minimum"),
    "336h_selected_max.json": (336, "d19_selected_face", "maximum"),
    "336h_reopened_min.json": (336, "reopened", "minimum"),
    "336h_reopened_max.json": (336, "reopened", "maximum"),
}


@dataclass(frozen=True)
class D26WindowRecord:
    window_id: str
    hours: int
    selected_face_minimum_primal_mwh: float
    selected_face_minimum_dual_mwh: float | None
    selected_face_minimum_bound_complete: bool
    selected_face_maximum_primal_mwh: float
    selected_face_maximum_dual_mwh: float | None
    selected_face_maximum_bound_complete: bool
    reopened_minimum_primal_mwh: float
    reopened_minimum_dual_mwh: float
    reopened_minimum_relative_gap: float
    reopened_minimum_termination: str
    reopened_maximum_primal_mwh: float
    reopened_maximum_dual_mwh: float
    reopened_maximum_relative_gap: float
    reopened_maximum_termination: str
    exact_reopened_envelope: bool
    maximum_positive_normalized_constraint_residual: float
    maximum_auxiliary_objective_mismatch_mwh: float
    actual_price_path_assigned: bool
    formal_tac: bool
    e1_ready: bool
    scientific_status: str


@dataclass(frozen=True)
class D26BundleExport:
    csv_path: Path
    manifest_path: Path
    execution_path: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_number(payload: dict[str, object], key: str) -> float:
    try:
        number = float(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"D26 probe has no finite {key}") from exc
    if not math.isfinite(number):
        raise ValueError(f"D26 probe has no finite {key}")
    return number


def _load_probes(probe_dir: str | Path) -> dict[tuple[int, str, str], dict[str, object]]:
    source = Path(probe_dir)
    probes: dict[tuple[int, str, str], dict[str, object]] = {}
    for name, expected_key in EXPECTED_PROBES.items():
        path = source / name
        if not path.is_file():
            raise ValueError(f"D26 bundle is missing {name}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        actual_key = (
            int(payload.get("hours", 0)),
            str(payload.get("scope", "")),
            str(payload.get("direction", "")),
        )
        if payload.get("schema") != D26_PROBE_SCHEMA or actual_key != expected_key:
            raise ValueError(f"D26 probe identity mismatch: {name}")
        if payload.get("normalized_admissibility_constraints") is not True:
            raise ValueError(f"D26 probe is not normalized: {name}")
        if _finite_number(payload, "strict_feasibility_tolerance") != (
            STRICT_FEASIBILITY_TOLERANCE
        ):
            raise ValueError(f"D26 probe has the wrong strict tolerance: {name}")
        if any(
            payload.get(key) is not False
            for key in (
                "actual_price_path_assigned",
                "formal_tac",
                "e1_ready",
            )
        ):
            raise ValueError(f"D26 probe crosses its scientific boundary: {name}")
        if (
            _finite_number(
                payload, "maximum_positive_normalized_constraint_residual"
            )
            > STRICT_FEASIBILITY_TOLERANCE
        ):
            raise ValueError(f"D26 probe violates its strict tolerance: {name}")
        if abs(_finite_number(payload, "auxiliary_objective_mismatch_mwh")) > 1e-6:
            raise ValueError(f"D26 probe failed PCC L1 recomputation: {name}")
        dual_raw = payload.get("dual_bound_mwh")
        dual_is_finite = dual_raw is not None and math.isfinite(float(dual_raw))
        if (payload.get("bound_certificate_complete") is True) != dual_is_finite:
            raise ValueError(f"D26 probe has an inconsistent dual flag: {name}")
        fixed_number = _finite_number(payload, "fixed_primary_integer_count")
        fixed_count = int(fixed_number)
        if fixed_number != fixed_count:
            raise ValueError(f"D26 probe has a noninteger fixed count: {name}")
        if expected_key[1] == "d19_selected_face":
            valid_integer_scope = (
                fixed_count > 0
                and payload.get("fixed_primary_integrality_removed") is True
            )
        else:
            valid_integer_scope = (
                fixed_count == 0
                and payload.get("fixed_primary_integrality_removed") is False
            )
        if not valid_integer_scope:
            raise ValueError(f"D26 probe has the wrong integer scope: {name}")
        probes[actual_key] = payload
    return probes


def _validate_conditional_witnesses(
    probes: dict[tuple[int, str, str], dict[str, object]],
) -> None:
    for hours in (24, 336):
        for direction in ("minimum", "maximum"):
            selected = probes[(hours, "d19_selected_face", direction)]
            reopened = probes[(hours, "reopened", direction)]
            witness = _finite_number(reopened, "conditional_face_warm_start_mwh")
            selected_primal = _finite_number(selected, "primal_bound_mwh")
            if not math.isclose(
                witness,
                selected_primal,
                rel_tol=0.0,
                abs_tol=KNOWN_WITNESS_TOLERANCE_MWH,
            ):
                raise ValueError("D26 reopened solve lost its selected-face witness")
            reopened_primal = _finite_number(reopened, "primal_bound_mwh")
            if direction == "minimum":
                valid = reopened_primal <= witness + KNOWN_WITNESS_TOLERANCE_MWH
            else:
                valid = reopened_primal >= witness - KNOWN_WITNESS_TOLERANCE_MWH
            if not valid:
                raise ValueError("D26 reopened incumbent is worse than its witness")


def _records(
    probes: dict[tuple[int, str, str], dict[str, object]],
) -> tuple[D26WindowRecord, ...]:
    records: list[D26WindowRecord] = []
    for hours in (24, 336):
        selected_min = probes[(hours, "d19_selected_face", "minimum")]
        selected_max = probes[(hours, "d19_selected_face", "maximum")]
        reopened_min = probes[(hours, "reopened", "minimum")]
        reopened_max = probes[(hours, "reopened", "maximum")]
        exact = all(
            payload.get("bound_certificate_complete") is True
            and payload.get("termination") == "optimal"
            and _finite_number(payload, "relative_gap") <= 1e-9
            for payload in (reopened_min, reopened_max)
        )
        residual = max(
            _finite_number(
                payload, "maximum_positive_normalized_constraint_residual"
            )
            for payload in (
                selected_min,
                selected_max,
                reopened_min,
                reopened_max,
            )
        )
        mismatch = max(
            abs(_finite_number(payload, "auxiliary_objective_mismatch_mwh"))
            for payload in (
                selected_min,
                selected_max,
                reopened_min,
                reopened_max,
            )
        )
        records.append(
            D26WindowRecord(
                window_id=str(reopened_min["window_id"]),
                hours=hours,
                selected_face_minimum_primal_mwh=_finite_number(
                    selected_min, "primal_bound_mwh"
                ),
                selected_face_minimum_dual_mwh=selected_min.get("dual_bound_mwh"),
                selected_face_minimum_bound_complete=bool(
                    selected_min["bound_certificate_complete"]
                ),
                selected_face_maximum_primal_mwh=_finite_number(
                    selected_max, "primal_bound_mwh"
                ),
                selected_face_maximum_dual_mwh=selected_max.get("dual_bound_mwh"),
                selected_face_maximum_bound_complete=bool(
                    selected_max["bound_certificate_complete"]
                ),
                reopened_minimum_primal_mwh=_finite_number(
                    reopened_min, "primal_bound_mwh"
                ),
                reopened_minimum_dual_mwh=_finite_number(
                    reopened_min, "dual_bound_mwh"
                ),
                reopened_minimum_relative_gap=_finite_number(
                    reopened_min, "relative_gap"
                ),
                reopened_minimum_termination=str(reopened_min["termination"]),
                reopened_maximum_primal_mwh=_finite_number(
                    reopened_max, "primal_bound_mwh"
                ),
                reopened_maximum_dual_mwh=_finite_number(
                    reopened_max, "dual_bound_mwh"
                ),
                reopened_maximum_relative_gap=_finite_number(
                    reopened_max, "relative_gap"
                ),
                reopened_maximum_termination=str(reopened_max["termination"]),
                exact_reopened_envelope=exact,
                maximum_positive_normalized_constraint_residual=residual,
                maximum_auxiliary_objective_mismatch_mwh=mismatch,
                actual_price_path_assigned=False,
                formal_tac=False,
                e1_ready=False,
                scientific_status=(
                    "exact_strict_numerical_envelope_not_formal_tac"
                    if exact
                    else "bounded_strict_numerical_envelope_not_formal_tac"
                ),
            )
        )
    return tuple(records)


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
) -> D26BundleExport:
    probes = _load_probes(probe_dir)
    _validate_conditional_witnesses(probes)
    records = _records(probes)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    csv_path = destination / "e0d26_numerical_certification.csv"
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
    execution = {
        name: json.loads((Path(probe_dir) / name).read_text(encoding="utf-8"))
        for name in EXPECTED_PROBES
    }
    execution_path.write_text(
        json.dumps(execution, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    source_dir = Path(__file__).resolve().parent
    manifest = {
        "schema": D26_BUNDLE_SCHEMA,
        "scientific_scope": "strict_numerical_certificate_not_price_not_tac_not_e1",
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
            "normalized_admissibility_constraints": True,
            "conditional_face_witness_required_for_reopened_scope": True,
            "bound_certificate_separate_from_termination_label": True,
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
            "d26_numerical_certification.py": _sha256(
                source_dir / "d26_numerical_certification.py"
            ),
            "d26_certification_bundle.py": _sha256(Path(__file__)),
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
    return D26BundleExport(csv_path, manifest_path, execution_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the E0-D-26 probe bundle.")
    parser.add_argument("--probe-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    exported = write_bundle(args.probe_dir, args.output_dir)
    print(json.dumps({key: str(value) for key, value in asdict(exported).items()}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
