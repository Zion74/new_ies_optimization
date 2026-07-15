"""E0-D-40 full-year-first build and resource gate.

This module deliberately separates deterministic scientific manifests from
platform-dependent execution metadata.  Gate A only builds and audits models;
it never creates or invokes a solver.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

from tes_bess_boundary.e0d17_exploration import COAL_PRICE_CNY_PER_TCE
from tes_bess_boundary.e0d38_prevalidation import (
    build_d38_case,
    load_full_year_input,
    planning_inputs_for_state,
    state_spec,
)
from tes_bess_boundary.model import (
    AnnualCurtailmentServiceSpec,
    AnnualPCCExportServiceSpec,
    Architecture,
    ValidationObjectiveSpec,
)
from tes_bess_boundary.planning_model import build_endogenous_capacity_model


SERVICE_SCHEMA_ID = "tes_bess_boundary.e0d40_full_year_service.v1"
BUILD_SCHEMA_ID = "tes_bess_boundary.e0d40_full_year_build_audit.v1"
GATE_A_SCHEMA_ID = "tes_bess_boundary.e0d40_gate_a_manifest.v1"
CLAIM_SCOPE = "controlled_public_cost_sensitivity_not_formal_project_tac"
FORMAL_PROJECT_TAC_READY = False

SERVICE_NAME = "e0d40_full_year_service.json"
SERVICE_EXECUTION_NAME = "service_execution.json"
GATE_A_MANIFEST_NAME = "gate_a_manifest.json"
GATE_A_EXECUTION_NAME = "gate_a_execution.json"

FORMAL_HEAT_SHA256 = (
    "a89d3654600eac53768529ad9ef6d304b7d756783359fc1f1db95fd2bd4c709e"
)
LEGACY_VRE_SHA256 = (
    "515892a944dacf75c4bae3f41f008b01924f30dbd9b004d132afbdb7c0e25b6f"
)
PRICE_BASIS_TREE_SHA256 = (
    "a01eb224bccbf27fdf61d11fe440a73ce45ef085f6973da6b07146be2d704cb3"
)
D38_BASELINE_SERVICE_SHA256 = (
    "93f3d7b5c50312d08ea3dd78b1af70661facf880fcc882b1bb1ac32a783977b3"
)
D39_GATE_B_RESULT_SHA256 = (
    "47f33db2d3a00bbe5f70cd342198fd5daa1538663c49b8ec7d39641fd27b645b"
)

ACTUAL_RENEWABLE_AVAILABLE_MWH = 3_395_699.0645758654
EPSILON_CURTAILMENT_FRACTION = 0.10
EPSILON_CURTAILMENT_CEILING_MWH = 339_569.90645758656
PCC_EXPORT_TARGET_MWH = 4_035_354.738554194
ACTUAL_MINIMUM_CURTAILMENT_MWH = 565_916.1220067485

FULL_YEAR_HOURS = 8_784
EXPECTED_BLOCK_COUNT = 1
EXPECTED_STATE_NODES_PER_STORAGE = FULL_YEAR_HOURS + EXPECTED_BLOCK_COUNT
BUILD_PEAK_RSS_LIMIT_GIB = 20.0
BUILD_MIN_AVAILABLE_MEMORY_GIB = 40.0

ARCHITECTURES = (
    Architecture.NO_STORAGE,
    Architecture.BESS,
    Architecture.TES,
    Architecture.HYBRID,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(directory: Path) -> str:
    digest = hashlib.sha256()
    files = tuple(sorted(path for path in directory.rglob("*") if path.is_file()))
    if not files:
        raise ValueError(f"hash input directory is empty: {directory}")
    for path in files:
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_json_bytes(payload))
    temporary.replace(path)


def _require_close(actual: object, expected: float, name: str) -> None:
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(float(actual)) or not math.isclose(
        float(actual), expected, rel_tol=0.0, abs_tol=1e-9
    ):
        raise ValueError(f"{name} mismatch")


def _code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    names = (
        "e0d40_full_year_compute_gate.py",
        "e0d38_prevalidation.py",
        "e0d37_block_horizon.py",
        "planning_model.py",
        "capacity_planning.py",
        "model.py",
    )
    return {name: _sha256(package / name) for name in names}


def _input_hashes(
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, str]:
    hashes = {
        "heat_file_sha256": _sha256(heat_path),
        "vre_file_sha256": _sha256(vre_path),
        "price_basis_tree_sha256": _tree_sha256(price_basis_path),
    }
    expected = {
        "heat_file_sha256": FORMAL_HEAT_SHA256,
        "vre_file_sha256": LEGACY_VRE_SHA256,
        "price_basis_tree_sha256": PRICE_BASIS_TREE_SHA256,
    }
    for key, expected_hash in expected.items():
        if hashes[key] != expected_hash:
            raise ValueError(f"D40 {key} mismatch")
    return hashes


def build_full_year_service_payload(
    source_service_path: Path,
    d39_gate_b_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    """Extract a representative-period-free service contract from frozen evidence."""

    if _sha256(source_service_path) != D38_BASELINE_SERVICE_SHA256:
        raise ValueError("D40 source D38 baseline service hash mismatch")
    if _sha256(d39_gate_b_path) != D39_GATE_B_RESULT_SHA256:
        raise ValueError("D40 D39 Gate B result hash mismatch")
    source = json.loads(source_service_path.read_text(encoding="utf-8"))
    d39 = json.loads(d39_gate_b_path.read_text(encoding="utf-8"))
    if source.get("schema_id") != "tes_bess_boundary.e0d38_service_contract.v1":
        raise ValueError("D40 source service schema mismatch")
    if source.get("status") != "complete":
        raise ValueError("D40 source service is incomplete")
    state = source.get("state")
    if not isinstance(state, dict) or state.get("state_id") != "baseline":
        raise ValueError("D40 source service is not baseline")
    _require_close(state.get("heat_scale"), 1.0, "source heat scale")
    _require_close(
        state.get("pcc_export_capacity_mw"),
        700.0,
        "source PCC capacity",
    )
    _require_close(
        source.get("actual_renewable_available_mwh"),
        ACTUAL_RENEWABLE_AVAILABLE_MWH,
        "actual renewable availability",
    )
    _require_close(
        source.get("epsilon_curtailment_ceiling_mwh"),
        EPSILON_CURTAILMENT_CEILING_MWH,
        "epsilon curtailment ceiling",
    )
    _require_close(
        source.get("pcc_export_target_mwh"),
        PCC_EXPORT_TARGET_MWH,
        "PCC export target",
    )
    if source.get("formal_project_tac_ready") is not False:
        raise ValueError("D40 source service claim scope mismatch")
    source_provenance = source.get("provenance")
    if not isinstance(source_provenance, dict):
        raise ValueError("D40 source service lacks provenance")
    for key, expected_hash in (
        ("actual_heat_file_sha256", FORMAL_HEAT_SHA256),
        ("actual_vre_file_sha256", LEGACY_VRE_SHA256),
        ("price_basis_tree_sha256", PRICE_BASIS_TREE_SHA256),
    ):
        if source_provenance.get(key) != expected_hash:
            raise ValueError(f"D40 source service {key} mismatch")

    gate = d39.get("minimum_curtailment_prevalidation_gate")
    if d39.get("status") != "complete" or not isinstance(gate, dict):
        raise ValueError("D40 D39 Gate B evidence is incomplete")
    if gate.get("passed") is not False:
        raise ValueError("D40 requires the frozen failed D39 Gate B evidence")
    _require_close(
        d39.get("actual_minimum_curtailment_mwh"),
        ACTUAL_MINIMUM_CURTAILMENT_MWH,
        "D39 actual minimum curtailment",
    )
    _require_close(
        d39.get("actual_renewable_available_mwh"),
        ACTUAL_RENEWABLE_AVAILABLE_MWH,
        "D39 actual renewable availability",
    )
    _require_close(
        d39.get("epsilon_10_percent_ceiling_mwh"),
        EPSILON_CURTAILMENT_CEILING_MWH,
        "D39 epsilon ceiling",
    )
    d39_provenance = d39.get("provenance")
    if not isinstance(d39_provenance, dict):
        raise ValueError("D40 D39 Gate B evidence lacks provenance")
    if d39_provenance.get("heat_file_sha256") != FORMAL_HEAT_SHA256:
        raise ValueError("D40 D39 heat hash mismatch")
    if d39_provenance.get("vre_file_sha256") != LEGACY_VRE_SHA256:
        raise ValueError("D40 D39 VRE hash mismatch")

    return {
        "schema_id": SERVICE_SCHEMA_ID,
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "representative_period_input_used": False,
        "state": {
            "state_id": "baseline",
            "physical_service_key": "baseline_heat_pcc700",
            "heat_scale": 1.0,
            "pcc_export_capacity_mw": 700.0,
        },
        "actual_renewable_available_mwh": ACTUAL_RENEWABLE_AVAILABLE_MWH,
        "epsilon_curtailment_fraction": EPSILON_CURTAILMENT_FRACTION,
        "epsilon_curtailment_ceiling_mwh": EPSILON_CURTAILMENT_CEILING_MWH,
        "pcc_export_target_mwh": PCC_EXPORT_TARGET_MWH,
        "actual_no_storage_minimum_curtailment_mwh": (
            ACTUAL_MINIMUM_CURTAILMENT_MWH
        ),
        "source_evidence": {
            "d38_baseline_service_sha256": D38_BASELINE_SERVICE_SHA256,
            "d39_gate_b_result_sha256": D39_GATE_B_RESULT_SHA256,
            "d39_gate_b_passed": False,
        },
        "provenance": {
            **_input_hashes(heat_path, vre_path, price_basis_path),
            "code_sha256": _code_hashes(),
        },
    }


def load_full_year_service(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_id") != SERVICE_SCHEMA_ID:
        raise ValueError("D40 service schema mismatch")
    if payload.get("claim_scope") != CLAIM_SCOPE:
        raise ValueError("D40 service claim scope mismatch")
    if payload.get("formal_project_tac_ready") is not False:
        raise ValueError("D40 service cannot be formal project TAC")
    if payload.get("representative_period_input_used") is not False:
        raise ValueError("D40 service must not use representative periods")
    state = payload.get("state")
    if not isinstance(state, dict) or state != {
        "state_id": "baseline",
        "physical_service_key": "baseline_heat_pcc700",
        "heat_scale": 1.0,
        "pcc_export_capacity_mw": 700.0,
    }:
        raise ValueError("D40 service state mismatch")
    for key, expected in (
        ("actual_renewable_available_mwh", ACTUAL_RENEWABLE_AVAILABLE_MWH),
        ("epsilon_curtailment_fraction", EPSILON_CURTAILMENT_FRACTION),
        ("epsilon_curtailment_ceiling_mwh", EPSILON_CURTAILMENT_CEILING_MWH),
        ("pcc_export_target_mwh", PCC_EXPORT_TARGET_MWH),
        (
            "actual_no_storage_minimum_curtailment_mwh",
            ACTUAL_MINIMUM_CURTAILMENT_MWH,
        ),
    ):
        _require_close(payload.get(key), expected, key)
    if payload.get("source_evidence") != {
        "d38_baseline_service_sha256": D38_BASELINE_SERVICE_SHA256,
        "d39_gate_b_result_sha256": D39_GATE_B_RESULT_SHA256,
        "d39_gate_b_passed": False,
    }:
        raise ValueError("D40 service source evidence mismatch")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("D40 service lacks provenance")
    if set(provenance) != {
        "heat_file_sha256",
        "vre_file_sha256",
        "price_basis_tree_sha256",
        "code_sha256",
    }:
        raise ValueError("D40 service contains unregistered provenance fields")
    if provenance.get("heat_file_sha256") != FORMAL_HEAT_SHA256:
        raise ValueError("D40 service heat hash mismatch")
    if provenance.get("vre_file_sha256") != LEGACY_VRE_SHA256:
        raise ValueError("D40 service VRE hash mismatch")
    if provenance.get("price_basis_tree_sha256") != PRICE_BASIS_TREE_SHA256:
        raise ValueError("D40 service price basis hash mismatch")
    if provenance.get("code_sha256") != _code_hashes():
        raise ValueError("D40 service code hash mismatch")
    return payload


def _service_specs(
    service: dict[str, Any],
) -> tuple[AnnualCurtailmentServiceSpec, AnnualPCCExportServiceSpec]:
    return (
        AnnualCurtailmentServiceSpec(
            service_id="e0d40_baseline_epsilon10_actual",
            maximum_curtailment_mwh=service["epsilon_curtailment_ceiling_mwh"],
        ),
        AnnualPCCExportServiceSpec(
            service_id="e0d40_baseline_actual_no_storage_pcc",
            target_export_mwh=service["pcc_export_target_mwh"],
        ),
    )


def _linearity_audit(model: object) -> dict[str, Any]:
    from pyomo.environ import Constraint, Objective, Var
    from pyomo.repn import generate_standard_repn

    nonlinear_components: list[str] = []
    for component_type in (Constraint, Objective):
        for item in model.component_data_objects(component_type, active=True):
            expression = item.body if component_type is Constraint else item.expr
            representation = generate_standard_repn(expression)
            if (
                representation.nonlinear_expr is not None
                or representation.quadratic_vars
            ):
                nonlinear_components.append(item.name)
    variables = tuple(model.component_data_objects(Var, active=True))
    return {
        "active_variable_count": len(variables),
        "active_binary_variable_count": sum(
            1 for variable in variables if variable.is_binary()
        ),
        "active_constraint_count": sum(
            1 for _ in model.component_data_objects(Constraint, active=True)
        ),
        "nonlinear_component_count": len(nonlinear_components),
        "nonlinear_components": nonlinear_components,
    }


def _capacity_bound_audit(model: object, architecture: Architecture) -> dict[str, Any]:
    required: list[tuple[str, object]] = []
    link_components: dict[str, bool] = {}
    if architecture in (Architecture.BESS, Architecture.HYBRID):
        required.extend(
            (f"bess.{name}", getattr(model.bess, name))
            for name in (
                "energy_capacity_mwh",
                "charge_power_capacity_mw",
                "discharge_power_capacity_mw",
                "pcs_power_capacity_mw",
            )
        )
        link_components.update(
            {
                f"bess.{name}": hasattr(model.bess, name)
                for name in (
                    "installed",
                    "pcs_installed_upper",
                    "energy_requires_installation",
                    "charge_uses_common_pcs",
                    "discharge_uses_common_pcs",
                )
            }
        )
    if architecture in (Architecture.TES, Architecture.HYBRID):
        required.extend(
            (f"tes.{name}", getattr(model.tes, name))
            for name in (
                "salt_mass_t",
                "ht_tank_capacity_t",
                "mt_tank_capacity_t",
                "lt_tank_capacity_t",
                "ht_service_salt_mass_t",
                "mt_service_salt_mass_t",
                "electric_charge_input_capacity_mw",
                "steam_to_ht_input_capacity_mw",
                "steam_to_mt_input_capacity_mw",
                "electric_output_capacity_mw",
                "heat_output_capacity_mw",
            )
        )
        link_components.update(
            {
                f"tes.{name}": hasattr(model.tes, name)
                for name in (
                    "ht_state_capacity",
                    "mt_state_capacity",
                    "lt_state_capacity",
                    "ht_full_inventory_capacity",
                    "mt_full_inventory_capacity",
                    "lt_full_inventory_capacity",
                    "electric_charge_capacity_limit",
                    "steam_to_ht_capacity_limit",
                    "steam_to_mt_capacity_limit",
                    "electric_output_capacity_limit",
                    "heat_output_capacity_limit",
                    "ht_service_mass_limit",
                    "mt_service_mass_limit",
                )
            }
        )
        if hasattr(model.tes, "installed"):
            link_components.update(
                {
                    f"tes.{name}": hasattr(model.tes, name)
                    for name in (
                        "installed",
                        "port_installed",
                        "material_salt_upper",
                        "material_ht_tank_upper",
                        "material_mt_tank_upper",
                        "material_lt_tank_upper",
                        "material_port_upper",
                        "material_port_requires_tes",
                    )
                }
            )
    bounds: dict[str, dict[str, float | None]] = {}
    for name, variable in required:
        lower = None if variable.lb is None else float(variable.lb)
        upper = None if variable.ub is None else float(variable.ub)
        bounds[name] = {"lower_bound": lower, "upper_bound": upper}
    finite_nonnegative_bounds = all(
        item["lower_bound"] is not None
        and math.isfinite(float(item["lower_bound"]))
        and float(item["lower_bound"]) >= 0.0
        and item["upper_bound"] is not None
        and math.isfinite(float(item["upper_bound"]))
        and float(item["upper_bound"]) > 0.0
        for item in bounds.values()
    )
    return {
        "capacity_variable_count": len(bounds),
        "capacity_variable_bounds": bounds,
        "tes_capacity_policy": (
            "not_applicable"
            if architecture not in (Architecture.TES, Architecture.HYBRID)
            else (
                "semicontinuous_with_installation_binary"
                if hasattr(model.tes, "installed")
                else "continuous_zero_capacity_allowed"
            )
        ),
        "installation_link_components": link_components,
        "all_capacity_bounds_finite_nonnegative": finite_nonnegative_bounds,
        "all_installation_links_present": all(link_components.values()),
        "passed": finite_nonnegative_bounds and all(link_components.values()),
    }


def _state_boundary_audit(model: object, architecture: Architecture) -> dict[str, Any]:
    includes_bess = architecture in (Architecture.BESS, Architecture.HYBRID)
    includes_tes = architecture in (Architecture.TES, Architecture.HYBRID)
    chp_transition = [
        len(model.chp[unit].commitment_transition) for unit in model.unit_index
    ]
    chp_ramp_up = [len(model.chp[unit].normal_ramp_up) for unit in model.unit_index]
    chp_ramp_down = [
        len(model.chp[unit].normal_ramp_down) for unit in model.unit_index
    ]
    payload: dict[str, Any] = {
        "block_count": EXPECTED_BLOCK_COUNT,
        "cross_block_state_transfer_allowed": False,
        "chp_transition_constraints_per_unit": chp_transition,
        "chp_ramp_up_constraints_per_unit": chp_ramp_up,
        "chp_ramp_down_constraints_per_unit": chp_ramp_down,
        "chp_terminal_online_constraints_absent": all(
            not hasattr(model.chp[unit], "terminal_online")
            for unit in model.unit_index
        ),
        "bess": None,
        "tes": None,
    }
    if includes_bess:
        payload["bess"] = {
            "state_nodes": len(model.bess.states),
            "cyclic_constraints": len(model.bess.cyclic_energy),
            "fixed_initial_constraint_absent": not hasattr(
                model.bess, "initial_energy"
            ),
        }
    if includes_tes:
        payload["tes"] = {
            "state_nodes": len(model.tes.states),
            "cyclic_constraints_per_inventory": {
                "ht": len(model.tes.cyclic_ht),
                "mt": len(model.tes.cyclic_mt),
                "lt": len(model.tes.cyclic_lt),
            },
            "fixed_initial_constraints_absent": all(
                not hasattr(model.tes, name)
                for name in ("initial_ht", "initial_mt", "initial_lt")
            ),
        }
    storage_ok = True
    if includes_bess:
        storage_ok = storage_ok and payload["bess"] == {
            "state_nodes": EXPECTED_STATE_NODES_PER_STORAGE,
            "cyclic_constraints": 1,
            "fixed_initial_constraint_absent": True,
        }
    if includes_tes:
        storage_ok = storage_ok and payload["tes"] == {
            "state_nodes": EXPECTED_STATE_NODES_PER_STORAGE,
            "cyclic_constraints_per_inventory": {"ht": 1, "mt": 1, "lt": 1},
            "fixed_initial_constraints_absent": True,
        }
    payload["passed"] = all(
        (
            storage_ok,
            all(value == FULL_YEAR_HOURS for value in chp_transition),
            all(value == FULL_YEAR_HOURS for value in chp_ramp_up),
            all(value == FULL_YEAR_HOURS for value in chp_ramp_down),
            payload["chp_terminal_online_constraints_absent"],
        )
    )
    return payload


def build_architecture_manifest(
    architecture: Architecture,
    service_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    """Build one 8784 h model and return its deterministic Gate A audit."""

    from pyomo.environ import value

    if not isinstance(architecture, Architecture):
        raise ValueError("D40 architecture must use Architecture")
    service = load_full_year_service(service_path)
    input_hashes = _input_hashes(heat_path, vre_path, price_basis_path)
    state = state_spec("baseline")
    horizon_input = load_full_year_input(heat_path, vre_path, state)
    if horizon_input.timeseries.period_count != FULL_YEAR_HOURS:
        raise ValueError("D40 requires exactly 8784 actual hours")
    if len(horizon_input.horizon.dispatch_blocks) != EXPECTED_BLOCK_COUNT:
        raise ValueError("D40 requires one full-year cyclic block")
    if not math.isclose(
        horizon_input.renewable_available_mwh,
        ACTUAL_RENEWABLE_AVAILABLE_MWH,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError("D40 full-year renewable availability mismatch")
    curtailment_service, pcc_service = _service_specs(service)
    case = build_d38_case(
        state=state,
        architecture=architecture,
        horizon_input=horizon_input,
        planning_inputs=planning_inputs_for_state(price_basis_path, state),
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=COAL_PRICE_CNY_PER_TCE,
            curtailment_penalty_cny_per_mwh=0.0,
        ),
        curtailment_service=curtailment_service,
        pcc_export_service=pcc_service,
    )
    model = build_endogenous_capacity_model(case)
    linearity = _linearity_audit(model)
    capacity = _capacity_bound_audit(model, architecture)
    state_boundary = _state_boundary_audit(model, architecture)
    includes_bess = hasattr(model, "bess")
    includes_tes = hasattr(model, "tes")
    weighted_hours = float(value(model.annual_weighted_hours))
    service_audit = {
        "curtailment_constraint_active": bool(
            model.annual_curtailment_service.active
        ),
        "pcc_export_constraint_active": bool(model.annual_pcc_export_service.active),
        "curtailment_ceiling_mwh": EPSILON_CURTAILMENT_CEILING_MWH,
        "pcc_export_target_mwh": PCC_EXPORT_TARGET_MWH,
    }
    architecture_presence = {
        "bess_block_present": includes_bess,
        "tes_block_present": includes_tes,
    }
    expected_presence = {
        Architecture.NO_STORAGE: {
            "bess_block_present": False,
            "tes_block_present": False,
        },
        Architecture.BESS: {
            "bess_block_present": True,
            "tes_block_present": False,
        },
        Architecture.TES: {
            "bess_block_present": False,
            "tes_block_present": True,
        },
        Architecture.HYBRID: {
            "bess_block_present": True,
            "tes_block_present": True,
        },
    }[architecture]
    passed = all(
        (
            weighted_hours == float(FULL_YEAR_HOURS),
            architecture_presence == expected_presence,
            linearity["active_variable_count"] > 0,
            linearity["active_binary_variable_count"] > 0,
            linearity["active_constraint_count"] > 0,
            linearity["nonlinear_component_count"] == 0,
            capacity["passed"],
            state_boundary["passed"],
            service_audit["curtailment_constraint_active"],
            service_audit["pcc_export_constraint_active"],
        )
    )
    manifest = {
        "schema_id": BUILD_SCHEMA_ID,
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "solver_invoked": False,
        "status": "build_complete_no_solve" if passed else "build_audit_failed",
        "architecture": architecture.value,
        "service_contract_sha256": _sha256(service_path),
        "provenance": {**input_hashes, "code_sha256": _code_hashes()},
        "horizon": {
            "horizon_id": horizon_input.horizon_id,
            "model_period_count": horizon_input.timeseries.period_count,
            "weighted_annual_hours": weighted_hours,
            "dispatch_block_count": len(horizon_input.horizon.dispatch_blocks),
            "dispatch_block_lengths": [
                len(block.periods) for block in horizon_input.horizon.dispatch_blocks
            ],
        },
        "architecture_presence": architecture_presence,
        "service_audit": service_audit,
        "capacity_bound_audit": capacity,
        "state_boundary_audit": state_boundary,
        "linearity_audit": linearity,
        "audit": {"passed": passed},
    }
    return manifest


def _peak_rss_gib() -> float | None:
    try:
        import resource

        rss = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        divisor = 1024.0**3 if sys.platform == "darwin" else 1024.0**2
        return rss / divisor
    except (ImportError, OSError, ValueError):
        return None


def _available_memory_gib() -> float | None:
    meminfo = Path("/proc/meminfo")
    if not meminfo.is_file():
        return None
    for line in meminfo.read_text(encoding="ascii").splitlines():
        if line.startswith("MemAvailable:"):
            return float(line.split()[1]) / 1024.0**2
    return None


def write_service_bundle(
    source_service_path: Path,
    d39_gate_b_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    started = perf_counter()
    payload = build_full_year_service_payload(
        source_service_path,
        d39_gate_b_path,
        heat_path,
        vre_path,
        price_basis_path,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    service_bytes = _canonical_json_bytes(payload)
    (output_dir / SERVICE_NAME).write_bytes(service_bytes)
    execution = {
        "schema_id": f"{SERVICE_SCHEMA_ID}.execution",
        "runtime_seconds": perf_counter() - started,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "service_sha256": hashlib.sha256(service_bytes).hexdigest(),
    }
    _write_json(output_dir / SERVICE_EXECUTION_NAME, execution)
    return payload


def write_architecture_audit(
    architecture: Architecture,
    service_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    available_before = _available_memory_gib()
    started = perf_counter()
    manifest = build_architecture_manifest(
        architecture,
        service_path,
        heat_path,
        vre_path,
        price_basis_path,
    )
    runtime = perf_counter() - started
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_name = f"build_{architecture.value}.json"
    manifest_bytes = _canonical_json_bytes(manifest)
    (output_dir / manifest_name).write_bytes(manifest_bytes)
    execution = {
        "schema_id": f"{BUILD_SCHEMA_ID}.execution",
        "architecture": architecture.value,
        "runtime_seconds": runtime,
        "peak_process_rss_gib": _peak_rss_gib(),
        "available_memory_before_gib": available_before,
        "available_memory_after_gib": _available_memory_gib(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
    _write_json(output_dir / f"build_{architecture.value}_execution.json", execution)
    if manifest["audit"]["passed"] is not True:
        raise RuntimeError(f"D40 {architecture.value} build audit failed")
    return manifest


def compile_gate_a_manifest(
    service_path: Path,
    build_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile four clean-process audits and enforce the preregistered resource gate."""

    service = load_full_year_service(service_path)
    service_sha = _sha256(service_path)
    builds: dict[str, dict[str, Any]] = {}
    executions: dict[str, dict[str, Any]] = {}
    for architecture in ARCHITECTURES:
        name = architecture.value
        manifest_path = build_dir / f"build_{name}.json"
        execution_path = build_dir / f"build_{name}_execution.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        execution = json.loads(execution_path.read_text(encoding="utf-8"))
        if manifest.get("schema_id") != BUILD_SCHEMA_ID:
            raise ValueError(f"D40 {name} build schema mismatch")
        if manifest.get("architecture") != name:
            raise ValueError(f"D40 {name} build architecture mismatch")
        if manifest.get("service_contract_sha256") != service_sha:
            raise ValueError(f"D40 {name} service hash mismatch")
        if manifest.get("solver_invoked") is not False:
            raise ValueError(f"D40 {name} Gate A invoked a solver")
        if manifest.get("audit", {}).get("passed") is not True:
            raise ValueError(f"D40 {name} structural audit failed")
        if execution.get("schema_id") != f"{BUILD_SCHEMA_ID}.execution":
            raise ValueError(f"D40 {name} execution schema mismatch")
        if execution.get("architecture") != name:
            raise ValueError(f"D40 {name} execution architecture mismatch")
        if execution.get("manifest_sha256") != _sha256(manifest_path):
            raise ValueError(f"D40 {name} execution manifest hash mismatch")
        builds[name] = manifest
        executions[name] = execution

    sizes = {
        name: payload["linearity_audit"] for name, payload in builds.items()
    }
    monotonic = all(
        (
            sizes["bess"]["active_variable_count"]
            > sizes["no_storage"]["active_variable_count"],
            sizes["tes"]["active_variable_count"]
            > sizes["no_storage"]["active_variable_count"],
            sizes["hybrid"]["active_variable_count"]
            > sizes["bess"]["active_variable_count"],
            sizes["hybrid"]["active_variable_count"]
            > sizes["tes"]["active_variable_count"],
            sizes["hybrid"]["active_binary_variable_count"]
            > sizes["bess"]["active_binary_variable_count"],
            sizes["hybrid"]["active_binary_variable_count"]
            > sizes["tes"]["active_binary_variable_count"],
            sizes["hybrid"]["active_constraint_count"]
            > sizes["bess"]["active_constraint_count"],
            sizes["hybrid"]["active_constraint_count"]
            > sizes["tes"]["active_constraint_count"],
        )
    )
    resource_values_ok = all(
        isinstance(execution.get(key), (int, float))
        and not isinstance(execution.get(key), bool)
        and math.isfinite(float(execution[key]))
        for execution in executions.values()
        for key in (
            "peak_process_rss_gib",
            "available_memory_before_gib",
            "available_memory_after_gib",
        )
    )
    resource_passed = resource_values_ok and all(
        float(execution["peak_process_rss_gib"]) <= BUILD_PEAK_RSS_LIMIT_GIB
        and float(execution["available_memory_after_gib"])
        >= BUILD_MIN_AVAILABLE_MEMORY_GIB
        for execution in executions.values()
    )
    passed = monotonic and resource_passed
    manifest = {
        "schema_id": GATE_A_SCHEMA_ID,
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "solver_invoked": False,
        "status": "gate_a_passed" if passed else "build_or_resource_failure",
        "service_contract_sha256": service_sha,
        "service": {
            "state_id": service["state"]["state_id"],
            "epsilon_curtailment_ceiling_mwh": service[
                "epsilon_curtailment_ceiling_mwh"
            ],
            "pcc_export_target_mwh": service["pcc_export_target_mwh"],
            "representative_period_input_used": False,
        },
        "build_manifest_sha256": {
            name: _sha256(build_dir / f"build_{name}.json") for name in builds
        },
        "model_size": sizes,
        "architecture_size_ordering_passed": monotonic,
        "resource_thresholds": {
            "maximum_peak_process_rss_gib": BUILD_PEAK_RSS_LIMIT_GIB,
            "minimum_available_memory_after_build_gib": (
                BUILD_MIN_AVAILABLE_MEMORY_GIB
            ),
        },
        "resource_measurements_complete": resource_values_ok,
        "resource_gate_passed": resource_passed,
        "audit": {"passed": passed},
    }
    execution_payload = {
        "schema_id": f"{GATE_A_SCHEMA_ID}.execution",
        "case_execution": executions,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
    }
    return manifest, execution_payload


def write_gate_a_manifest(
    service_path: Path,
    build_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    manifest, execution = compile_gate_a_manifest(service_path, build_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_bytes = _canonical_json_bytes(manifest)
    (output_dir / GATE_A_MANIFEST_NAME).write_bytes(manifest_bytes)
    execution["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    _write_json(output_dir / GATE_A_EXECUTION_NAME, execution)
    if manifest["audit"]["passed"] is not True:
        raise RuntimeError("D40 Gate A build/resource audit failed")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    service = commands.add_parser("service")
    service.add_argument("--source-service", type=Path, required=True)
    service.add_argument("--d39-gate-b", type=Path, required=True)
    service.add_argument("--heat-path", type=Path, required=True)
    service.add_argument("--vre-path", type=Path, required=True)
    service.add_argument("--price-basis-path", type=Path, required=True)
    service.add_argument("--output-dir", type=Path, required=True)

    build = commands.add_parser("build")
    build.add_argument(
        "--architecture",
        choices=tuple(item.value for item in ARCHITECTURES),
        required=True,
    )
    build.add_argument("--service-file", type=Path, required=True)
    build.add_argument("--heat-path", type=Path, required=True)
    build.add_argument("--vre-path", type=Path, required=True)
    build.add_argument("--price-basis-path", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)

    audit = commands.add_parser("audit")
    audit.add_argument("--service-file", type=Path, required=True)
    audit.add_argument("--build-dir", type=Path, required=True)
    audit.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "service":
        payload = write_service_bundle(
            args.source_service,
            args.d39_gate_b,
            args.heat_path,
            args.vre_path,
            args.price_basis_path,
            args.output_dir,
        )
    elif args.command == "build":
        payload = write_architecture_audit(
            Architecture(args.architecture),
            args.service_file,
            args.heat_path,
            args.vre_path,
            args.price_basis_path,
            args.output_dir,
        )
    else:
        payload = write_gate_a_manifest(
            args.service_file,
            args.build_dir,
            args.output_dir,
        )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
