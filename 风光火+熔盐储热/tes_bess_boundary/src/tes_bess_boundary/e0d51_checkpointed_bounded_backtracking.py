"""D51 Gate 0 checkpointed one-block backtracking controller.

This module is deliberately limited to shortened-horizon validation.  It adds
atomic, replayable attempt checkpoints and a deterministic one-block rollback
state machine around the D50 physical-binary relax-and-fix mechanism.  It does
not authorize or expose an 8784-hour formal entry point.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
    BinaryInventory,
    extract_binary_snapshot,
    restore_binary_domains,
)
from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
    _bound_and_constraint_audit,
    _name_list_sha256,
    _service_audit,
    _sha256,
    _variable_map,
    write_seed_csv_gz,
)
from tes_bess_boundary.e0d48_hamming_primal_recovery import (
    _configure_hamming_solver,
    constraint_identity,
)
from tes_bess_boundary.e0d49_physics_first_fuel_projection_primal_recovery import (
    exact_lift_fuel_encoding,
)
from tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix import (
    BINARY_VALUE_TOLERANCE,
    StageDomainPlan,
    _objective_identity,
    apply_stage_domain_plan,
    commit_stage_snapshot,
    make_stage_domain_plan,
    prepare_d50_model,
    solve_d50_original_cost_repair,
    write_physical_snapshot,
)
from tes_bess_boundary.model import Architecture


CHECKPOINT_SCHEMA_ID = "tes_bess_boundary.e0d51_attempt_checkpoint.v1"
RESULT_SCHEMA_ID = "tes_bess_boundary.e0d51_gate0_candidate.v1"
REPAIR_SCHEMA_ID = "tes_bess_boundary.e0d51_original_cost_repair.v1"
FEASIBILITY_OBJECTIVE_COMPONENT = "d51_feasibility_objective"
NO_GOOD_COMPONENT = "d51_registered_no_good_cuts"

MAX_GATE0_PERIODS = 840
MAX_ATTEMPTS_PER_STAGE = 3
MAX_TOTAL_ROLLBACK_EVENTS = 4
MAX_ROLLBACK_DEPTH = 1
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _coerce_binary_value(raw: object, *, label: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"D51 {label} value is not numeric")
    number = float(raw)
    if not math.isfinite(number):
        raise ValueError(f"D51 {label} value is not finite")
    rounded = int(round(number))
    if rounded not in (0, 1) or abs(number - rounded) > BINARY_VALUE_TOLERANCE:
        raise ValueError(f"D51 {label} value is fractional")
    return rounded


def _atomic_publish(path: Path, content: bytes) -> None:
    """Publish one immutable file through same-directory atomic rename."""

    if path.exists():
        raise FileExistsError(f"D51 checkpoint path already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _finite_model_values(model: object) -> dict[str, float]:
    values: dict[str, float] = {}
    invalid: list[str] = []
    for name, variable in sorted(_variable_map(model).items()):
        raw = variable.value
        if raw is None or not math.isfinite(float(raw)):
            invalid.append(name)
        else:
            values[name] = float(raw)
    if invalid:
        raise ValueError(f"D51 checkpoint has non-finite variables: {invalid[:3]}")
    return values


def _variable_boundary_identity(model: object) -> dict[str, Any]:
    digest = hashlib.sha256()
    variables = _variable_map(model)
    for name, variable in sorted(variables.items()):
        for item in (
            name,
            variable.lb,
            variable.ub,
            bool(variable.fixed),
            bool(variable.is_binary()),
        ):
            digest.update(str(item).encode("utf-8"))
            digest.update(b"\0")
    return {
        "variable_count": len(variables),
        "name_bound_fixed_domain_sha256": digest.hexdigest(),
    }


def _values_csv_gzip(values: Mapping[str, float]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(("variable_name", "value"))
    for name in sorted(values):
        writer.writerow((name, format(float(values[name]), ".17g")))
    return gzip.compress(stream.getvalue().encode("utf-8"), compresslevel=9, mtime=0)


def _read_values_csv_gzip(path: Path) -> dict[str, float]:
    try:
        content = gzip.decompress(path.read_bytes()).decode("utf-8")
    except (OSError, EOFError, UnicodeDecodeError) as error:
        raise ValueError("D51 checkpoint value artifact is unreadable") from error
    rows = csv.reader(io.StringIO(content, newline=""))
    header = next(rows, None)
    if header != ["variable_name", "value"]:
        raise ValueError("D51 checkpoint value artifact has an invalid header")
    values: dict[str, float] = {}
    for row in rows:
        if len(row) != 2 or not row[0] or row[0] in values:
            raise ValueError("D51 checkpoint value artifact has malformed rows")
        try:
            number = float(row[1])
        except ValueError as error:
            raise ValueError("D51 checkpoint value artifact has a non-number") from error
        if not math.isfinite(number):
            raise ValueError("D51 checkpoint value artifact has a non-finite value")
        values[row[0]] = number
    return values


@dataclass(frozen=True)
class NoGoodCutSpec:
    """One exact physical-block pattern excluded after a failed extension."""

    stage_index: int
    block_index: int
    binary_values: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if self.stage_index < 0 or self.block_index < 0:
            raise ValueError("D51 no-good cut indices must be non-negative")
        if not self.binary_values:
            raise ValueError("D51 no-good cut requires a non-empty block")
        names = tuple(name for name, _ in self.binary_values)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("D51 no-good cut names must be sorted and unique")
        if any(value not in (0, 1) for _, value in self.binary_values):
            raise ValueError("D51 no-good cut values must be binary")

    def payload(self) -> dict[str, Any]:
        core = {
            "stage_index": self.stage_index,
            "block_index": self.block_index,
            "binary_values": {name: value for name, value in self.binary_values},
        }
        return {**core, "cut_sha256": _payload_sha256(core)}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> NoGoodCutSpec:
        raw_values = payload.get("binary_values")
        if not isinstance(raw_values, Mapping):
            raise ValueError("D51 no-good cut payload lacks binary values")
        spec = cls(
            stage_index=int(payload["stage_index"]),
            block_index=int(payload["block_index"]),
            binary_values=tuple(
                sorted(
                    (
                        str(name),
                        _coerce_binary_value(value, label="no-good cut"),
                    )
                    for name, value in raw_values.items()
                )
            ),
        )
        if payload.get("cut_sha256") != spec.payload()["cut_sha256"]:
            raise ValueError("D51 no-good cut payload hash mismatch")
        return spec


def add_registered_no_good_cut(
    model: object,
    spec: NoGoodCutSpec,
    *,
    existing_sha256: set[str] | None = None,
) -> str:
    """Add exactly one audited binary no-good cut to a model."""

    from pyomo.environ import ConstraintList, quicksum

    cut_hash = str(spec.payload()["cut_sha256"])
    if existing_sha256 is not None and cut_hash in existing_sha256:
        raise ValueError("D51 duplicate no-good cut is forbidden")
    variables = _variable_map(model)
    missing = sorted(name for name, _ in spec.binary_values if name not in variables)
    if missing:
        raise ValueError(f"D51 no-good cut variables are missing: {missing[:3]}")
    forbidden_global = sorted(
        name for name, _ in spec.binary_values if name.endswith(".installed")
    )
    if forbidden_global:
        raise ValueError("D51 no-good cut cannot exclude global topology values")
    nonbinary = sorted(
        name for name, _ in spec.binary_values if not variables[name].is_binary()
    )
    if nonbinary:
        raise ValueError(f"D51 no-good cut variables are not binary: {nonbinary[:3]}")
    if not hasattr(model, NO_GOOD_COMPONENT):
        model.add_component(NO_GOOD_COMPONENT, ConstraintList())
    component = getattr(model, NO_GOOD_COMPONENT)
    expression = quicksum(
        1.0 - variables[name] if value == 1 else variables[name]
        for name, value in spec.binary_values
    )
    component.add(expression >= 1.0)
    if existing_sha256 is not None:
        existing_sha256.add(cut_hash)
    return cut_hash


def activate_feasibility_objective(model: object) -> dict[str, Any]:
    """Replace the single active economic objective by the registered zero goal."""

    from pyomo.environ import Objective, minimize

    if hasattr(model, FEASIBILITY_OBJECTIVE_COMPONENT):
        raise ValueError("D51 feasibility objective already exists")
    objectives = tuple(
        model.component_data_objects(Objective, active=True, descend_into=True)
    )
    if len(objectives) != 1:
        raise ValueError("D51 requires exactly one active original objective")
    original = objectives[0]
    before = _objective_identity(model)
    original.deactivate()
    model.add_component(
        FEASIBILITY_OBJECTIVE_COMPONENT,
        Objective(expr=0.0, sense=minimize),
    )
    after = _objective_identity(model)
    return {
        "original_objective_name": original.name,
        "original_objective_identity": before,
        "feasibility_objective_identity": after,
        "constant_zero_objective": True,
        "passed": after["active_objective_names"] == [FEASIBILITY_OBJECTIVE_COMPONENT],
    }


def restore_original_economic_objective(
    model: object,
    objective_audit: Mapping[str, Any],
) -> dict[str, Any]:
    """Remove the Gate 0 objective and reactivate the exact original objective."""

    component = getattr(model, FEASIBILITY_OBJECTIVE_COMPONENT, None)
    if component is None or not component.active:
        raise ValueError("D51 feasibility objective is not active")
    component.deactivate()
    model.del_component(FEASIBILITY_OBJECTIVE_COMPONENT)
    original = model.find_component(str(objective_audit["original_objective_name"]))
    if original is None:
        raise ValueError("D51 original objective component is missing")
    original.activate()
    restored = _objective_identity(model)
    passed = restored == objective_audit["original_objective_identity"]
    if not passed:
        raise ValueError("D51 original objective identity was not restored")
    return {"restored_objective_identity": restored, "passed": True}


def capture_first_feasibility_incumbent(
    model: object,
    *,
    time_limit_seconds: float,
    threads: int,
    tee: bool = False,
) -> dict[str, Any]:
    """Capture and load the first complete incumbent under the zero objective."""

    import highspy

    active = _objective_identity(model)
    if active["active_objective_names"] != [FEASIBILITY_OBJECTIVE_COMPONENT]:
        raise ValueError("D51 capture requires the registered feasibility objective")
    solver = _configure_hamming_solver(
        time_limit_seconds=time_limit_seconds,
        threads=threads,
    )
    solver.config.warmstart = False
    solver.set_instance(model)
    expected_names = set(_variable_map(model))
    index_to_variable = {
        column: solver._vars[variable_id][0]
        for variable_id, column in solver._pyomo_var_to_solver_var_map.items()
    }
    if set(index_to_variable) != set(range(len(expected_names))):
        raise ValueError("D51 HiGHS/Pyomo column map is incomplete")
    if {item.name for item in index_to_variable.values()} != expected_names:
        raise ValueError("D51 HiGHS/Pyomo variable map is incomplete")
    captured: dict[str, Any] = {}

    def _callback(event: object) -> None:
        if captured:
            return
        raw = tuple(float(item) for item in event.data_out.mip_solution)
        if len(raw) != len(index_to_variable) or not all(map(math.isfinite, raw)):
            return
        captured["column_values"] = raw
        captured["capture_source"] = "mip_solution_callback"
        event.interrupt()

    solver._solver_model.cbMipSolution.subscribe(_callback)
    started = perf_counter()
    highspy.Highs.resetGlobalScheduler(True)
    try:
        results = solver.solve(
            model,
            tee=tee,
            load_solutions=False,
            warmstart=False,
        )
    finally:
        highspy.Highs.resetGlobalScheduler(True)
    runtime = perf_counter() - started
    info = solver._solver_model.getInfo()
    solution = solver._solver_model.getSolution()
    if not captured and bool(getattr(solution, "value_valid", False)):
        raw = tuple(float(item) for item in solution.col_value)
        if len(raw) == len(index_to_variable) and all(map(math.isfinite, raw)):
            captured["column_values"] = raw
            captured["capture_source"] = "returned_highs_solution"
    solver_status = {
        "termination_condition": str(results.solver.termination_condition).lower(),
        "highs_model_status": solver._solver_model.modelStatusToString(
            solver._solver_model.getModelStatus()
        ),
        "mip_node_count": int(getattr(info, "mip_node_count", -1)),
        "primal_solution_status": int(getattr(info, "primal_solution_status", -1)),
        "solution_value_valid": bool(getattr(solution, "value_valid", False)),
    }
    if not captured:
        return {
            "status": "stage_no_feasibility_incumbent",
            "incumbent_captured": False,
            "runtime_seconds": runtime,
            "solver_status": solver_status,
            "candidate_objective": "constant_zero",
            "warmstart_requested": False,
            "formal_upper_bound_eligible": False,
        }
    values: dict[str, float] = {}
    for column, number in enumerate(captured["column_values"]):
        variable = index_to_variable[column]
        variable.set_value(number, skip_validation=True)
        values[variable.name] = number
    return {
        "status": "stage_feasibility_incumbent_captured",
        "incumbent_captured": True,
        "capture_source": captured["capture_source"],
        "runtime_seconds": runtime,
        "solver_status": solver_status,
        "candidate_objective": "constant_zero",
        "reported_candidate_objective": 0.0,
        "variable_values": values,
        "variable_count": len(values),
        "expected_variable_count": len(expected_names),
        "complete_variable_mapping": set(values) == expected_names,
        "variable_names_sha256": _name_list_sha256(tuple(sorted(values))),
        "warmstart_requested": False,
        "formal_upper_bound_eligible": False,
    }


def _capacity_values(values: Mapping[str, float]) -> dict[str, float]:
    return {name: values[name] for name in sorted(values) if "capacity" in name.lower()}


def write_attempt_checkpoint(
    checkpoint_dir: Path,
    *,
    architecture: Architecture,
    stage_index: int,
    attempt_index: int,
    parent_checkpoint_sha256: str | None,
    rollback_source_checkpoint_sha256: str | None,
    fixed_snapshot_after_commit: Mapping[str, int],
    current_block_values: Mapping[str, int],
    domain_audit: Mapping[str, Any],
    commit_audit: Mapping[str, Any],
    capture_audit: Mapping[str, Any],
    original_constraint_identity: Mapping[str, Any],
    current_constraint_identity: Mapping[str, Any],
    objective_audit: Mapping[str, Any],
    no_good_specs: Sequence[NoGoodCutSpec],
    model: object,
) -> dict[str, Any]:
    """Atomically publish one complete immutable stage-attempt checkpoint."""

    if stage_index < 0 or attempt_index < 0:
        raise ValueError("D51 checkpoint indices must be non-negative")
    for label, digest in (
        ("parent", parent_checkpoint_sha256),
        ("rollback source", rollback_source_checkpoint_sha256),
    ):
        if digest is not None and SHA256_PATTERN.fullmatch(digest) is None:
            raise ValueError(f"D51 checkpoint {label} hash is invalid")
    values = _finite_model_values(model)
    fixed = {
        name: _coerce_binary_value(value, label="checkpoint fixed snapshot")
        for name, value in fixed_snapshot_after_commit.items()
    }
    current = {
        name: _coerce_binary_value(value, label="checkpoint block pattern")
        for name, value in current_block_values.items()
    }
    if not current:
        raise ValueError("D51 checkpoint current block pattern is empty")
    if not set(current).issubset(fixed):
        raise ValueError("D51 checkpoint block pattern is outside the fixed snapshot")
    for name, value in fixed.items():
        if name not in values or abs(values[name] - value) > BINARY_VALUE_TOLERANCE:
            raise ValueError("D51 checkpoint fixed values disagree with the incumbent")
    base = f"stage_{stage_index:02d}_attempt_{attempt_index:02d}"
    values_path = checkpoint_dir / f"{base}.values.csv.gz"
    manifest_path = checkpoint_dir / f"{base}.json"
    if values_path.exists() or manifest_path.exists():
        raise FileExistsError(f"D51 checkpoint attempt already exists: {base}")
    compressed = _values_csv_gzip(values)
    _atomic_publish(values_path, compressed)
    values_hash = _sha256(values_path)
    capture = {key: value for key, value in capture_audit.items() if key != "variable_values"}
    payload = {
        "schema_id": CHECKPOINT_SCHEMA_ID,
        "architecture": architecture.value,
        "state_event": "stage_incumbent_checkpointed_before_next_fixing",
        "stage_index": stage_index,
        "attempt_index": attempt_index,
        "parent_checkpoint_sha256": parent_checkpoint_sha256,
        "rollback_source_checkpoint_sha256": rollback_source_checkpoint_sha256,
        "values_artifact": {
            "relative_path": values_path.name,
            "sha256": values_hash,
            "byte_count": values_path.stat().st_size,
            "variable_count": len(values),
            "variable_names_sha256": _name_list_sha256(tuple(sorted(values))),
        },
        "capacity_variable_values": _capacity_values(values),
        "fixed_physical_values_after_commit": {name: fixed[name] for name in sorted(fixed)},
        "current_block_physical_values": {name: current[name] for name in sorted(current)},
        "global_topology_values": {
            name: fixed[name]
            for name in sorted(fixed)
            if name.endswith(".installed")
        },
        "fixed_physical_count_after_commit": len(fixed),
        "domain_audit": dict(domain_audit),
        "commit_audit": dict(commit_audit),
        "capture_audit": capture,
        "original_constraint_identity": dict(original_constraint_identity),
        "current_constraint_identity": dict(current_constraint_identity),
        "current_variable_boundary_identity": _variable_boundary_identity(model),
        "objective_audit": dict(objective_audit),
        "registered_no_good_cuts": [spec.payload() for spec in no_good_specs],
        "registered_no_good_cut_count": len(no_good_specs),
        "formal_upper_bound_eligible": False,
    }
    try:
        _atomic_publish(manifest_path, _canonical_json_bytes(payload))
    except Exception:
        values_path.unlink(missing_ok=True)
        raise
    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path),
        "values_path": str(values_path),
        "values_sha256": values_hash,
        "stage_index": stage_index,
        "attempt_index": attempt_index,
    }


def read_attempt_checkpoint(
    manifest_path: Path,
    *,
    expected_parent_sha256: str | None,
) -> tuple[dict[str, Any], dict[str, float]]:
    """Read and hash-audit one checkpoint bundle without mutating a model."""

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("D51 checkpoint manifest is unreadable") from error
    if payload.get("schema_id") != CHECKPOINT_SCHEMA_ID:
        raise ValueError("D51 checkpoint schema mismatch")
    if payload.get("architecture") != Architecture.BESS.value:
        raise ValueError("D51 Gate 0 checkpoint must be BESS")
    if payload.get("state_event") != (
        "stage_incumbent_checkpointed_before_next_fixing"
    ):
        raise ValueError("D51 checkpoint state event mismatch")
    stage_index = int(payload.get("stage_index", -1))
    attempt_index = int(payload.get("attempt_index", -1))
    if stage_index < 0 or attempt_index < 0:
        raise ValueError("D51 checkpoint indices are invalid")
    if manifest_path.name != f"stage_{stage_index:02d}_attempt_{attempt_index:02d}.json":
        raise ValueError("D51 checkpoint manifest path does not match its indices")
    parent = payload.get("parent_checkpoint_sha256")
    rollback_source = payload.get("rollback_source_checkpoint_sha256")
    for label, digest in (("parent", parent), ("rollback source", rollback_source)):
        if digest is not None and SHA256_PATTERN.fullmatch(str(digest)) is None:
            raise ValueError(f"D51 checkpoint {label} hash is invalid")
    if payload.get("parent_checkpoint_sha256") != expected_parent_sha256:
        raise ValueError("D51 checkpoint parent hash mismatch")
    if payload.get("formal_upper_bound_eligible") is not False:
        raise ValueError("D51 Gate 0 checkpoint cannot be upper-bound eligible")
    artifact = payload.get("values_artifact")
    if not isinstance(artifact, Mapping):
        raise ValueError("D51 checkpoint values artifact is missing")
    relative = Path(str(artifact.get("relative_path", "")))
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name != str(relative):
        raise ValueError("D51 checkpoint values path is not local to the bundle")
    values_path = manifest_path.parent / relative
    if not values_path.is_file() or _sha256(values_path) != artifact.get("sha256"):
        raise ValueError("D51 checkpoint values artifact hash mismatch")
    if values_path.stat().st_size != int(artifact.get("byte_count", -1)):
        raise ValueError("D51 checkpoint values artifact size mismatch")
    values = _read_values_csv_gzip(values_path)
    if len(values) != int(artifact.get("variable_count", -1)):
        raise ValueError("D51 checkpoint variable count mismatch")
    if _name_list_sha256(tuple(sorted(values))) != artifact.get(
        "variable_names_sha256"
    ):
        raise ValueError("D51 checkpoint variable-name hash mismatch")
    fixed = payload.get("fixed_physical_values_after_commit")
    current = payload.get("current_block_physical_values")
    global_values = payload.get("global_topology_values")
    if (
        not isinstance(fixed, Mapping)
        or not isinstance(current, Mapping)
        or not isinstance(global_values, Mapping)
    ):
        raise ValueError("D51 checkpoint physical snapshots are missing")
    if not set(current).issubset(fixed):
        raise ValueError("D51 checkpoint current block is outside the fixed prefix")
    if not set(global_values).issubset(fixed):
        raise ValueError("D51 checkpoint global topology is outside the fixed prefix")
    if set(current) & set(global_values):
        raise ValueError("D51 checkpoint block pattern includes global topology")
    if any(not str(name).endswith(".installed") for name in global_values):
        raise ValueError("D51 checkpoint has an unregistered global topology name")
    if len(fixed) != int(payload.get("fixed_physical_count_after_commit", -1)):
        raise ValueError("D51 checkpoint fixed physical count mismatch")
    for name, raw in fixed.items():
        value = _coerce_binary_value(raw, label="checkpoint fixed snapshot")
        if name not in values:
            raise ValueError("D51 checkpoint fixed snapshot is invalid")
        if abs(values[name] - value) > BINARY_VALUE_TOLERANCE:
            raise ValueError("D51 checkpoint fixed snapshot does not match values")
    cuts = payload.get("registered_no_good_cuts")
    if not isinstance(cuts, list) or len(cuts) != int(
        payload.get("registered_no_good_cut_count", -1)
    ):
        raise ValueError("D51 checkpoint no-good cut count mismatch")
    parsed = [NoGoodCutSpec.from_payload(item) for item in cuts]
    cut_hashes = [item.payload()["cut_sha256"] for item in parsed]
    if len(cut_hashes) != len(set(cut_hashes)):
        raise ValueError("D51 checkpoint contains duplicate no-good cuts")
    capacities = payload.get("capacity_variable_values")
    if not isinstance(capacities, Mapping):
        raise ValueError("D51 checkpoint capacity snapshot is missing")
    for name, number in capacities.items():
        if name not in values or values[name] != float(number):
            raise ValueError("D51 checkpoint capacity snapshot mismatch")
    boundary = payload.get("current_variable_boundary_identity")
    if not isinstance(boundary, Mapping):
        raise ValueError("D51 checkpoint variable-boundary identity is missing")
    return payload, values


def replay_attempt_checkpoint(
    model: object,
    manifest_path: Path,
    *,
    expected_parent_sha256: str | None,
    inventory: BinaryInventory | None = None,
    domain_plan: StageDomainPlan | None = None,
) -> dict[str, Any]:
    """Replay values, objective, cuts and optionally the exact attempt domains."""

    payload, values = read_attempt_checkpoint(
        manifest_path,
        expected_parent_sha256=expected_parent_sha256,
    )
    if constraint_identity(model) != payload["original_constraint_identity"]:
        raise ValueError("D51 replay clean constraint identity mismatch")
    variables = _variable_map(model)
    if set(variables) != set(values):
        raise ValueError("D51 replay variable identity mismatch")
    objective = activate_feasibility_objective(model)
    expected_objective = payload["objective_audit"]
    if objective != expected_objective:
        raise ValueError("D51 replay objective identity mismatch")
    cut_hashes: set[str] = set()
    for raw in payload["registered_no_good_cuts"]:
        add_registered_no_good_cut(
            model,
            NoGoodCutSpec.from_payload(raw),
            existing_sha256=cut_hashes,
        )
    if constraint_identity(model) != payload["current_constraint_identity"]:
        raise ValueError("D51 replay registered-constraint identity mismatch")
    if (inventory is None) != (domain_plan is None):
        raise ValueError("D51 replay requires inventory and domain plan together")
    domain_replay = None
    if inventory is not None and domain_plan is not None:
        fixed_after = payload["fixed_physical_values_after_commit"]
        missing_prior = sorted(set(domain_plan.fixed_physical_names) - set(fixed_after))
        if missing_prior:
            raise ValueError(
                f"D51 replay prior fixed prefix is missing: {missing_prior[:3]}"
            )
        prior_snapshot = {
            name: int(fixed_after[name]) for name in domain_plan.fixed_physical_names
        }
        if set(prior_snapshot) != set(domain_plan.fixed_physical_names):
            raise ValueError("D51 replay cannot reconstruct the prior fixed prefix")
        domain_replay = apply_stage_domain_plan(
            model,
            inventory,
            domain_plan,
            prior_snapshot,
        )
        structural_keys = (
            "stage_index",
            "current_block",
            "lookahead_block",
            "fixed_physical_count",
            "active_physical_count",
            "relaxed_physical_count",
            "projected_fuel_count",
            "fixed_physical_names_sha256",
            "active_physical_names_sha256",
            "relaxed_physical_names_sha256",
            "projected_fuel_names_sha256",
            "active_binary_count_after_domain_update",
            "active_binary_names_sha256_after_domain_update",
            "partition_complete_and_disjoint",
            "relaxed_domains_valid",
            "passed",
        )
        if any(
            domain_replay[key] != payload["domain_audit"][key]
            for key in structural_keys
        ):
            raise ValueError("D51 replay stage-domain audit mismatch")
    if _variable_boundary_identity(model) != payload[
        "current_variable_boundary_identity"
    ]:
        raise ValueError("D51 replay variable-boundary identity mismatch")
    for name, number in values.items():
        variables[name].set_value(number, skip_validation=True)
    replayed_capacity = {
        name: float(variables[name].value)
        for name in payload["capacity_variable_values"]
    }
    if replayed_capacity != payload["capacity_variable_values"]:
        raise ValueError("D51 replay capacity values mismatch")
    fixed = payload["fixed_physical_values_after_commit"]
    maximum_fixed_residual = max(
        (abs(float(variables[name].value) - int(value)) for name, value in fixed.items()),
        default=0.0,
    )
    if maximum_fixed_residual > BINARY_VALUE_TOLERANCE:
        raise ValueError("D51 replay fixed values mismatch")
    return {
        "checkpoint_manifest_sha256": _sha256(manifest_path),
        "variable_count": len(values),
        "fixed_physical_count": len(fixed),
        "registered_no_good_cut_count": len(cut_hashes),
        "stage_domain_replayed": domain_replay is not None,
        "stage_domain_replay_audit": domain_replay,
        "maximum_fixed_value_residual": maximum_fixed_residual,
        "passed": True,
    }


@dataclass(frozen=True)
class CommittedStageRecord:
    stage_index: int
    attempt_index: int
    checkpoint_sha256: str
    current_block_values: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class BacktrackingTransition:
    event: str
    next_stage_index: int | None
    rejected_record: CommittedStageRecord | None = None
    terminal_status: str | None = None


@dataclass
class BoundedBacktrackingController:
    """Pure deterministic D51 Gate 0 one-block rollback state machine."""

    stage_count: int
    max_attempts_per_stage: int = MAX_ATTEMPTS_PER_STAGE
    max_total_rollback_events: int = MAX_TOTAL_ROLLBACK_EVENTS
    current_stage_index: int = 0
    rollback_anchor_stage_index: int | None = None
    total_rollback_events: int = 0
    attempt_index_by_stage: dict[int, int] = field(default_factory=dict)
    committed_records: dict[int, CommittedStageRecord] = field(default_factory=dict)
    terminal_status: str | None = None

    def __post_init__(self) -> None:
        if self.stage_count <= 0:
            raise ValueError("D51 controller requires at least one stage")
        if self.max_attempts_per_stage != MAX_ATTEMPTS_PER_STAGE:
            raise ValueError("D51 Gate 0 attempt limit is frozen at three")
        if self.max_total_rollback_events != MAX_TOTAL_ROLLBACK_EVENTS:
            raise ValueError("D51 Gate 0 rollback budget is frozen at four")
        self.attempt_index_by_stage = {
            index: 0 for index in range(self.stage_count)
        }

    @property
    def current_attempt_index(self) -> int:
        return self.attempt_index_by_stage[self.current_stage_index]

    def record_commit(self, record: CommittedStageRecord) -> BacktrackingTransition:
        if self.terminal_status is not None:
            raise ValueError("D51 controller is already terminal")
        if record.stage_index != self.current_stage_index:
            raise ValueError("D51 commit does not match the current stage")
        if record.attempt_index != self.current_attempt_index:
            raise ValueError("D51 commit does not match the current attempt")
        if SHA256_PATTERN.fullmatch(record.checkpoint_sha256) is None:
            raise ValueError("D51 committed checkpoint hash is invalid")
        self.committed_records[record.stage_index] = record
        if (
            self.rollback_anchor_stage_index is not None
            and record.stage_index == self.rollback_anchor_stage_index - 1
        ):
            self.current_stage_index = self.rollback_anchor_stage_index
            return BacktrackingTransition(
                event="alternative_block_committed_retry_failed_frontier",
                next_stage_index=self.current_stage_index,
            )
        if self.rollback_anchor_stage_index == record.stage_index:
            self.rollback_anchor_stage_index = None
        self.current_stage_index = record.stage_index + 1
        if self.current_stage_index == self.stage_count:
            self.terminal_status = "checkpointed_path_complete"
            return BacktrackingTransition(
                event="path_complete",
                next_stage_index=None,
                terminal_status=self.terminal_status,
            )
        return BacktrackingTransition(
            event="advance",
            next_stage_index=self.current_stage_index,
        )

    def record_failure(self, stage_index: int) -> BacktrackingTransition:
        if self.terminal_status is not None:
            raise ValueError("D51 controller is already terminal")
        if stage_index != self.current_stage_index:
            raise ValueError("D51 failure does not match the current stage")
        if (
            self.rollback_anchor_stage_index is not None
            and stage_index == self.rollback_anchor_stage_index - 1
        ):
            return self._close("alternative_stage_itself_has_no_incumbent")
        if stage_index == 0:
            return self._close("stage_zero_has_no_incumbent")
        if self.total_rollback_events >= self.max_total_rollback_events:
            return self._close("total_rollback_budget_exhausted")
        target = stage_index - MAX_ROLLBACK_DEPTH
        rejected = self.committed_records.get(target)
        if rejected is None:
            return self._close("missing_rollback_checkpoint")
        next_attempt = self.attempt_index_by_stage[target] + 1
        if next_attempt >= self.max_attempts_per_stage:
            return self._close("stage_attempt_budget_exhausted")
        self.total_rollback_events += 1
        self.attempt_index_by_stage[target] = next_attempt
        self.rollback_anchor_stage_index = stage_index
        for index in tuple(self.committed_records):
            if index >= target:
                del self.committed_records[index]
        self.current_stage_index = target
        return BacktrackingTransition(
            event="rollback_one_block",
            next_stage_index=target,
            rejected_record=rejected,
        )

    def _close(self, reason: str) -> BacktrackingTransition:
        self.terminal_status = "closed_no_checkpointed_path"
        return BacktrackingTransition(
            event=reason,
            next_stage_index=None,
            terminal_status=self.terminal_status,
        )


CaptureFunction = Callable[[object, int, int], dict[str, Any]]


def _current_block_values(
    committed: Mapping[str, int],
    prior: Mapping[str, int],
    *,
    global_names: Sequence[str],
) -> dict[str, int]:
    current_names = set(committed) - set(prior) - set(global_names)
    return {name: committed[name] for name in sorted(current_names)}


def _progress_append(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _closed_candidate_payload(
    *,
    controller: BoundedBacktrackingController,
    failed_stage_index: int,
    checkpoint_artifacts: Sequence[Mapping[str, Any]],
    no_good_specs: Sequence[NoGoodCutSpec],
    objective_restore_audit: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_id": RESULT_SCHEMA_ID,
        "status": "closed_no_checkpointed_path",
        "failed_stage_index": failed_stage_index,
        "controller_terminal_status": controller.terminal_status,
        "total_rollback_events": controller.total_rollback_events,
        "checkpoint_manifest_sha256": {
            Path(str(item["manifest_path"])).name: item["manifest_sha256"]
            for item in checkpoint_artifacts
        },
        "registered_no_good_cut_count": len(no_good_specs),
        "objective_restore_audit": dict(objective_restore_audit),
        "candidate_artifact": None,
        "formal_8784h_optimization_invoked": False,
        "formal_upper_bound_eligible": False,
    }


def solve_gate0_checkpointed_candidate(
    model: object,
    inventory: BinaryInventory,
    chp_units: Sequence[object],
    *,
    architecture: Architecture,
    guide_path: Path,
    checkpoint_dir: Path,
    progress_output_path: Path,
    physical_snapshot_output_path: Path,
    candidate_output_path: Path,
    commit_hours: int,
    time_limit_seconds: float,
    threads: int,
    require_locked_guide_hash: bool = False,
    capture_function: CaptureFunction | None = None,
) -> dict[str, Any]:
    """Run the shortened-horizon D51 Gate 0 controller and candidate lift."""

    if checkpoint_dir.exists():
        raise FileExistsError(f"D51 checkpoint directory already exists: {checkpoint_dir}")
    if progress_output_path.exists():
        raise FileExistsError(f"D51 progress output already exists: {progress_output_path}")
    partition, layout, blocks, preparation = prepare_d50_model(
        model,
        inventory,
        architecture=architecture,
        guide_path=guide_path,
        commit_hours=commit_hours,
        require_locked_guide_hash=require_locked_guide_hash,
        require_formal_counts=False,
    )
    if len(layout.periods) > MAX_GATE0_PERIODS:
        raise PermissionError("D51 Gate 0 forbids optimization beyond 840 periods")
    checkpoint_dir.mkdir(parents=True)
    objective_audit = activate_feasibility_objective(model)
    if objective_audit["passed"] is not True:
        raise ValueError("D51 feasibility objective audit failed")
    controller = BoundedBacktrackingController(stage_count=len(blocks))
    fixed_snapshot: dict[str, int] = {}
    fixed_after_stage: dict[int, dict[str, int]] = {}
    checkpoint_artifacts: list[dict[str, Any]] = []
    no_good_specs: list[NoGoodCutSpec] = []
    installed_cut_hashes: set[str] = set()
    rollback_source_hash: str | None = None

    def default_capture(current_model: object, _stage: int, _attempt: int) -> dict[str, Any]:
        return capture_first_feasibility_incumbent(
            current_model,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
        )

    capture = capture_function or default_capture
    while controller.terminal_status is None:
        stage_index = controller.current_stage_index
        attempt_index = controller.current_attempt_index
        plan = make_stage_domain_plan(
            layout,
            blocks,
            partition.projected_fuel_code_names,
            stage_index,
        )
        domain_audit = apply_stage_domain_plan(
            model,
            inventory,
            plan,
            fixed_snapshot,
        )
        if domain_audit["passed"] is not True:
            raise ValueError("D51 stage domain audit failed")
        _progress_append(
            progress_output_path,
            {
                "event": "attempt_started",
                "stage_index": stage_index,
                "attempt_index": attempt_index,
                "rollback_events": controller.total_rollback_events,
            },
        )
        captured = capture(model, stage_index, attempt_index)
        if captured.get("incumbent_captured") is not True:
            transition = controller.record_failure(stage_index)
            _progress_append(
                progress_output_path,
                {
                    "event": transition.event,
                    "stage_index": stage_index,
                    "attempt_index": attempt_index,
                    "next_stage_index": transition.next_stage_index,
                    "terminal_status": transition.terminal_status,
                },
            )
            if transition.terminal_status is not None:
                restored = restore_original_economic_objective(model, objective_audit)
                return _closed_candidate_payload(
                    controller=controller,
                    failed_stage_index=stage_index,
                    checkpoint_artifacts=checkpoint_artifacts,
                    no_good_specs=no_good_specs,
                    objective_restore_audit=restored,
                )
            rejected = transition.rejected_record
            if rejected is None:
                raise AssertionError("D51 rollback lacks a rejected checkpoint")
            spec = NoGoodCutSpec(
                stage_index=rejected.stage_index,
                block_index=blocks[rejected.stage_index].index,
                binary_values=rejected.current_block_values,
            )
            add_registered_no_good_cut(
                model,
                spec,
                existing_sha256=installed_cut_hashes,
            )
            no_good_specs.append(spec)
            rollback_source_hash = rejected.checkpoint_sha256
            target = int(transition.next_stage_index)
            fixed_snapshot = (
                dict(fixed_after_stage[target - 1]) if target > 0 else {}
            )
            for index in tuple(fixed_after_stage):
                if index >= target:
                    del fixed_after_stage[index]
            continue

        prior_snapshot = dict(fixed_snapshot)
        committed, commit_audit = commit_stage_snapshot(
            model,
            layout,
            plan,
            prior_snapshot,
        )
        if commit_audit["passed"] is not True:
            raise ValueError("D51 stage commit audit failed")
        block_values = _current_block_values(
            committed,
            prior_snapshot,
            global_names=layout.global_names,
        )
        parent_hash = (
            controller.committed_records[stage_index - 1].checkpoint_sha256
            if stage_index > 0
            else None
        )
        artifact = write_attempt_checkpoint(
            checkpoint_dir,
            architecture=architecture,
            stage_index=stage_index,
            attempt_index=attempt_index,
            parent_checkpoint_sha256=parent_hash,
            rollback_source_checkpoint_sha256=rollback_source_hash,
            fixed_snapshot_after_commit=committed,
            current_block_values=block_values,
            domain_audit=domain_audit,
            commit_audit=commit_audit,
            capture_audit=captured,
            original_constraint_identity=preparation["original_constraint_identity"],
            current_constraint_identity=constraint_identity(model),
            objective_audit=objective_audit,
            no_good_specs=no_good_specs,
            model=model,
        )
        checkpoint_artifacts.append(artifact)
        record = CommittedStageRecord(
            stage_index=stage_index,
            attempt_index=attempt_index,
            checkpoint_sha256=str(artifact["manifest_sha256"]),
            current_block_values=tuple(sorted(block_values.items())),
        )
        transition = controller.record_commit(record)
        fixed_snapshot = dict(committed)
        fixed_after_stage[stage_index] = dict(committed)
        rollback_source_hash = None
        _progress_append(
            progress_output_path,
            {
                "event": "attempt_checkpointed",
                "stage_index": stage_index,
                "attempt_index": attempt_index,
                "checkpoint_sha256": artifact["manifest_sha256"],
                "next_event": transition.event,
                "next_stage_index": transition.next_stage_index,
            },
        )

    if controller.terminal_status != "checkpointed_path_complete":
        raise AssertionError("D51 controller reached an unknown terminal state")
    physical_artifact = write_physical_snapshot(
        physical_snapshot_output_path,
        architecture=architecture,
        stage_index=len(blocks) - 1,
        stage_count=len(blocks),
        snapshot=fixed_snapshot,
    )
    objective_restore = restore_original_economic_objective(model, objective_audit)
    try:
        lift_audit = exact_lift_fuel_encoding(model, chp_units)
        if lift_audit["passed"] is not True:
            raise ValueError("D51 exact fuel lift audit failed")
        restore_binary_domains(model, inventory)
        binary_snapshot = extract_binary_snapshot(
            model,
            inventory,
            tolerance=BINARY_VALUE_TOLERANCE,
        )
    except Exception as error:  # noqa: BLE001 - canonical Gate 0 failure evidence
        return {
            "schema_id": RESULT_SCHEMA_ID,
            "status": "gate0_final_exact_lift_failed",
            "checkpoint_manifest_sha256": {
                Path(str(item["manifest_path"])).name: item["manifest_sha256"]
                for item in checkpoint_artifacts
            },
            "physical_snapshot_artifact": physical_artifact,
            "objective_restore_audit": objective_restore,
            "exact_lift_error_type": type(error).__name__,
            "exact_lift_error_message": str(error),
            "candidate_artifact": None,
            "formal_8784h_optimization_invoked": False,
            "formal_upper_bound_eligible": False,
        }
    feasibility = _bound_and_constraint_audit(model)
    service = _service_audit(model)
    passed = feasibility["passed"] and service["passed"]
    candidate_artifact = None
    status = "gate0_candidate_audit_failed"
    if passed:
        candidate_artifact = write_seed_csv_gz(
            candidate_output_path,
            _finite_model_values(model),
            binary_snapshot,
        )
        status = "gate0_checkpointed_candidate_exactly_lifted"
    return {
        "schema_id": RESULT_SCHEMA_ID,
        "status": status,
        "stage_count": len(blocks),
        "completed_stage_count": len(blocks),
        "controller_terminal_status": controller.terminal_status,
        "total_rollback_events": controller.total_rollback_events,
        "checkpoint_count": len(checkpoint_artifacts),
        "checkpoint_manifest_sha256": {
            Path(str(item["manifest_path"])).name: item["manifest_sha256"]
            for item in checkpoint_artifacts
        },
        "registered_no_good_cut_count": len(no_good_specs),
        "physical_snapshot_artifact": physical_artifact,
        "objective_restore_audit": objective_restore,
        "exact_fuel_lift_audit": lift_audit,
        "candidate_independent_feasibility_audit": feasibility,
        "candidate_service_audit": service,
        "candidate_audit_passed": passed,
        "candidate_artifact": candidate_artifact,
        "candidate_requires_original_cost_repair": True,
        "formal_8784h_optimization_invoked": False,
        "formal_upper_bound_eligible": False,
    }


def solve_d51_original_cost_repair(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Reuse the frozen D50 clean repair and mark it as Gate 0 evidence."""

    result = solve_d50_original_cost_repair(*args, **kwargs)
    result["schema_id"] = REPAIR_SCHEMA_ID
    result["gate0_shortened_horizon_only"] = True
    result["formal_8784h_optimization_invoked"] = False
    return result


def gate0_period_count_audit(period_count: int) -> dict[str, Any]:
    """Expose the non-negotiable Gate 0 horizon guard for tests and manifests."""

    if period_count <= 0:
        raise ValueError("D51 Gate 0 period count must be positive")
    permitted = period_count <= MAX_GATE0_PERIODS
    return {
        "period_count": period_count,
        "maximum_gate0_period_count": MAX_GATE0_PERIODS,
        "formal_8784h_optimization_invoked": False,
        "gate0_optimization_permitted": permitted,
        "passed": permitted,
    }
