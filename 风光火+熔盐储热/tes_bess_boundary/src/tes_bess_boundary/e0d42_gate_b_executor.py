"""E0-D-42 parent-enforced native HiGHS Gate B phase executor.

This module is deliberately model-agnostic.  A separate formal driver must
construct and presolve a locked full-year model exactly once, then persist the
presolved ``HighsLp`` with :func:`write_lp_archive`.  This executor runs the
frozen B1/B2 phases in clean child processes, saves native solution and basis
artifacts, independently certifies every returned row-dual vector, and lets a
Linux parent enforce the preregistered wall-clock and memory gates.

No function in this module changes a planning model or accepts a solver log as
a lower-bound certificate.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import platform
import signal
import struct
import subprocess
import sys
import time
from array import array
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Sequence

from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
from tes_bess_boundary.e0d42_native_highs_certificate import (
    SUPPORTED_HIGHS_VERSION,
    audit_highs_lp,
    certify_lagrangian_lower_bound,
    fingerprint_highs_lp,
)


LP_ARCHIVE_SCHEMA_ID = "tes_bess_boundary.e0d42_lp_archive.v1"
SOLUTION_ARCHIVE_SCHEMA_ID = "tes_bess_boundary.e0d42_solution_archive.v1"
BASIS_SCHEMA_ID = "tes_bess_boundary.e0d42_basis_checkpoint.v1"
PHASE_RESULT_SCHEMA_ID = "tes_bess_boundary.e0d42_gate_b_phase.v1"
PHASE_EXECUTION_SCHEMA_ID = f"{PHASE_RESULT_SCHEMA_ID}.execution"
LP_MANIFEST_SCHEMA_ID = "tes_bess_boundary.e0d42_gate_b_lp_manifest.v1"
LP_PLAN_EXECUTION_SCHEMA_ID = f"{LP_MANIFEST_SCHEMA_ID}.execution"
LP_ARCHIVE_MAGIC = b"D42LP01\n"
SOLUTION_ARCHIVE_MAGIC = b"D42SOL1\n"

FORMAL_THREADS = 12
FORMAL_RANDOM_SEED = 0
FORMAL_TOLERANCE = 1e-7
FORMAL_DECIMAL_PRECISION = 80
IPX_SOFT_WALL_SECONDS = 900.0
IPX_PARENT_HARD_WALL_SECONDS = 1_020.0
SIMPLEX_SOFT_WALL_SECONDS = 600.0
SIMPLEX_PARENT_HARD_WALL_SECONDS = 720.0
TOTAL_LP_PARENT_WALL_SECONDS = 4_500.0
MAX_SIMPLEX_CHECKPOINTS = 4
PROCESS_RSS_LIMIT_GIB = 35.0
AGGREGATE_RSS_LIMIT_GIB = 75.0
HOST_MEMORY_RESERVE_GIB = 15.0
MONITOR_INTERVAL_SECONDS = 0.5
HEARTBEAT_INTERVAL_SECONDS = 5.0
TERMINATION_GRACE_SECONDS = 30.0
OPTIMAL_OBJECTIVE_RELATIVE_TOLERANCE = 1e-7
OPTIMAL_OBJECTIVE_ABSOLUTE_TOLERANCE = 1e-4


@dataclass(frozen=True)
class PhaseSpec:
    """One immutable B1/B2 phase from the D42 result-before contract."""

    key: str
    solver_name: str
    soft_wall_seconds: float
    parent_hard_wall_seconds: float
    checkpoint_index: int | None
    prior_simplex_basis_required: bool


PHASE_SPECS = (
    PhaseSpec(
        "ipx",
        "ipx",
        IPX_SOFT_WALL_SECONDS,
        IPX_PARENT_HARD_WALL_SECONDS,
        None,
        False,
    ),
    *tuple(
        PhaseSpec(
            f"simplex_{index}",
            "simplex",
            SIMPLEX_SOFT_WALL_SECONDS,
            SIMPLEX_PARENT_HARD_WALL_SECONDS,
            index,
            index > 1,
        )
        for index in range(1, MAX_SIMPLEX_CHECKPOINTS + 1)
    ),
)
PHASE_BY_KEY = {spec.key: spec for spec in PHASE_SPECS}


def formal_phase_plan() -> list[dict[str, Any]]:
    """Return the exact serial B1/B2 plan as JSON-compatible evidence."""

    return [asdict(spec) for spec in PHASE_SPECS]


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(_canonical_json_bytes(payload))
    temporary.replace(path)


def _normalised_array(typecode: str, values: Iterable[Any]) -> array[Any]:
    payload = array(typecode, values)
    if sys.byteorder != "little":
        payload.byteswap()
    return payload


def _write_binary_archive(
    path: Path,
    *,
    magic: bytes,
    header: dict[str, Any],
    arrays: Sequence[tuple[str, str, Iterable[Any]]],
) -> None:
    if path.exists():
        raise FileExistsError(f"D42 refuses to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    layout: list[dict[str, Any]] = []
    normalized: list[tuple[str, str, array[Any]]] = []
    for label, typecode, values in arrays:
        payload = _normalised_array(typecode, values)
        layout.append(
            {
                "label": label,
                "typecode": typecode,
                "count": len(payload),
                "byte_count": len(payload) * payload.itemsize,
            }
        )
        normalized.append((label, typecode, payload))
    full_header = {**header, "array_layout": layout}
    encoded_header = _canonical_json_bytes(full_header)
    with path.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            compresslevel=6,
            mtime=0,
        ) as compressed:
            compressed.write(magic)
            compressed.write(struct.pack("<Q", len(encoded_header)))
            compressed.write(encoded_header)
            for label, typecode, payload in normalized:
                encoded_label = label.encode("utf-8")
                compressed.write(struct.pack("<Q", len(encoded_label)))
                compressed.write(encoded_label)
                compressed.write(typecode.encode("ascii"))
                compressed.write(struct.pack("<Q", len(payload)))
                raw_values = payload.tobytes()
                compressed.write(struct.pack("<Q", len(raw_values)))
                compressed.write(raw_values)


def _read_exact(stream: Any, count: int) -> bytes:
    payload = stream.read(count)
    if len(payload) != count:
        raise ValueError("truncated D42 binary archive")
    return payload


def _read_binary_archive(
    path: Path,
    *,
    expected_magic: bytes,
) -> tuple[dict[str, Any], dict[str, array[Any]]]:
    with gzip.open(path, "rb") as stream:
        if _read_exact(stream, len(expected_magic)) != expected_magic:
            raise ValueError("D42 binary archive magic mismatch")
        header_size = struct.unpack("<Q", _read_exact(stream, 8))[0]
        header = json.loads(_read_exact(stream, header_size).decode("utf-8"))
        if not isinstance(header, dict):
            raise ValueError("D42 binary archive header is not an object")
        arrays: dict[str, array[Any]] = {}
        for expected in header.get("array_layout", []):
            label_size = struct.unpack("<Q", _read_exact(stream, 8))[0]
            label = _read_exact(stream, label_size).decode("utf-8")
            typecode = _read_exact(stream, 1).decode("ascii")
            count = struct.unpack("<Q", _read_exact(stream, 8))[0]
            byte_count = struct.unpack("<Q", _read_exact(stream, 8))[0]
            if (
                label != expected.get("label")
                or typecode != expected.get("typecode")
                or count != expected.get("count")
                or byte_count != expected.get("byte_count")
            ):
                raise ValueError("D42 binary archive layout mismatch")
            values = array(typecode)
            values.frombytes(_read_exact(stream, byte_count))
            if sys.byteorder != "little":
                values.byteswap()
            if len(values) != count:
                raise ValueError("D42 binary archive array length mismatch")
            arrays[label] = values
        if stream.read(1) != b"":
            raise ValueError("D42 binary archive has trailing data")
    return header, arrays


def write_lp_archive(lp: object, path: Path) -> dict[str, Any]:
    """Persist one deterministic compressed copy of a frozen continuous LP."""

    audit = audit_highs_lp(lp)
    if audit["noncontinuous_column_count"] != 0:
        raise ValueError("D42 Gate B LP archive must be continuous")
    lp_sha256 = fingerprint_highs_lp(lp)
    integrality = (
        [int(value.value) for value in lp.integrality_]
        if len(lp.integrality_)
        else []
    )
    header = {
        "schema_id": LP_ARCHIVE_SCHEMA_ID,
        "lp_sha256": lp_sha256,
        "objective_sense": audit["objective_sense"],
        "objective_offset": float(lp.offset_),
        "num_col": audit["num_col"],
        "num_row": audit["num_row"],
        "num_nz": audit["num_nz"],
        "highs_version": SUPPORTED_HIGHS_VERSION,
        "audit": audit,
    }
    _write_binary_archive(
        path,
        magic=LP_ARCHIVE_MAGIC,
        header=header,
        arrays=(
            ("col_cost", "d", (float(value) for value in lp.col_cost_)),
            ("col_lower", "d", (float(value) for value in lp.col_lower_)),
            ("col_upper", "d", (float(value) for value in lp.col_upper_)),
            ("row_lower", "d", (float(value) for value in lp.row_lower_)),
            ("row_upper", "d", (float(value) for value in lp.row_upper_)),
            ("integrality", "b", integrality),
            ("matrix_start", "q", (int(value) for value in lp.a_matrix_.start_)),
            ("matrix_index", "q", (int(value) for value in lp.a_matrix_.index_)),
            ("matrix_value", "d", (float(value) for value in lp.a_matrix_.value_)),
        ),
    )
    return {
        **header,
        "archive_file": path.name,
        "archive_sha256": _sha256(path),
    }


def read_lp_archive(
    path: Path,
    *,
    expected_lp_sha256: str | None = None,
) -> tuple[object, dict[str, Any]]:
    """Reconstruct a ``HighsLp`` and reject any byte or identity mismatch."""

    import highspy

    header, arrays = _read_binary_archive(path, expected_magic=LP_ARCHIVE_MAGIC)
    if header.get("schema_id") != LP_ARCHIVE_SCHEMA_ID:
        raise ValueError("D42 LP archive schema mismatch")
    if header.get("highs_version") != SUPPORTED_HIGHS_VERSION:
        raise ValueError("D42 LP archive HiGHS version mismatch")
    required = {
        "col_cost",
        "col_lower",
        "col_upper",
        "row_lower",
        "row_upper",
        "integrality",
        "matrix_start",
        "matrix_index",
        "matrix_value",
    }
    if set(arrays) != required:
        raise ValueError("D42 LP archive array set mismatch")
    lp = highspy.HighsLp()
    lp.num_col_ = int(header["num_col"])
    lp.num_row_ = int(header["num_row"])
    lp.offset_ = float(header["objective_offset"])
    sense = header.get("objective_sense")
    if sense != "minimize":
        raise ValueError("D42 Gate B only accepts minimization LP archives")
    lp.sense_ = highspy.ObjSense.kMinimize
    lp.col_cost_ = arrays["col_cost"]
    lp.col_lower_ = arrays["col_lower"]
    lp.col_upper_ = arrays["col_upper"]
    lp.row_lower_ = arrays["row_lower"]
    lp.row_upper_ = arrays["row_upper"]
    lp.integrality_ = [
        highspy.HighsVarType(int(value)) for value in arrays["integrality"]
    ]
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_ = arrays["matrix_start"]
    lp.a_matrix_.index_ = arrays["matrix_index"]
    lp.a_matrix_.value_ = arrays["matrix_value"]
    audit = audit_highs_lp(lp)
    lp_sha256 = fingerprint_highs_lp(lp)
    if lp_sha256 != header.get("lp_sha256"):
        raise ValueError("D42 LP archive fingerprint does not match its header")
    if expected_lp_sha256 is not None and lp_sha256 != expected_lp_sha256:
        raise ValueError("D42 LP archive fingerprint differs from the locked identity")
    if audit != header.get("audit"):
        raise ValueError("D42 LP archive structural audit differs from its header")
    return lp, {
        **header,
        "archive_file": path.name,
        "archive_sha256": _sha256(path),
        "roundtrip_fingerprint_passed": True,
    }


def _phase_paths(output_dir: Path, phase_key: str) -> dict[str, Path]:
    if phase_key not in PHASE_BY_KEY:
        raise ValueError(f"unknown D42 Gate B phase: {phase_key}")
    prefix = f"phase_{phase_key}"
    return {
        "result": output_dir / f"{prefix}_result.json",
        "execution": output_dir / f"{prefix}_execution.json",
        "solver_log": output_dir / f"{prefix}_solver.log",
        "heartbeat": output_dir / f"{prefix}_heartbeat.ndjson",
        "progress": output_dir / f"{prefix}_progress.json",
        "solution": output_dir / f"{prefix}_solution.bin.gz",
        "certificate": output_dir / f"{prefix}_certificate.json",
        "basis": output_dir / f"{prefix}_basis.bas",
        "basis_meta": output_dir / f"{prefix}_basis.json",
    }


def _set_locked_options(owner: object, spec: PhaseSpec) -> dict[str, Any]:
    import highspy

    options: dict[str, Any] = {
        "output_flag": True,
        "presolve": "off",
        "solver": spec.solver_name,
        "threads": FORMAL_THREADS,
        "random_seed": FORMAL_RANDOM_SEED,
        "primal_feasibility_tolerance": FORMAL_TOLERANCE,
        "dual_feasibility_tolerance": FORMAL_TOLERANCE,
        "primal_residual_tolerance": FORMAL_TOLERANCE,
        "dual_residual_tolerance": FORMAL_TOLERANCE,
        "optimality_tolerance": FORMAL_TOLERANCE,
        "ipm_optimality_tolerance": FORMAL_TOLERANCE,
        "kkt_tolerance": FORMAL_TOLERANCE,
        "user_objective_scale": 0,
        "user_bound_scale": 0,
    }
    if spec.solver_name == "ipx":
        options["run_crossover"] = "on"
    else:
        options["simplex_strategy"] = 1
        options["simplex_scale_strategy"] = 2
    for name, value in options.items():
        status = owner.setOptionValue(name, value)
        if status != highspy.HighsStatus.kOk:
            raise RuntimeError(f"HiGHS rejected locked option {name}={value!r}: {status}")
    return options


def _finite_or_none(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _info_audit(owner: object, info: object) -> dict[str, Any]:
    numeric_names = (
        "objective_function_value",
        "max_complementarity_violation",
        "max_dual_infeasibility",
        "max_dual_residual_error",
        "max_primal_infeasibility",
        "max_primal_residual_error",
        "max_relative_dual_infeasibility",
        "max_relative_dual_residual_error",
        "max_relative_primal_infeasibility",
        "max_relative_primal_residual_error",
        "primal_dual_integral",
        "primal_dual_objective_error",
        "sum_dual_infeasibilities",
        "sum_primal_infeasibilities",
    )
    integer_names = (
        "basis_validity",
        "crossover_iteration_count",
        "ipm_iteration_count",
        "num_complementarity_violations",
        "num_dual_infeasibilities",
        "num_dual_residual_errors",
        "num_primal_infeasibilities",
        "num_primal_residual_errors",
        "simplex_iteration_count",
    )
    payload = {name: _finite_or_none(getattr(info, name)) for name in numeric_names}
    payload.update({name: int(getattr(info, name)) for name in integer_names})
    payload.update(
        {
            "valid": bool(info.valid),
            "primal_solution_status": owner.solutionStatusToString(
                info.primal_solution_status
            ),
            "dual_solution_status": owner.solutionStatusToString(
                info.dual_solution_status
            ),
        }
    )
    return payload


def _write_solution_archive(
    path: Path,
    *,
    solution: object,
    lp_sha256: str,
    phase_key: str,
    model_status: str,
) -> dict[str, Any]:
    header = {
        "schema_id": SOLUTION_ARCHIVE_SCHEMA_ID,
        "lp_sha256": lp_sha256,
        "phase": phase_key,
        "model_status": model_status,
        "value_valid": bool(solution.value_valid),
        "dual_valid": bool(solution.dual_valid),
    }
    _write_binary_archive(
        path,
        magic=SOLUTION_ARCHIVE_MAGIC,
        header=header,
        arrays=(
            ("col_value", "d", (float(value) for value in solution.col_value)),
            ("col_dual", "d", (float(value) for value in solution.col_dual)),
            ("row_value", "d", (float(value) for value in solution.row_value)),
            ("row_dual", "d", (float(value) for value in solution.row_dual)),
        ),
    )
    return {
        **header,
        "archive_file": path.name,
        "archive_sha256": _sha256(path),
    }


def _load_basis_checkpoint(
    *,
    owner: object,
    basis_path: Path,
    basis_meta_path: Path,
    expected_lp_sha256: str,
) -> dict[str, Any]:
    import highspy

    metadata = json.loads(basis_meta_path.read_text(encoding="utf-8"))
    if metadata.get("schema_id") != BASIS_SCHEMA_ID:
        raise ValueError("D42 basis checkpoint schema mismatch")
    if metadata.get("lp_sha256") != expected_lp_sha256:
        raise ValueError("D42 basis checkpoint LP fingerprint mismatch")
    if metadata.get("basis_valid") is not True:
        raise ValueError("D42 basis checkpoint is not valid")
    if metadata.get("basis_file_sha256") != _sha256(basis_path):
        raise ValueError("D42 basis checkpoint file hash mismatch")
    status = owner.readBasis(str(basis_path))
    if status == highspy.HighsStatus.kError:
        raise ValueError(f"HiGHS rejected D42 basis checkpoint: {status}")
    if owner.getBasis().valid is not True:
        raise ValueError("HiGHS loaded an invalid D42 basis checkpoint")
    return {
        "basis_file": basis_path.name,
        "basis_meta_file": basis_meta_path.name,
        "basis_file_sha256": metadata["basis_file_sha256"],
        "basis_meta_sha256": _sha256(basis_meta_path),
        "source_phase": metadata.get("phase"),
        "loaded": True,
    }


def _write_basis_checkpoint(
    *,
    owner: object,
    basis_path: Path,
    basis_meta_path: Path,
    lp_sha256: str,
    phase_key: str,
) -> dict[str, Any]:
    import highspy

    basis = owner.getBasis()
    metadata: dict[str, Any] = {
        "schema_id": BASIS_SCHEMA_ID,
        "phase": phase_key,
        "lp_sha256": lp_sha256,
        "basis_valid": bool(basis.valid),
        "basis_file": None,
        "basis_file_sha256": None,
    }
    if basis.valid:
        status = owner.writeBasis(str(basis_path))
        if status == highspy.HighsStatus.kError or not basis_path.is_file():
            raise RuntimeError(f"HiGHS failed to write D42 basis: {status}")
        metadata["basis_file"] = basis_path.name
        metadata["basis_file_sha256"] = _sha256(basis_path)
    _atomic_write_json(basis_meta_path, metadata)
    return {**metadata, "basis_meta_sha256": _sha256(basis_meta_path)}


def _at_most(value: float | None, threshold: float) -> bool:
    return value is not None and value <= threshold


def _residual_passed_or_unavailable(
    value: float | None,
    count: int | None,
) -> bool:
    """Accept a checked residual or HiGHS' explicit ``-1`` unavailable state."""

    if count == -1 and value is None:
        return True
    return _at_most(value, FORMAL_TOLERANCE)


def _classify_phase(
    *,
    model_status: str,
    info_audit: dict[str, Any],
    certificate: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    objective = info_audit.get("objective_function_value")
    lower = certificate.get("lower_bound_float")
    compatible_direction = bool(
        objective is not None
        and lower is not None
        and lower
        <= objective
        + max(
            OPTIMAL_OBJECTIVE_ABSOLUTE_TOLERANCE,
            abs(objective) * OPTIMAL_OBJECTIVE_RELATIVE_TOLERANCE,
        )
    )
    close_at_optimum = bool(
        compatible_direction
        and math.isclose(
            objective,
            lower,
            rel_tol=OPTIMAL_OBJECTIVE_RELATIVE_TOLERANCE,
            abs_tol=OPTIMAL_OBJECTIVE_ABSOLUTE_TOLERANCE,
        )
    )
    kkt_passed = all(
        (
            info_audit.get("valid") is True,
            str(info_audit.get("primal_solution_status", "")).lower()
            == "feasible",
            str(info_audit.get("dual_solution_status", "")).lower()
            == "feasible",
            _at_most(info_audit.get("max_primal_infeasibility"), FORMAL_TOLERANCE),
            _at_most(info_audit.get("max_dual_infeasibility"), FORMAL_TOLERANCE),
            _residual_passed_or_unavailable(
                info_audit.get("max_primal_residual_error"),
                info_audit.get("num_primal_residual_errors"),
            ),
            _residual_passed_or_unavailable(
                info_audit.get("max_dual_residual_error"),
                info_audit.get("num_dual_residual_errors"),
            ),
            _at_most(info_audit.get("primal_dual_objective_error"), FORMAL_TOLERANCE),
        )
    )
    optimal = model_status.strip().lower() == "optimal"
    certificate_eligible = certificate.get("formal_lower_bound_eligible") is True
    optimal_eligible = all(
        (optimal, kkt_passed, certificate_eligible, compatible_direction, close_at_optimum)
    )
    if optimal_eligible:
        classification = "certified_optimal_relaxation"
    elif certificate_eligible:
        classification = "certified_finite_lower_bound"
    else:
        classification = "native_state_without_certificate"
    return classification, {
        "native_optimal_status": optimal,
        "kkt_passed": kkt_passed,
        "primal_residual_check_available": (
            info_audit.get("num_primal_residual_errors") != -1
        ),
        "dual_residual_check_available": (
            info_audit.get("num_dual_residual_errors") != -1
        ),
        "certificate_eligible": certificate_eligible,
        "certificate_not_above_primal": compatible_direction,
        "certificate_close_to_primal_at_optimum": close_at_optimum,
        "certified_optimal_relaxation": optimal_eligible,
        "passed": classification
        in {"certified_optimal_relaxation", "certified_finite_lower_bound"},
    }


def run_phase_child(
    *,
    lp_archive_path: Path,
    expected_lp_sha256: str,
    phase_key: str,
    output_dir: Path,
    input_basis_path: Path | None = None,
    input_basis_meta_path: Path | None = None,
) -> dict[str, Any]:
    """Run one formal phase in the current clean child process."""

    import highspy

    if phase_key not in PHASE_BY_KEY:
        raise ValueError(f"unknown D42 Gate B phase: {phase_key}")
    spec = PHASE_BY_KEY[phase_key]
    if (input_basis_path is None) != (input_basis_meta_path is None):
        raise ValueError("D42 input basis and metadata must be provided together")
    if spec.prior_simplex_basis_required and input_basis_path is None:
        raise ValueError(f"{phase_key} requires the preceding simplex basis")
    paths = _phase_paths(output_dir, phase_key)
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in ("result", "solution", "certificate", "basis", "basis_meta"):
        if paths[key].exists():
            raise FileExistsError(f"D42 refuses to overwrite {paths[key]}")

    lp, archive_audit = read_lp_archive(
        lp_archive_path,
        expected_lp_sha256=expected_lp_sha256,
    )
    highspy.Highs.resetGlobalScheduler(True)
    owner = highspy.Highs()
    options = _set_locked_options(owner, spec)
    pass_status = owner.passModel(lp)
    if pass_status != highspy.HighsStatus.kOk:
        raise RuntimeError(f"HiGHS passModel failed: {pass_status}")
    input_basis_audit = None
    if input_basis_path is not None and input_basis_meta_path is not None:
        input_basis_audit = _load_basis_checkpoint(
            owner=owner,
            basis_path=input_basis_path,
            basis_meta_path=input_basis_meta_path,
            expected_lp_sha256=expected_lp_sha256,
        )

    started = perf_counter()
    last_progress = -HEARTBEAT_INTERVAL_SECONDS
    callback_count = 0
    soft_interrupt_requested = False
    latest_iterations = {"ipm": 0, "simplex": 0}

    def write_progress(state: str) -> None:
        _atomic_write_json(
            paths["progress"],
            {
                "schema_id": PHASE_EXECUTION_SCHEMA_ID,
                "phase": phase_key,
                "pid": os.getpid(),
                "state": state,
                "elapsed_seconds": perf_counter() - started,
                "ipm_iteration_count": latest_iterations["ipm"],
                "simplex_iteration_count": latest_iterations["simplex"],
                "callback_count": callback_count,
                "soft_interrupt_requested": soft_interrupt_requested,
            },
        )

    write_progress("native_solve_starting")

    def interrupt(event: object) -> None:
        nonlocal callback_count, last_progress, soft_interrupt_requested
        callback_count += 1
        latest_iterations["ipm"] = int(event.data_out.ipm_iteration_count)
        latest_iterations["simplex"] = int(
            event.data_out.simplex_iteration_count
        )
        elapsed = perf_counter() - started
        if elapsed - last_progress >= HEARTBEAT_INTERVAL_SECONDS:
            write_progress("native_solve_running")
            last_progress = elapsed
        if elapsed >= spec.soft_wall_seconds:
            soft_interrupt_requested = True
            write_progress("soft_interrupt_requested")
            event.interrupt()

    if spec.solver_name == "ipx":
        owner.cbIpmInterrupt += interrupt
    else:
        owner.cbSimplexInterrupt += interrupt
    run_status = owner.run()
    if run_status == highspy.HighsStatus.kError:
        raise RuntimeError("HiGHS failed without an auditable D42 native state")

    info = owner.getInfo()
    solution = owner.getSolution()
    model_status = owner.modelStatusToString(owner.getModelStatus())
    latest_iterations["ipm"] = int(info.ipm_iteration_count)
    latest_iterations["simplex"] = int(info.simplex_iteration_count)
    write_progress("native_returned_certifying")

    solution_audit = _write_solution_archive(
        paths["solution"],
        solution=solution,
        lp_sha256=expected_lp_sha256,
        phase_key=phase_key,
        model_status=model_status,
    )
    certificate = certify_lagrangian_lower_bound(
        lp,
        tuple(float(value) for value in solution.row_dual),
        expected_lp_sha256=expected_lp_sha256,
        precision=FORMAL_DECIMAL_PRECISION,
    ).to_audit()
    _atomic_write_json(paths["certificate"], certificate)
    basis_audit = _write_basis_checkpoint(
        owner=owner,
        basis_path=paths["basis"],
        basis_meta_path=paths["basis_meta"],
        lp_sha256=expected_lp_sha256,
        phase_key=phase_key,
    )
    info_audit = _info_audit(owner, info)
    classification, acceptance = _classify_phase(
        model_status=model_status,
        info_audit=info_audit,
        certificate=certificate,
    )
    result = {
        "schema_id": PHASE_RESULT_SCHEMA_ID,
        "status": classification,
        "phase": phase_key,
        "solver_name": spec.solver_name,
        "lp_sha256": expected_lp_sha256,
        "lp_archive_sha256": archive_audit["archive_sha256"],
        "highs_version": owner.version(),
        "run_status": str(run_status),
        "model_status": model_status,
        "callback_count": callback_count,
        "soft_interrupt_requested": soft_interrupt_requested,
        "runtime_seconds": perf_counter() - started,
        "locked_options": options,
        "phase_spec": asdict(spec),
        "input_basis": input_basis_audit,
        "native_info": info_audit,
        "native_solution": solution_audit,
        "solution_sha256": _sha256(paths["solution"]),
        "certificate": certificate,
        "certificate_sha256": _sha256(paths["certificate"]),
        "basis": basis_audit,
        "acceptance_audit": acceptance,
        "formal_lower_bound_eligible": acceptance["passed"],
        "technical_ranking_permitted": False,
    }
    _atomic_write_json(paths["result"], result)
    write_progress("phase_artifacts_complete")
    highspy.Highs.resetGlobalScheduler(True)
    return result


def _available_memory_gib() -> float | None:
    path = Path("/proc/meminfo")
    if not path.is_file():
        return None
    for line in path.read_text(encoding="ascii").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / (1024.0**2)
    return None


def _process_table() -> dict[int, tuple[int, float]]:
    table: dict[int, tuple[int, float]] = {}
    page_size = os.sysconf("SC_PAGE_SIZE") if os.name != "nt" else 4096
    proc = Path("/proc")
    if not proc.is_dir():
        return table
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="ascii")
            right = stat.rfind(")")
            fields = stat[right + 2 :].split()
            ppid = int(fields[1])
            resident_pages = int(
                (entry / "statm").read_text(encoding="ascii").split()[1]
            )
            table[int(entry.name)] = (
                ppid,
                resident_pages * page_size / (1024.0**3),
            )
        except (FileNotFoundError, IndexError, OSError, ValueError):
            continue
    return table


def _process_tree_rss_gib(root_pid: int) -> float | None:
    table = _process_table()
    if root_pid not in table:
        return None
    selected = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _rss) in table.items():
            if ppid in selected and pid not in selected:
                selected.add(pid)
                changed = True
    return sum(table[pid][1] for pid in selected if pid in table)


def _process_rss_gib(pid: int) -> float | None:
    entry = _process_table().get(pid)
    return None if entry is None else entry[1]


def monitor_stop_reason(
    *,
    phase_elapsed_seconds: float,
    phase_hard_wall_seconds: float,
    total_elapsed_seconds: float,
    child_tree_rss_gib: float | None,
    aggregate_rss_gib: float | None,
    available_memory_gib: float | None,
) -> str | None:
    """Apply D42 hard-wall and memory stops in frozen priority order."""

    if total_elapsed_seconds >= TOTAL_LP_PARENT_WALL_SECONDS:
        return "total_lp_parent_wall_reached"
    if phase_elapsed_seconds >= phase_hard_wall_seconds:
        return "phase_parent_hard_wall_reached"
    if child_tree_rss_gib is not None and child_tree_rss_gib >= PROCESS_RSS_LIMIT_GIB:
        return "process_tree_rss_limit_reached"
    if aggregate_rss_gib is not None and aggregate_rss_gib >= AGGREGATE_RSS_LIMIT_GIB:
        return "aggregate_rss_limit_reached"
    if available_memory_gib is not None and available_memory_gib < HOST_MEMORY_RESERVE_GIB:
        return "host_memory_reserve_breached"
    return None


def _terminate_process_group(process: subprocess.Popen[Any]) -> str:
    if process.poll() is not None:
        return "already_exited"
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=TERMINATION_GRACE_SECONDS)
        return "sigterm"
    except (OSError, subprocess.TimeoutExpired):
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
        process.wait(timeout=TERMINATION_GRACE_SECONDS)
        return "sigkill"


def _phase_command(
    *,
    lp_archive_path: Path,
    expected_lp_sha256: str,
    phase_key: str,
    output_dir: Path,
    input_basis_path: Path | None,
    input_basis_meta_path: Path | None,
) -> list[str]:
    command = [
        sys.executable,
        "-u",
        "-m",
        "tes_bess_boundary.e0d42_gate_b_executor",
        "_phase-child",
        "--lp-archive",
        str(lp_archive_path),
        "--expected-lp-sha256",
        expected_lp_sha256,
        "--phase",
        phase_key,
        "--output-dir",
        str(output_dir),
    ]
    if input_basis_path is not None and input_basis_meta_path is not None:
        command.extend(
            [
                "--input-basis",
                str(input_basis_path),
                "--input-basis-meta",
                str(input_basis_meta_path),
            ]
        )
    return command


def run_monitored_phase(
    *,
    lp_archive_path: Path,
    expected_lp_sha256: str,
    phase_key: str,
    output_dir: Path,
    total_run_started: float,
    input_basis_path: Path | None = None,
    input_basis_meta_path: Path | None = None,
) -> dict[str, Any]:
    """Run one clean child under Linux parent wall-clock and resource gates."""

    if phase_key not in PHASE_BY_KEY:
        raise ValueError(f"unknown D42 Gate B phase: {phase_key}")
    spec = PHASE_BY_KEY[phase_key]
    paths = _phase_paths(output_dir, phase_key)
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in (
        "result",
        "execution",
        "solver_log",
        "heartbeat",
        "solution",
        "certificate",
        "basis",
        "basis_meta",
    ):
        if paths[key].exists():
            raise FileExistsError(f"D42 refuses to overwrite {paths[key]}")
    _lp, archive_audit = read_lp_archive(
        lp_archive_path,
        expected_lp_sha256=expected_lp_sha256,
    )
    del _lp
    available_before = _available_memory_gib()
    if available_before is None:
        raise RuntimeError("D42 formal parent execution requires Linux /proc")
    if available_before < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D42 host memory is below the frozen reserve")
    total_before = perf_counter() - total_run_started
    if total_before >= TOTAL_LP_PARENT_WALL_SECONDS:
        raise RuntimeError("D42 total LP parent wall is already exhausted")

    command = _phase_command(
        lp_archive_path=lp_archive_path,
        expected_lp_sha256=expected_lp_sha256,
        phase_key=phase_key,
        output_dir=output_dir,
        input_basis_path=input_basis_path,
        input_basis_meta_path=input_basis_meta_path,
    )
    started_payload = {
        "schema_id": PHASE_EXECUTION_SCHEMA_ID,
        "status": "child_starting",
        "phase": phase_key,
        "lp_sha256": expected_lp_sha256,
        "lp_archive_sha256": archive_audit["archive_sha256"],
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "available_memory_before_gib": available_before,
        "hard_wall_enforced_by_parent": True,
        "phase_spec": asdict(spec),
        "formal_phase_plan": formal_phase_plan(),
        "resource_thresholds": {
            "process_tree_rss_limit_gib": PROCESS_RSS_LIMIT_GIB,
            "aggregate_rss_limit_gib": AGGREGATE_RSS_LIMIT_GIB,
            "host_memory_reserve_gib": HOST_MEMORY_RESERVE_GIB,
            "monitor_interval_seconds": MONITOR_INTERVAL_SECONDS,
            "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
            "termination_grace_seconds": TERMINATION_GRACE_SECONDS,
            "total_lp_parent_wall_seconds": TOTAL_LP_PARENT_WALL_SECONDS,
        },
    }
    _atomic_write_json(paths["execution"], started_payload)

    peak_child_tree = 0.0
    peak_aggregate = 0.0
    minimum_available = available_before
    rss_samples = 0
    memory_samples = 0
    stop_reason: str | None = None
    termination_signal: str | None = None
    phase_started = perf_counter()
    last_heartbeat = -HEARTBEAT_INTERVAL_SECONDS
    with paths["solver_log"].open(
        "w", encoding="utf-8", newline="\n"
    ) as solver_log, paths["heartbeat"].open(
        "w", encoding="utf-8", newline="\n", buffering=1
    ) as heartbeat_log:
        process = subprocess.Popen(
            command,
            stdout=solver_log,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
        )
        while process.poll() is None:
            phase_elapsed = perf_counter() - phase_started
            total_elapsed = perf_counter() - total_run_started
            child_tree = _process_tree_rss_gib(process.pid)
            parent_rss = _process_rss_gib(os.getpid())
            available = _available_memory_gib()
            aggregate = (
                child_tree + parent_rss
                if child_tree is not None and parent_rss is not None
                else None
            )
            if child_tree is not None:
                peak_child_tree = max(peak_child_tree, child_tree)
                rss_samples += 1
            if aggregate is not None:
                peak_aggregate = max(peak_aggregate, aggregate)
            if available is not None:
                minimum_available = min(minimum_available, available)
                memory_samples += 1
            if phase_elapsed - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                progress = None
                if paths["progress"].is_file():
                    try:
                        progress = json.loads(
                            paths["progress"].read_text(encoding="utf-8")
                        )
                    except (json.JSONDecodeError, OSError):
                        progress = {"state": "progress_read_incomplete"}
                heartbeat = {
                    "phase": phase_key,
                    "pid": process.pid,
                    "phase_elapsed_seconds": phase_elapsed,
                    "total_elapsed_seconds": total_elapsed,
                    "solver_progress": progress,
                    "child_process_tree_rss_gib": child_tree,
                    "parent_child_aggregate_rss_gib": aggregate,
                    "available_memory_gib": available,
                }
                heartbeat_log.write(json.dumps(heartbeat, sort_keys=True) + "\n")
                heartbeat_log.flush()
                last_heartbeat = phase_elapsed
            stop_reason = monitor_stop_reason(
                phase_elapsed_seconds=phase_elapsed,
                phase_hard_wall_seconds=spec.parent_hard_wall_seconds,
                total_elapsed_seconds=total_elapsed,
                child_tree_rss_gib=child_tree,
                aggregate_rss_gib=aggregate,
                available_memory_gib=available,
            )
            if stop_reason is not None:
                termination_signal = _terminate_process_group(process)
                break
            time.sleep(MONITOR_INTERVAL_SECONDS)
        return_code = process.wait()
    runtime = perf_counter() - phase_started
    result = (
        json.loads(paths["result"].read_text(encoding="utf-8"))
        if paths["result"].is_file()
        else None
    )
    hashes = {
        key: _sha256(paths[key]) if paths[key].is_file() else None
        for key in (
            "result",
            "solver_log",
            "heartbeat",
            "progress",
            "solution",
            "certificate",
            "basis",
            "basis_meta",
        )
    }
    resource_gate_passed = all(
        (
            stop_reason is None,
            rss_samples > 0,
            memory_samples > 0,
            peak_child_tree < PROCESS_RSS_LIMIT_GIB,
            peak_aggregate < AGGREGATE_RSS_LIMIT_GIB,
            minimum_available >= HOST_MEMORY_RESERVE_GIB,
        )
    )
    complete = return_code == 0 and result is not None and resource_gate_passed
    execution = {
        **started_payload,
        "status": "complete" if complete else "interrupted_or_failed",
        "return_code": return_code,
        "phase_runtime_seconds": runtime,
        "total_elapsed_seconds_after": perf_counter() - total_run_started,
        "peak_child_process_tree_rss_gib": peak_child_tree,
        "peak_parent_child_aggregate_rss_gib": peak_aggregate,
        "minimum_available_memory_gib": minimum_available,
        "rss_sample_count": rss_samples,
        "available_memory_sample_count": memory_samples,
        "stop_reason": stop_reason,
        "termination_signal": termination_signal,
        "resource_gate_passed": resource_gate_passed,
        "artifact_sha256": hashes,
        "formal_lower_bound_eligible": bool(
            complete and result.get("formal_lower_bound_eligible") is True
        ),
        "technical_ranking_permitted": False,
    }
    _atomic_write_json(paths["execution"], execution)
    return execution


def _audit_completed_phase(
    *,
    output_dir: Path,
    phase_key: str,
    expected_lp_sha256: str,
) -> dict[str, Any]:
    paths = _phase_paths(output_dir, phase_key)
    if not paths["result"].is_file() or not paths["execution"].is_file():
        return {"status": "missing", "eligible": False}
    result = json.loads(paths["result"].read_text(encoding="utf-8"))
    execution = json.loads(paths["execution"].read_text(encoding="utf-8"))
    expected_hashes = execution.get("artifact_sha256", {})
    actual_hashes = {
        key: _sha256(paths[key]) if paths[key].is_file() else None
        for key in (
            "result",
            "solver_log",
            "heartbeat",
            "progress",
            "solution",
            "certificate",
            "basis",
            "basis_meta",
        )
    }
    artifact_hashes_passed = expected_hashes == actual_hashes
    identity_passed = all(
        (
            result.get("schema_id") == PHASE_RESULT_SCHEMA_ID,
            execution.get("schema_id") == PHASE_EXECUTION_SCHEMA_ID,
            result.get("phase") == phase_key,
            execution.get("phase") == phase_key,
            result.get("lp_sha256") == expected_lp_sha256,
            execution.get("lp_sha256") == expected_lp_sha256,
        )
    )
    execution_passed = all(
        (
            execution.get("status") == "complete",
            execution.get("return_code") == 0,
            execution.get("resource_gate_passed") is True,
            execution.get("stop_reason") is None,
            execution.get("hard_wall_enforced_by_parent") is True,
        )
    )
    certificate_file = (
        json.loads(paths["certificate"].read_text(encoding="utf-8"))
        if paths["certificate"].is_file()
        else None
    )
    certificate_passed = all(
        (
            certificate_file is not None,
            result.get("certificate") == certificate_file,
            result.get("certificate_sha256") == actual_hashes["certificate"],
            certificate_file.get("lp_sha256") == expected_lp_sha256
            if certificate_file is not None
            else False,
        )
    )
    solution_passed = all(
        (
            actual_hashes["solution"] is not None,
            result.get("solution_sha256") == actual_hashes["solution"],
        )
    )
    basis = result.get("basis", {})
    basis_passed = all(
        (
            actual_hashes["basis_meta"] is not None,
            basis.get("basis_meta_sha256") == actual_hashes["basis_meta"],
            (
                basis.get("basis_file_sha256") == actual_hashes["basis"]
                if basis.get("basis_valid") is True
                else actual_hashes["basis"] is None
            ),
        )
    )
    eligible = all(
        (
            artifact_hashes_passed,
            identity_passed,
            execution_passed,
            certificate_passed,
            solution_passed,
            basis_passed,
            result.get("formal_lower_bound_eligible") is True,
            result.get("status")
            in {
                "certified_optimal_relaxation",
                "certified_finite_lower_bound",
            },
            result.get("acceptance_audit", {}).get("passed") is True,
        )
    )
    lower_bound_decimal = (
        certificate_file.get("lower_bound_decimal")
        if certificate_passed and certificate_file is not None
        else None
    )
    try:
        finite_lower = (
            lower_bound_decimal is not None
            and Decimal(lower_bound_decimal).is_finite()
        )
    except Exception:  # noqa: BLE001 - malformed evidence is ineligible
        finite_lower = False
    eligible = bool(eligible and finite_lower)
    return {
        "status": "audited" if eligible else "invalid_or_incomplete",
        "classification": result.get("status"),
        "eligible": eligible,
        "lower_bound_decimal": lower_bound_decimal if eligible else None,
        "basis_valid": bool(eligible and basis.get("basis_valid") is True),
        "artifact_hashes_passed": artifact_hashes_passed,
        "identity_passed": identity_passed,
        "execution_passed": execution_passed,
        "certificate_passed": certificate_passed,
        "solution_passed": solution_passed,
        "basis_passed": basis_passed,
        "result_sha256": actual_hashes["result"],
        "execution_sha256": _sha256(paths["execution"]),
        "basis_file": basis.get("basis_file"),
        "basis_meta_file": paths["basis_meta"].name,
    }


def compile_lp_manifest(
    *,
    output_dir: Path,
    expected_lp_sha256: str,
) -> dict[str, Any]:
    """Select the strongest independently audited phase certificate."""

    phases = {
        spec.key: _audit_completed_phase(
            output_dir=output_dir,
            phase_key=spec.key,
            expected_lp_sha256=expected_lp_sha256,
        )
        for spec in PHASE_SPECS
    }
    valid = [phase for phase in phases.values() if phase.get("eligible") is True]
    optimal = [
        phase
        for phase in valid
        if phase.get("classification") == "certified_optimal_relaxation"
    ]
    if valid:
        selected = max(valid, key=lambda item: Decimal(item["lower_bound_decimal"]))
        lower_bound_decimal = selected["lower_bound_decimal"]
        lower_bound_float = float(Decimal(lower_bound_decimal))
        selected_phase = next(
            key for key, value in phases.items() if value is selected
        )
    else:
        lower_bound_decimal = None
        lower_bound_float = None
        selected_phase = None
    any_complete_native_state = any(
        phase.get("execution_passed") is True for phase in phases.values()
    )
    if optimal:
        status = "certified_optimal_relaxation"
    elif valid:
        status = "certified_finite_lower_bound"
    elif any_complete_native_state:
        status = "native_state_without_certificate"
    else:
        status = "no_strict_certificate"
    return {
        "schema_id": LP_MANIFEST_SCHEMA_ID,
        "status": status,
        "lp_sha256": expected_lp_sha256,
        "formal_phase_plan": formal_phase_plan(),
        "formal_lower_bound_eligible": bool(valid),
        "formal_lower_bound_decimal": lower_bound_decimal,
        "formal_lower_bound_float": lower_bound_float,
        "selected_phase": selected_phase,
        "phase_audits": phases,
        "technical_ranking_permitted": False,
    }


def _completed_result(output_dir: Path, phase_key: str) -> dict[str, Any] | None:
    paths = _phase_paths(output_dir, phase_key)
    if not paths["result"].is_file() or not paths["execution"].is_file():
        return None
    execution = json.loads(paths["execution"].read_text(encoding="utf-8"))
    if execution.get("status") != "complete":
        return None
    return json.loads(paths["result"].read_text(encoding="utf-8"))


def _resource_failure_requires_stop(execution: dict[str, Any]) -> bool:
    reason = execution.get("stop_reason")
    return reason in {
        "total_lp_parent_wall_reached",
        "process_tree_rss_limit_reached",
        "aggregate_rss_limit_reached",
        "host_memory_reserve_breached",
    }


def run_frozen_lp_plan(
    *,
    lp_archive_path: Path,
    expected_lp_sha256: str,
    output_dir: Path,
    total_run_started: float,
) -> dict[str, Any]:
    """Execute B1 then at most four recoverable B2 checkpoints serially."""

    started = perf_counter()
    executions: dict[str, Any] = {}
    ipx_execution = run_monitored_phase(
        lp_archive_path=lp_archive_path,
        expected_lp_sha256=expected_lp_sha256,
        phase_key="ipx",
        output_dir=output_dir,
        total_run_started=total_run_started,
    )
    executions["ipx"] = ipx_execution
    ipx_result = _completed_result(output_dir, "ipx")
    if ipx_result is not None and ipx_result.get("status") == (
        "certified_optimal_relaxation"
    ):
        stop_reason = "ipx_certified_optimal"
    elif _resource_failure_requires_stop(ipx_execution):
        stop_reason = str(ipx_execution.get("stop_reason"))
    else:
        stop_reason = None

    prior_basis_path: Path | None = None
    prior_basis_meta_path: Path | None = None
    if ipx_result is not None and ipx_result.get("basis", {}).get("basis_valid") is True:
        ipx_paths = _phase_paths(output_dir, "ipx")
        prior_basis_path = ipx_paths["basis"]
        prior_basis_meta_path = ipx_paths["basis_meta"]

    for index in range(1, MAX_SIMPLEX_CHECKPOINTS + 1):
        if stop_reason is not None:
            break
        phase_key = f"simplex_{index}"
        if index > 1 and (prior_basis_path is None or prior_basis_meta_path is None):
            stop_reason = "preceding_simplex_basis_missing_or_invalid"
            break
        if perf_counter() - total_run_started >= TOTAL_LP_PARENT_WALL_SECONDS:
            stop_reason = "total_lp_parent_wall_reached"
            break
        execution = run_monitored_phase(
            lp_archive_path=lp_archive_path,
            expected_lp_sha256=expected_lp_sha256,
            phase_key=phase_key,
            output_dir=output_dir,
            total_run_started=total_run_started,
            input_basis_path=prior_basis_path,
            input_basis_meta_path=prior_basis_meta_path,
        )
        executions[phase_key] = execution
        result = _completed_result(output_dir, phase_key)
        if result is not None and result.get("status") == (
            "certified_optimal_relaxation"
        ):
            stop_reason = f"{phase_key}_certified_optimal"
            break
        if _resource_failure_requires_stop(execution):
            stop_reason = str(execution.get("stop_reason"))
            break
        if result is None or result.get("basis", {}).get("basis_valid") is not True:
            stop_reason = f"{phase_key}_basis_missing_or_invalid"
            break
        paths = _phase_paths(output_dir, phase_key)
        prior_basis_path = paths["basis"]
        prior_basis_meta_path = paths["basis_meta"]
    if stop_reason is None:
        stop_reason = "four_simplex_checkpoints_completed"

    manifest = compile_lp_manifest(
        output_dir=output_dir,
        expected_lp_sha256=expected_lp_sha256,
    )
    manifest_path = output_dir / "lp_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"D42 refuses to overwrite {manifest_path}")
    _atomic_write_json(manifest_path, manifest)
    execution_payload = {
        "schema_id": LP_PLAN_EXECUTION_SCHEMA_ID,
        "status": manifest["status"],
        "lp_sha256": expected_lp_sha256,
        "manifest_sha256": _sha256(manifest_path),
        "runtime_seconds": perf_counter() - started,
        "total_elapsed_seconds": perf_counter() - total_run_started,
        "stop_reason": stop_reason,
        "phase_executions": executions,
        "technical_ranking_permitted": False,
    }
    execution_path = output_dir / "lp_execution.json"
    if execution_path.exists():
        raise FileExistsError(f"D42 refuses to overwrite {execution_path}")
    _atomic_write_json(execution_path, execution_payload)
    return {"manifest": manifest, "execution": execution_payload}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    child = commands.add_parser("_phase-child")
    child.add_argument("--lp-archive", type=Path, required=True)
    child.add_argument("--expected-lp-sha256", required=True)
    child.add_argument("--phase", choices=tuple(PHASE_BY_KEY), required=True)
    child.add_argument("--output-dir", type=Path, required=True)
    child.add_argument("--input-basis", type=Path)
    child.add_argument("--input-basis-meta", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command != "_phase-child":
        raise AssertionError(f"unhandled command: {args.command}")
    payload = run_phase_child(
        lp_archive_path=args.lp_archive,
        expected_lp_sha256=args.expected_lp_sha256,
        phase_key=args.phase,
        output_dir=args.output_dir,
        input_basis_path=args.input_basis,
        input_basis_meta_path=args.input_basis_meta,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
