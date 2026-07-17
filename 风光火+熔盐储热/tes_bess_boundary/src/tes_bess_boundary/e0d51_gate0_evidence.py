"""Build and compile D51 shortened-horizon Gate 0 evidence.

Only a deterministic 24-hour BESS demonstration and read-only evidence
compilation are exposed.  There is intentionally no formal-year command.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
    RelaxationMode,
    apply_relaxation,
    collect_binary_inventory,
)
from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
    _sha256,
    fix_engineering_capacity_anchor,
    solve_continuous_guide,
)
from tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix import (
    make_stage_domain_plan,
    prepare_d50_model,
)
from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
    _atomic_publish,
    _canonical_json_bytes,
    read_attempt_checkpoint,
    replay_attempt_checkpoint,
    solve_d51_original_cost_repair,
    solve_gate0_checkpointed_candidate,
)
from tes_bess_boundary.model import Architecture
from tes_bess_boundary.planning_model import (
    EndogenousCapacityCase,
    build_endogenous_capacity_model,
)


DEMONSTRATION_SCHEMA_ID = "tes_bess_boundary.e0d51_gate0_demonstration.v1"
GATE0_SCHEMA_ID = "tes_bess_boundary.e0d51_gate0_manifest.v1"
GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def build_gate0_24h_case() -> EndogenousCapacityCase:
    """Build the frozen BESS-only 24-hour control-path demonstration case."""

    from tes_bess_boundary.capacity_planning import (
        BESSPlanningBounds,
        BESSPlanningSpec,
    )
    from tes_bess_boundary.components.chp import (
        CHPCommitmentSpec,
        CHPFeasibleRegion,
        CHPFuelPoint,
        CHPUnitSpec,
        CHPVertex,
        CommitmentTransitionFormulation,
        FuelSegmentFormulation,
        HeatBasis,
        LowLoadFuelRule,
    )
    from tes_bess_boundary.economics import (
        AnnualHorizonSpec,
        PriceBasisConversion,
        ProjectFinance,
    )
    from tes_bess_boundary.formal_bess_costs import (
        build_resolved_rahman_bess_join_contract,
    )
    from tes_bess_boundary.model import (
        AnnualCurtailmentServiceSpec,
        AnnualPCCExportServiceSpec,
        E0CTimeSeries,
        ValidationObjectiveSpec,
    )

    architecture = Architecture.BESS
    chp = CHPCommitmentSpec(
        unit=CHPUnitSpec(
            name="d51_gate0_chp",
            feasible_region=CHPFeasibleRegion(
                (
                    CHPVertex(400.0, 0.0),
                    CHPVertex(700.0, 0.0),
                    CHPVertex(400.0, 100.0),
                )
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.05,
        ),
        fuel_points=(
            CHPFuelPoint(400.0, 300.0),
            CHPFuelPoint(700.0, 280.0),
        ),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
    )
    bess = BESSPlanningSpec(
        bounds=BESSPlanningBounds(2_400.0, 100.0, 100.0),
        soc_min=0.1,
        soc_max=0.9,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        initial_soc_fraction=0.5,
        cyclic=True,
    )
    bess_economics = (
        build_resolved_rahman_bess_join_contract().build_planning_economics(
            finance=ProjectFinance(project_years=20, real_discount_rate=0.10),
            conversion=PriceBasisConversion(
                source_currency="USD",
                source_price_base_year=2019,
                target_currency="CNY",
                target_price_base_year=2024,
                source_price_index=255.657,
                target_price_index=313.689,
                target_currency_per_source_currency=7.1217,
                price_index_series_id="D51 Gate 0 toy CPI",
                exchange_rate_series_id="D51 Gate 0 toy FX",
            ),
            reference_annual_ac_efc=365.0,
            ac_deliverable_fraction=0.8 * 0.95,
        )
    )
    return EndogenousCapacityCase(
        architecture=architecture,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(10.0,) * 24,
            wind_available_mw=(0.0,) * 24,
            pv_available_mw=(0.0,) * 24,
        ),
        chp_units=(chp,),
        chp_initial_online=(1,),
        chp_terminal_online=(1,),
        pcc_export_capacity_mw=700.0,
        horizon=AnnualHorizonSpec((366.0,) * 24),
        bess=bess,
        bess_economics=bess_economics,
        tes=None,
        tes_cost_portfolio=None,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=800.0,
            curtailment_penalty_cny_per_mwh=0.0,
        ),
        curtailment_service=AnnualCurtailmentServiceSpec(
            service_id="d51-gate0-curtailment",
            maximum_curtailment_mwh=339_569.90645758656,
        ),
        pcc_export_service=AnnualPCCExportServiceSpec(
            service_id="d51-gate0-export",
            target_export_mwh=4_035_354.738554194,
        ),
        chp_fuel_segment_formulation=FuelSegmentFormulation.LOGARITHMIC,
        chp_transition_formulation=CommitmentTransitionFormulation.CONTINUOUS_ENVELOPE,
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_publish(path, _canonical_json_bytes(payload))


def run_gate0_24h_demonstration(
    *,
    output_dir: Path,
    time_limit_seconds: float = 30.0,
    threads: int = 1,
) -> dict[str, Any]:
    """Run, persist and clean-replay the normative D51 24-hour Gate 0 chain."""

    if output_dir.exists():
        raise FileExistsError(f"D51 Gate 0 demonstration already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    started = perf_counter()
    case = build_gate0_24h_case()

    guide_model = build_endogenous_capacity_model(case)
    guide_inventory = collect_binary_inventory(guide_model)
    anchor = fix_engineering_capacity_anchor(guide_model, Architecture.BESS)
    relaxation = apply_relaxation(
        guide_model,
        guide_inventory,
        RelaxationMode.R0,
    )
    if anchor["passed"] is not True or relaxation["passed"] is not True:
        raise ValueError("D51 Gate 0 guide preparation failed")
    guide_path = output_dir / "guide.csv.gz"
    guide = solve_continuous_guide(
        guide_model,
        guide_inventory,
        seed_output_path=guide_path,
        time_limit_seconds=time_limit_seconds,
        threads=threads,
    )
    if guide["status"] != "continuous_guide_recovered":
        raise ValueError("D51 Gate 0 continuous guide was not recovered")

    candidate_model = build_endogenous_capacity_model(case)
    candidate_inventory = collect_binary_inventory(candidate_model)
    candidate_path = output_dir / "candidate.csv.gz"
    candidate = solve_gate0_checkpointed_candidate(
        candidate_model,
        candidate_inventory,
        case.chp_units,
        architecture=Architecture.BESS,
        guide_path=guide_path,
        checkpoint_dir=output_dir / "checkpoints",
        progress_output_path=output_dir / "progress.jsonl",
        physical_snapshot_output_path=output_dir / "physical_snapshot.json",
        candidate_output_path=candidate_path,
        commit_hours=8,
        time_limit_seconds=time_limit_seconds,
        threads=threads,
        require_locked_guide_hash=False,
    )
    _write_json(output_dir / "candidate_result.json", candidate)

    replays: list[dict[str, Any]] = []
    parent_hash: str | None = None
    checkpoint_paths = sorted((output_dir / "checkpoints").glob("stage_*.json"))
    for checkpoint_path in checkpoint_paths:
        checkpoint, _ = read_attempt_checkpoint(
            checkpoint_path,
            expected_parent_sha256=parent_hash,
        )
        replay_model = build_endogenous_capacity_model(case)
        replay_inventory = collect_binary_inventory(replay_model)
        partition, layout, blocks, _ = prepare_d50_model(
            replay_model,
            replay_inventory,
            architecture=Architecture.BESS,
            guide_path=guide_path,
            commit_hours=8,
            require_locked_guide_hash=False,
            require_formal_counts=False,
        )
        plan = make_stage_domain_plan(
            layout,
            blocks,
            partition.projected_fuel_code_names,
            int(checkpoint["stage_index"]),
        )
        replay = replay_attempt_checkpoint(
            replay_model,
            checkpoint_path,
            expected_parent_sha256=parent_hash,
            inventory=replay_inventory,
            domain_plan=plan,
        )
        replays.append(
            {
                "checkpoint": checkpoint_path.name,
                "checkpoint_manifest_sha256": _sha256(checkpoint_path),
                "replay_audit": replay,
            }
        )
        parent_hash = _sha256(checkpoint_path)

    repair = None
    if candidate["status"] == "gate0_checkpointed_candidate_exactly_lifted":
        repair_model = build_endogenous_capacity_model(case)
        repair_inventory = collect_binary_inventory(repair_model)
        repair = solve_d51_original_cost_repair(
            repair_model,
            repair_inventory,
            architecture=Architecture.BESS,
            candidate_path=candidate_path,
            solution_output_path=output_dir / "repaired_solution.csv.gz",
            time_limit_seconds=time_limit_seconds,
            threads=threads,
            require_named_constraint_groups=True,
        )
        _write_json(output_dir / "repair_result.json", repair)

    passed = all(
        (
            candidate["status"] == "gate0_checkpointed_candidate_exactly_lifted",
            candidate["candidate_audit_passed"] is True,
            candidate["checkpoint_count"] == 3,
            len(replays) == 3,
            all(item["replay_audit"]["passed"] for item in replays),
            repair is not None,
            repair is not None
            and repair["status"] == "audited_feasible_upper_bound_recovered",
        )
    )
    payload = {
        "schema_id": DEMONSTRATION_SCHEMA_ID,
        "status": (
            "gate0_24h_demonstration_passed"
            if passed
            else "gate0_24h_demonstration_failed"
        ),
        "architecture": Architecture.BESS.value,
        "period_count": 24,
        "commit_hours": 8,
        "stage_count": 3,
        "runtime_seconds": perf_counter() - started,
        "guide_status": guide["status"],
        "candidate_status": candidate["status"],
        "candidate_result_sha256": _sha256(output_dir / "candidate_result.json"),
        "checkpoint_replay_audit": replays,
        "repair_status": repair["status"] if repair else None,
        "repair_result_sha256": (
            _sha256(output_dir / "repair_result.json") if repair else None
        ),
        "formal_8784h_optimization_invoked": False,
        "formal_run_permitted": False,
        "formal_upper_bound_eligible": False,
        "audit": {"passed": passed},
    }
    _write_json(output_dir / "demonstration_result.json", payload)
    return payload


def _parse_junit(path: Path, *, no_skips: bool) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    failures = sum(bool(case.findall("failure")) for case in cases)
    errors = sum(bool(case.findall("error")) for case in cases)
    skipped = sum(bool(case.findall("skipped")) for case in cases)
    names = sorted(str(case.attrib.get("name", "")) for case in cases)
    passed = bool(cases) and failures == 0 and errors == 0
    if no_skips:
        passed = passed and skipped == 0
    return {
        "testcase_count": len(cases),
        "failure_count": failures,
        "error_count": errors,
        "skipped_count": skipped,
        "testcase_names": names,
        "file_sha256": _sha256(path),
        "passed": passed,
    }


def _code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    tests = package.parent.parent / "tests"
    paths = {
        "e0d51_checkpointed_bounded_backtracking.py": package
        / "e0d51_checkpointed_bounded_backtracking.py",
        "e0d51_gate0_evidence.py": package / "e0d51_gate0_evidence.py",
        "test_e0d51_checkpointed_bounded_backtracking.py": tests
        / "test_e0d51_checkpointed_bounded_backtracking.py",
    }
    return {name: _sha256(path) for name, path in paths.items()}


def compile_gate0_manifest(
    *,
    output_dir: Path,
    demonstration_result_path: Path,
    targeted_junit_path: Path,
    compatibility_junit_path: Path,
    full_junit_path: Path,
    ruff_log_path: Path,
    pycompile_log_path: Path,
    git_commit: str,
) -> dict[str, Any]:
    """Compile same-commit Linux Gate 0 evidence without running a solver."""

    if GIT_COMMIT_PATTERN.fullmatch(git_commit) is None:
        raise ValueError("D51 Gate 0 requires a full lowercase Git commit")
    manifest_path = output_dir / "gate0_manifest.json"
    execution_path = output_dir / "gate0_execution.json"
    if manifest_path.exists() or execution_path.exists():
        raise FileExistsError("D51 Gate 0 manifest already exists")
    demonstration = json.loads(
        demonstration_result_path.read_text(encoding="utf-8")
    )
    if demonstration.get("schema_id") != DEMONSTRATION_SCHEMA_ID:
        raise ValueError("D51 Gate 0 demonstration schema mismatch")
    if demonstration.get("status") != "gate0_24h_demonstration_passed":
        raise ValueError("D51 Gate 0 demonstration did not pass")
    if demonstration.get("formal_8784h_optimization_invoked") is not False:
        raise ValueError("D51 Gate 0 demonstration invoked formal optimization")
    tests = {
        "d51_targeted": _parse_junit(targeted_junit_path, no_skips=True),
        "d40_d51_compatibility": _parse_junit(
            compatibility_junit_path,
            no_skips=True,
        ),
        "full_package": _parse_junit(full_junit_path, no_skips=True),
    }
    required_targeted = {
        "test_state_machine_recovers_one_forced_dead_end",
        "test_atomic_checkpoint_round_trip_and_clean_replay",
        "test_24h_checkpointed_path_lifts_and_repairs_original_cost",
    }
    if not required_targeted.issubset(tests["d51_targeted"]["testcase_names"]):
        raise ValueError("D51 Gate 0 targeted JUnit lacks required tests")
    if not all(item["passed"] for item in tests.values()):
        raise ValueError("D51 Gate 0 test evidence failed")
    quality = {
        "ruff": {
            "sentinel_present": "D51_RUFF_PASSED"
            in ruff_log_path.read_text(encoding="utf-8"),
            "file_sha256": _sha256(ruff_log_path),
        },
        "pycompile": {
            "sentinel_present": "D51_PYCOMPILE_PASSED"
            in pycompile_log_path.read_text(encoding="utf-8"),
            "file_sha256": _sha256(pycompile_log_path),
        },
    }
    if not all(item["sentinel_present"] for item in quality.values()):
        raise ValueError("D51 Gate 0 quality sentinel is missing")
    started = perf_counter()
    artifact_hashes = {
        str(path.relative_to(output_dir)).replace("\\", "/"): _sha256(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file()
        and path not in {manifest_path, execution_path}
    }
    payload = {
        "schema_id": GATE0_SCHEMA_ID,
        "status": "gate0_controller_validated",
        "git_commit": git_commit,
        "code_sha256": _code_hashes(),
        "demonstration_result_sha256": _sha256(demonstration_result_path),
        "test_evidence": tests,
        "quality_evidence": quality,
        "artifact_sha256": artifact_hashes,
        "formal_8784h_optimization_invoked": False,
        "formal_run_permitted": False,
        "formal_capacity_or_upper_bound_available": False,
        "technical_ranking_permitted": False,
        "audit": {"passed": True},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(manifest_path, payload)
    _write_json(
        execution_path,
        {
            "schema_id": f"{GATE0_SCHEMA_ID}.execution",
            "status": "complete",
            "runtime_seconds": perf_counter() - started,
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "manifest_sha256": _sha256(manifest_path),
        },
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demonstration = commands.add_parser("demonstration-24h")
    demonstration.add_argument("--output-dir", type=Path, required=True)
    demonstration.add_argument("--time-limit", type=float, default=30.0)
    demonstration.add_argument("--threads", type=int, default=1)
    compile_gate = commands.add_parser("compile-gate0")
    compile_gate.add_argument("--output-dir", type=Path, required=True)
    compile_gate.add_argument("--demonstration-result", type=Path, required=True)
    compile_gate.add_argument("--targeted-junit", type=Path, required=True)
    compile_gate.add_argument("--compatibility-junit", type=Path, required=True)
    compile_gate.add_argument("--full-junit", type=Path, required=True)
    compile_gate.add_argument("--ruff-log", type=Path, required=True)
    compile_gate.add_argument("--pycompile-log", type=Path, required=True)
    compile_gate.add_argument("--git-commit", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "demonstration-24h":
        run_gate0_24h_demonstration(
            output_dir=args.output_dir,
            time_limit_seconds=args.time_limit,
            threads=args.threads,
        )
        return
    if args.command == "compile-gate0":
        compile_gate0_manifest(
            output_dir=args.output_dir,
            demonstration_result_path=args.demonstration_result,
            targeted_junit_path=args.targeted_junit,
            compatibility_junit_path=args.compatibility_junit,
            full_junit_path=args.full_junit,
            ruff_log_path=args.ruff_log,
            pycompile_log_path=args.pycompile_log,
            git_commit=args.git_commit,
        )
        return
    raise AssertionError(f"unhandled D51 Gate 0 command: {args.command}")


if __name__ == "__main__":
    main()
