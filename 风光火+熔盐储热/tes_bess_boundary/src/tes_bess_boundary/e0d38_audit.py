"""Audit a complete E0-D-38-R1 result bundle against the frozen gates.

The audit is deliberately downstream of the optimization model.  It reads the
restartable case JSON files, checks their identities and service/provenance
signatures, and evaluates only the thresholds preregistered in the D38
contract.  It does not reinterpret an incomplete solve as a scientific result.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_ID = "tes_bess_boundary.e0d38_bundle_audit.v1"
CASE_SCHEMA_ID = "tes_bess_boundary.e0d38_case_result.v1"
STATES = ("baseline", "high_heat_tight_pcc_r1", "long_duration_24h")
ARCHITECTURES = ("no_storage", "bess", "tes", "hybrid")
STORAGE_ARCHITECTURES = ("bess", "tes", "hybrid")
PHASES = (
    "representative_planning",
    "full_year_fixed",
    "full_year_reoptimization",
)

MIP_GAP_LIMIT = 0.001
SERVICE_TOLERANCE_MWH = 0.001
COST_REPLAY_ERROR_LIMIT = 0.03
CURTAILMENT_RATE_ERROR_LIMIT = 0.01
FUEL_ERROR_LIMIT = 0.03
COST_REGRET_LIMIT = 0.02
CAPACITY_ERROR_LIMIT = 0.10
ECONOMIC_INDIFFERENCE_BAND = 0.05

CAPACITY_FIELDS = (
    "bess_energy_capacity_mwh",
    "bess_charge_power_capacity_mw",
    "bess_discharge_power_capacity_mw",
    "bess_common_pcs_power_capacity_mw",
    "tes_salt_mass_t",
    "tes_ht_tank_capacity_t",
    "tes_mt_tank_capacity_t",
    "tes_lt_tank_capacity_t",
    "tes_ht_service_salt_mass_t",
    "tes_mt_service_salt_mass_t",
    "tes_electric_charge_input_capacity_mw",
    "tes_steam_to_ht_input_capacity_mw",
    "tes_steam_to_mt_input_capacity_mw",
    "tes_electric_output_capacity_mw",
    "tes_heat_output_capacity_mw",
)

INSTALLATION_FIELDS = (
    "bess_installation_binary",
    "tes_installation_binary",
    "tes_electric_charge_installation_binary",
    "tes_steam_to_ht_installation_binary",
    "tes_steam_to_mt_installation_binary",
    "tes_electric_output_installation_binary",
    "tes_heat_output_installation_binary",
)


def _case_path(
    result_dir: Path,
    state: str,
    phase: str,
    architecture: str,
) -> Path:
    return result_dir / f"case_{state}_{phase}_{architecture}.json"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"result is not a JSON object: {path}")
    return payload


def _finite_number(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} is not numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} is not finite")
    return number


def _relative_error(value: float, reference: float) -> float:
    return abs(value - reference) / max(abs(reference), 1e-9)


def _result_metric(payload: dict[str, Any], name: str) -> float:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("complete case lacks a result object")
    return _finite_number(result.get(name), name=name)


def _validate_identity(
    payload: dict[str, Any],
    *,
    state: str,
    phase: str,
    architecture: str,
) -> list[str]:
    failures: list[str] = []
    expected = {
        "schema_id": CASE_SCHEMA_ID,
        "phase": phase,
        "architecture": architecture,
        "formal_project_tac_ready": False,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            failures.append(f"{key}_mismatch")
    state_payload = payload.get("state")
    if not isinstance(state_payload, dict) or state_payload.get("state_id") != state:
        failures.append("state_id_mismatch")
    return failures


def _validate_complete_case(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    try:
        gap = _result_metric(payload, "relative_mip_gap")
        if gap > MIP_GAP_LIMIT + 1e-12:
            failures.append("mip_gap_exceeds_0.1_percent")
        service = payload.get("service_audit")
        if not isinstance(service, dict):
            failures.append("service_audit_missing")
            return failures
        pcc_residual = _finite_number(
            service.get("pcc_export_residual_mwh"),
            name="pcc_export_residual_mwh",
        )
        curtailment_slack = _finite_number(
            service.get("curtailment_ceiling_slack_mwh"),
            name="curtailment_ceiling_slack_mwh",
        )
        if abs(pcc_residual) > SERVICE_TOLERANCE_MWH + 1e-9:
            failures.append("pcc_service_residual_exceeds_1e-3_mwh")
        if curtailment_slack < -SERVICE_TOLERANCE_MWH - 1e-9:
            failures.append("curtailment_service_violation_exceeds_1e-3_mwh")
    except ValueError as error:
        failures.append(f"invalid_complete_case:{error}")
    return failures


def _capacity_audit(
    representative: dict[str, Any],
    reoptimized: dict[str, Any],
) -> dict[str, Any]:
    representative_snapshot = representative.get("capacity_snapshot")
    reoptimized_snapshot = reoptimized.get("capacity_snapshot")
    if not isinstance(representative_snapshot, dict) or not isinstance(
        reoptimized_snapshot, dict
    ):
        return {
            "status": "failed",
            "failures": ["capacity_snapshot_missing"],
        }

    field_errors: dict[str, float] = {}
    failures: list[str] = []
    for field in CAPACITY_FIELDS:
        representative_value = representative_snapshot.get(field)
        reoptimized_value = reoptimized_snapshot.get(field)
        if representative_value is None and reoptimized_value is None:
            continue
        try:
            field_errors[field] = _relative_error(
                _finite_number(representative_value, name=field),
                _finite_number(reoptimized_value, name=field),
            )
        except ValueError as error:
            failures.append(f"invalid_capacity:{error}")

    installation_mismatches: list[str] = []
    for field in INSTALLATION_FIELDS:
        representative_value = representative_snapshot.get(field)
        reoptimized_value = reoptimized_snapshot.get(field)
        if representative_value is None and reoptimized_value is None:
            continue
        try:
            difference = abs(
                _finite_number(representative_value, name=field)
                - _finite_number(reoptimized_value, name=field)
            )
            if difference > 1e-6:
                installation_mismatches.append(field)
        except ValueError as error:
            failures.append(f"invalid_installation_state:{error}")

    maximum_error = max(field_errors.values(), default=0.0)
    return {
        "status": "failed" if failures else "complete",
        "maximum_relative_capacity_error": maximum_error,
        "fields_exceeding_10_percent": sorted(
            field for field, error in field_errors.items() if error > 0.10 + 1e-12
        ),
        "installation_state_mismatches": installation_mismatches,
        "field_relative_errors": field_errors,
        "failures": failures,
    }


def _audit_architecture(
    *,
    state: str,
    architecture: str,
    cases: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    representative = cases["representative_planning"]
    fixed = cases["full_year_fixed"]
    reoptimized = (
        fixed
        if architecture == "no_storage"
        else cases["full_year_reoptimization"]
    )
    statuses = {
        "representative_planning": representative.get("status"),
        "full_year_fixed": fixed.get("status"),
        "full_year_reoptimization": reoptimized.get("status"),
    }
    failures: list[str] = []
    for phase, payload in (
        ("representative_planning", representative),
        ("full_year_fixed", fixed),
        ("full_year_reoptimization", reoptimized),
    ):
        failures.extend(
            f"{phase}:{failure}"
            for failure in _validate_identity(
                payload,
                state=state,
                phase=("full_year_fixed" if architecture == "no_storage" else phase),
                architecture=architecture,
            )
        )
        if payload.get("status") == "complete":
            failures.extend(
                f"{phase}:{failure}"
                for failure in _validate_complete_case(payload)
            )

    if architecture == "no_storage" and all(
        status == "infeasible" for status in statuses.values()
    ):
        return {
            "status": "consistent_infeasible",
            "phase_statuses": statuses,
            "failures": failures,
        }
    if any(status != "complete" for status in statuses.values()):
        failures.append("representative_full_year_feasibility_mismatch_or_failure")
        return {
            "status": "failed",
            "phase_statuses": statuses,
            "failures": failures,
        }

    try:
        representative_cost = _result_metric(
            representative, "annual_total_cost_cny"
        )
        fixed_cost = _result_metric(fixed, "annual_total_cost_cny")
        reoptimized_cost = _result_metric(reoptimized, "annual_total_cost_cny")
        representative_fuel = _result_metric(representative, "weighted_fuel_tce")
        fixed_fuel = _result_metric(fixed, "weighted_fuel_tce")
        representative_curtailment_rate = _finite_number(
            representative["service_audit"].get(
                "curtailment_rate_on_actual_availability"
            ),
            name="representative_curtailment_rate",
        )
        fixed_curtailment_rate = _finite_number(
            fixed["service_audit"].get("curtailment_rate_on_actual_availability"),
            name="fixed_curtailment_rate",
        )
    except (KeyError, ValueError) as error:
        failures.append(f"invalid_comparison_metric:{error}")
        return {
            "status": "failed",
            "phase_statuses": statuses,
            "failures": failures,
        }

    cost_replay_error = _relative_error(fixed_cost, representative_cost)
    curtailment_rate_error = abs(
        fixed_curtailment_rate - representative_curtailment_rate
    )
    fuel_error = _relative_error(representative_fuel, fixed_fuel)
    cost_regret = (fixed_cost - reoptimized_cost) / max(
        abs(reoptimized_cost), 1e-9
    )
    if cost_replay_error > COST_REPLAY_ERROR_LIMIT + 1e-12:
        failures.append("fixed_full_year_cost_error_exceeds_3_percent")
    if curtailment_rate_error > CURTAILMENT_RATE_ERROR_LIMIT + 1e-12:
        failures.append("curtailment_rate_error_exceeds_1_percentage_point")
    if fuel_error > FUEL_ERROR_LIMIT + 1e-12:
        failures.append("fuel_error_exceeds_3_percent")
    if cost_regret > COST_REGRET_LIMIT + 1e-12:
        failures.append("cost_regret_exceeds_2_percent")

    capacity = _capacity_audit(representative, reoptimized)
    if capacity["status"] == "failed":
        failures.extend(capacity["failures"])
    capacity_outside_band = bool(
        capacity["fields_exceeding_10_percent"]
        or capacity["installation_state_mismatches"]
    )
    flat_optimum = capacity_outside_band and cost_regret <= COST_REGRET_LIMIT + 1e-12
    if capacity_outside_band and not flat_optimum:
        failures.append("capacity_error_exceeds_10_percent_without_flat_optimum")

    return {
        "status": "passed" if not failures else "failed",
        "phase_statuses": statuses,
        "representative_cost_cny": representative_cost,
        "fixed_full_year_cost_cny": fixed_cost,
        "reoptimized_full_year_cost_cny": reoptimized_cost,
        "fixed_full_year_cost_error_fraction": cost_replay_error,
        "curtailment_rate_absolute_error": curtailment_rate_error,
        "fuel_relative_error": fuel_error,
        "cost_regret_fraction": cost_regret,
        "capacity_audit": capacity,
        "flat_optimum_region": flat_optimum,
        "failures": failures,
    }


def audit_result_bundle(result_dir: Path) -> dict[str, Any]:
    """Audit the canonical three-state D38-R1 result directory."""

    missing_files: list[str] = []
    cases: dict[tuple[str, str, str], dict[str, Any]] = {}
    for state in STATES:
        for architecture in ARCHITECTURES:
            required_phases = (
                PHASES[:2] if architecture == "no_storage" else PHASES
            )
            for phase in required_phases:
                path = _case_path(result_dir, state, phase, architecture)
                if not path.is_file():
                    missing_files.append(path.name)
                    continue
                cases[(state, architecture, phase)] = _read_json(path)

    base_payload: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "claim_scope": "temporal_aggregation_prevalidation_not_formal_project_tac",
        "formal_project_tac_ready": False,
        "thresholds": {
            "mip_relative_gap": MIP_GAP_LIMIT,
            "service_tolerance_mwh": SERVICE_TOLERANCE_MWH,
            "fixed_full_year_cost_error_fraction": COST_REPLAY_ERROR_LIMIT,
            "curtailment_rate_absolute_error": CURTAILMENT_RATE_ERROR_LIMIT,
            "fuel_relative_error": FUEL_ERROR_LIMIT,
            "cost_regret_fraction": COST_REGRET_LIMIT,
            "capacity_relative_error": CAPACITY_ERROR_LIMIT,
            "representative_economic_indifference_band": (
                ECONOMIC_INDIFFERENCE_BAND
            ),
        },
        "missing_files": sorted(missing_files),
    }
    if missing_files:
        return {**base_payload, "status": "incomplete", "state_audits": {}}

    state_audits: dict[str, Any] = {}
    overall_failures: list[str] = []
    provenance_signatures: set[str] = set()
    for state in STATES:
        architecture_audits: dict[str, Any] = {}
        representative_costs: dict[str, float] = {}
        full_year_costs: dict[str, float] = {}
        service_hashes: set[str] = set()
        for architecture in ARCHITECTURES:
            architecture_cases = {
                phase: cases[(state, architecture, phase)]
                for phase in (
                    PHASES[:2] if architecture == "no_storage" else PHASES
                )
            }
            audit = _audit_architecture(
                state=state,
                architecture=architecture,
                cases=architecture_cases,
            )
            architecture_audits[architecture] = audit
            if audit["status"] == "failed":
                overall_failures.append(f"{state}:{architecture}")
            if audit["status"] == "passed":
                representative_costs[architecture] = audit[
                    "representative_cost_cny"
                ]
                full_year_costs[architecture] = audit[
                    "reoptimized_full_year_cost_cny"
                ]
            for payload in architecture_cases.values():
                service_hash = payload.get("service_contract_sha256")
                if isinstance(service_hash, str):
                    service_hashes.add(service_hash)
                provenance = payload.get("provenance")
                if isinstance(provenance, dict):
                    provenance_signatures.add(
                        json.dumps(provenance, sort_keys=True, ensure_ascii=False)
                    )

        ranking: dict[str, Any]
        if representative_costs and full_year_costs:
            representative_minimum = min(representative_costs.values())
            indifference_set = sorted(
                architecture
                for architecture, cost in representative_costs.items()
                if cost
                <= (1.0 + ECONOMIC_INDIFFERENCE_BAND) * representative_minimum
            )
            full_year_winner = min(full_year_costs, key=full_year_costs.__getitem__)
            ranking_passed = full_year_winner in indifference_set
            ranking = {
                "status": "passed" if ranking_passed else "failed",
                "representative_5_percent_indifference_set": indifference_set,
                "full_year_proxy_cost_winner": full_year_winner,
            }
            if not ranking_passed:
                overall_failures.append(f"{state}:ranking")
        else:
            ranking = {
                "status": "failed",
                "failure": "no_complete_architecture_costs_for_ranking",
            }
            overall_failures.append(f"{state}:ranking")
        if len(service_hashes) != 1:
            overall_failures.append(f"{state}:service_contract_hash_mismatch")
        state_audits[state] = {
            "architectures": architecture_audits,
            "ranking_audit": ranking,
            "service_contract_sha256": (
                next(iter(service_hashes)) if len(service_hashes) == 1 else None
            ),
        }

    if len(provenance_signatures) != 1:
        overall_failures.append("cross_bundle_provenance_mismatch")
    return {
        **base_payload,
        "status": "passed" if not overall_failures else "failed",
        "state_audits": state_audits,
        "failures": sorted(set(overall_failures)),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = audit_result_bundle(args.result_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
