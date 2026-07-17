from __future__ import annotations

import json
import hashlib
from pathlib import Path

from tes_bess_boundary.e0d38_audit import (
    ARCHITECTURES,
    PHASES,
    STATES,
    audit_result_bundle,
)


def _case_payload(
    *,
    state: str,
    architecture: str,
    phase: str,
    cost: float = 100.0,
    fuel: float = 100.0,
    curtailment_rate: float = 0.10,
    capacity: float = 10.0,
    status: str = "complete",
    service_sha256: str = "",
) -> dict:
    payload = {
        "schema_id": "tes_bess_boundary.e0d38_case_result.v1",
        "state": {"state_id": state},
        "phase": phase,
        "architecture": architecture,
        "status": status,
        "formal_project_tac_ready": False,
        "service_contract_sha256": service_sha256,
        "provenance": {"input": "same"},
    }
    if status == "complete":
        payload.update(
            {
                "result": {
                    "relative_mip_gap": 0.0005,
                    "annual_total_cost_cny": cost,
                    "weighted_fuel_tce": fuel,
                },
                "service_audit": {
                    "pcc_export_residual_mwh": 0.0,
                    "curtailment_ceiling_slack_mwh": 1.0,
                    "curtailment_rate_on_actual_availability": curtailment_rate,
                },
                "capacity_snapshot": {
                    "architecture": architecture,
                    "bess_energy_capacity_mwh": (
                        capacity if architecture in {"bess", "hybrid"} else None
                    ),
                    "bess_installation_binary": (
                        1.0 if architecture in {"bess", "hybrid"} else None
                    ),
                    "tes_salt_mass_t": (
                        capacity if architecture in {"tes", "hybrid"} else None
                    ),
                    "tes_installation_binary": (
                        1.0 if architecture in {"tes", "hybrid"} else None
                    ),
                },
            }
        )
    return payload


def _write_bundle(result_dir: Path) -> None:
    service_hashes: dict[str, str] = {}
    for name in ("service_baseline.json", "service_high_heat_tight_pcc_r1.json"):
        service = {
            "schema_id": "tes_bess_boundary.e0d38_service_contract.v1",
            "status": "complete",
            "formal_project_tac_ready": False,
            "provenance": {"input": "same"},
        }
        path = result_dir / name
        path.write_text(json.dumps(service), encoding="utf-8")
        service_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for state in STATES:
        service_name = (
            "service_high_heat_tight_pcc_r1.json"
            if state == "high_heat_tight_pcc_r1"
            else "service_baseline.json"
        )
        for architecture in ARCHITECTURES:
            phases = PHASES[:2] if architecture == "no_storage" else PHASES
            for phase in phases:
                status = "infeasible" if architecture == "no_storage" else "complete"
                payload = _case_payload(
                    state=state,
                    architecture=architecture,
                    phase=phase,
                    cost={"bess": 100.0, "tes": 102.0, "hybrid": 103.0}.get(
                        architecture, 110.0
                    ),
                    status=status,
                    service_sha256=service_hashes[service_name],
                )
                path = result_dir / f"case_{state}_{phase}_{architecture}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")


def test_complete_consistent_bundle_passes(tmp_path: Path) -> None:
    _write_bundle(tmp_path)

    audit = audit_result_bundle(tmp_path)

    assert audit["status"] == "passed"
    assert not audit["missing_files"]
    for state in STATES:
        state_audit = audit["state_audits"][state]
        assert (
            state_audit["architectures"]["no_storage"]["status"]
            == "consistent_infeasible"
        )
        assert state_audit["ranking_audit"]["status"] == "passed"


def test_capacity_difference_is_flat_optimum_when_regret_is_small(
    tmp_path: Path,
) -> None:
    _write_bundle(tmp_path)
    representative_path = (
        tmp_path / "case_baseline_representative_planning_bess.json"
    )
    representative = json.loads(representative_path.read_text(encoding="utf-8"))
    representative["capacity_snapshot"]["bess_energy_capacity_mwh"] = 20.0
    representative_path.write_text(json.dumps(representative), encoding="utf-8")

    audit = audit_result_bundle(tmp_path)

    bess_audit = audit["state_audits"]["baseline"]["architectures"]["bess"]
    assert bess_audit["status"] == "passed"
    assert bess_audit["flat_optimum_region"] is True
    assert (
        "bess_energy_capacity_mwh"
        in bess_audit["capacity_audit"]["fields_exceeding_10_percent"]
    )


def test_missing_case_keeps_bundle_incomplete(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    missing = tmp_path / "case_baseline_full_year_fixed_bess.json"
    missing.unlink()

    audit = audit_result_bundle(tmp_path)

    assert audit["status"] == "incomplete"
    assert missing.name in audit["missing_files"]


def test_service_case_code_provenance_mismatch_fails_bundle(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    path = tmp_path / "service_baseline.json"
    service = json.loads(path.read_text(encoding="utf-8"))
    service["provenance"]["code"] = "stale"
    path.write_text(json.dumps(service), encoding="utf-8")

    audit = audit_result_bundle(tmp_path)

    assert audit["status"] == "failed"
    assert "baseline:service_integrity" in audit["failures"]
    assert audit["state_audits"]["baseline"]["service_integrity_failures"]
