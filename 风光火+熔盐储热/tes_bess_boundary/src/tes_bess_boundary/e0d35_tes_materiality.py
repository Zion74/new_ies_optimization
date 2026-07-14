"""E0-D-35 pre-registered TES engineering-materiality sensitivity runner.

Each invocation solves one 24 h TES or Hybrid case at one locked materiality
fraction.  The reference is the disclosed E0-D-17 1200 MWhth / 150 MW slice.
Positive fractions impose semi-continuous salt and active-port domains; zero is
the unchanged continuous-capacity D34 baseline.  Results remain public-cost
sensitivities and cannot certify a project TAC or a Yangling technology winner.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter

from tes_bess_boundary.capacity_planning import TESMaterialityPolicy
from tes_bess_boundary.e0d17_exploration import (
    COAL_PRICE_CNY_PER_TCE,
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
    TES_PORT_CAPACITY_MW,
    TES_THERMAL_CAPACITY_MWH,
    build_e0d17_tes_spec,
    load_e0d17_inputs,
)
from tes_bess_boundary.e0d34_endogenous_capacity_sample import (
    SERVICE_TOLERANCE_MWH,
    _case,
    _planning_inputs,
    _result_payload,
    _window,
)
from tes_bess_boundary.model import (
    AnnualCurtailmentServiceSpec,
    AnnualPCCExportServiceSpec,
    Architecture,
    ValidationObjectiveSpec,
)
from tes_bess_boundary.planning_model import solve_endogenous_capacity
from tes_bess_boundary.solver import create_highs_solver


SCHEMA_ID = "tes_bess_boundary.e0d35_tes_materiality.v1"
REFERENCE_SOURCE_ID = "e0-d-17:1200mwhth-150mw-cascade-slice-v1"
MATERIALITY_GRID = (0.0, 0.01, 0.05, 0.10)
SAMPLE_START = "2024-01-01T00:00:00"
SAMPLE_HOURS = 24


@dataclass(frozen=True)
class E0D35Service:
    service_id: str
    curtailment_ceiling_mwh: float
    pcc_export_target_mwh: float


SERVICES = {
    "natural": E0D35Service(
        service_id="e0d35_natural_same_pcc_24h",
        curtailment_ceiling_mwh=578_514.502570776,
        pcc_export_target_mwh=4_656_918.485025815,
    ),
    "strict_1pct": E0D35Service(
        service_id="e0d35_strict_1pct_same_pcc_24h",
        curtailment_ceiling_mwh=572_729.3565550681,
        pcc_export_target_mwh=4_656_918.485025815,
    ),
}


def _locked_fraction(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("materiality fraction must be finite")
    for registered in MATERIALITY_GRID:
        if math.isclose(value, registered, rel_tol=0.0, abs_tol=1e-12):
            return registered
    raise ValueError(f"materiality fraction must be one of {MATERIALITY_GRID}")


def reference_materiality_payload() -> dict:
    fixed = build_e0d17_tes_spec()
    return {
        "source_id": REFERENCE_SOURCE_ID,
        "sensible_heat_mwh": TES_THERMAL_CAPACITY_MWH,
        "salt_mass_t": fixed.physics.salt_mass_t,
        "common_port_scale_mw": TES_PORT_CAPACITY_MW,
        "temperature_lt_c": fixed.physics.temperature_lt,
        "temperature_mt_c": fixed.physics.temperature_mt,
        "temperature_ht_c": fixed.physics.temperature_ht,
        "steam_ports_in_legacy_slice_mw": [
            fixed.port_caps.steam_to_ht_reference_input_mw,
            fixed.port_caps.steam_to_mt_reference_input_mw,
        ],
        "common_port_scale_is_author_normalization": True,
        "project_minimum_scale_claimed": False,
    }


def build_e0d35_materiality_policy(
    fraction: float,
) -> TESMaterialityPolicy | None:
    registered = _locked_fraction(fraction)
    if registered == 0.0:
        return None
    reference = reference_materiality_payload()
    return TESMaterialityPolicy(
        reference_sensible_heat_mwh=reference["sensible_heat_mwh"],
        reference_salt_mass_t=reference["salt_mass_t"],
        reference_port_capacity_mw=reference["common_port_scale_mw"],
        minimum_reference_fraction=registered,
        source_id=REFERENCE_SOURCE_ID,
    )


_PORT_RESULT_FIELDS = {
    "electric_charge_input": (
        "tes_electric_charge_input_capacity_mw",
        "tes_electric_charge_installation_binary",
    ),
    "steam_to_ht_input": (
        "tes_steam_to_ht_input_capacity_mw",
        "tes_steam_to_ht_installation_binary",
    ),
    "steam_to_mt_input": (
        "tes_steam_to_mt_input_capacity_mw",
        "tes_steam_to_mt_installation_binary",
    ),
    "electric_output": (
        "tes_electric_output_capacity_mw",
        "tes_electric_output_installation_binary",
    ),
    "heat_output": (
        "tes_heat_output_capacity_mw",
        "tes_heat_output_installation_binary",
    ),
}


def _binary(value: float | None, name: str, *, tolerance: float = 1e-6) -> int:
    if value is None or not math.isfinite(value):
        raise ValueError(f"{name} is missing")
    rounded = int(round(value))
    if rounded not in (0, 1) or abs(value - rounded) > tolerance:
        raise ValueError(f"{name} is not binary: {value}")
    return rounded


def audit_materiality_result(
    result: object,
    *,
    fraction: float,
    service: E0D35Service,
    tolerance: float = 1e-6,
) -> dict:
    registered = _locked_fraction(fraction)
    curtailment_margin = (
        service.curtailment_ceiling_mwh - result.weighted_curtailment_mwh
    )
    pcc_residual = result.weighted_pcc_export_mwh - service.pcc_export_target_mwh
    if curtailment_margin < -SERVICE_TOLERANCE_MWH:
        raise ValueError("curtailment service is violated")
    if abs(pcc_residual) > SERVICE_TOLERANCE_MWH:
        raise ValueError("PCC export service is violated")

    reference = reference_materiality_payload()
    minimum_salt = registered * reference["salt_mass_t"]
    minimum_port = registered * reference["common_port_scale_mw"]
    port_audit = {}
    if registered == 0.0:
        if result.tes_installation_binary is not None:
            raise ValueError("continuous baseline unexpectedly contains materiality binaries")
        for port, (capacity_field, binary_field) in _PORT_RESULT_FIELDS.items():
            if getattr(result, binary_field) is not None:
                raise ValueError(f"continuous baseline contains {port} binary")
            port_audit[port] = {
                "capacity_mw": getattr(result, capacity_field),
                "installation_binary": None,
                "minimum_if_active_mw": 0.0,
                "passed": True,
            }
        installed = None
    else:
        installed = _binary(result.tes_installation_binary, "TES installation")
        salt_mass = float(result.tes_salt_mass_t)
        if installed == 0 and salt_mass > tolerance:
            raise ValueError("uninstalled TES has positive salt mass")
        if installed == 1 and salt_mass + tolerance < minimum_salt:
            raise ValueError("installed TES is below the salt materiality threshold")
        output_binary_sum = 0
        for port, (capacity_field, binary_field) in _PORT_RESULT_FIELDS.items():
            capacity = float(getattr(result, capacity_field))
            port_installed = _binary(getattr(result, binary_field), f"{port} installation")
            if port_installed > installed:
                raise ValueError(f"{port} is installed without TES")
            if port_installed == 0 and capacity > tolerance:
                raise ValueError(f"inactive {port} has positive capacity")
            if port_installed == 1 and capacity + tolerance < minimum_port:
                raise ValueError(f"active {port} is below its materiality threshold")
            if port in ("electric_output", "heat_output"):
                output_binary_sum += port_installed
            port_audit[port] = {
                "capacity_mw": capacity,
                "installation_binary": port_installed,
                "minimum_if_active_mw": minimum_port,
                "passed": True,
            }
        if installed > output_binary_sum:
            raise ValueError("installed TES has no useful output path")

    return {
        "passed": True,
        "fraction": registered,
        "tes_installation_binary": installed,
        "minimum_salt_mass_t": minimum_salt,
        "actual_salt_mass_t": result.tes_salt_mass_t,
        "minimum_active_port_capacity_mw": minimum_port,
        "ports": port_audit,
        "curtailment_margin_mwh": curtailment_margin,
        "pcc_export_residual_mwh": pcc_residual,
        "service_tolerance_mwh": SERVICE_TOLERANCE_MWH,
    }


def run_probe(args: argparse.Namespace) -> dict:
    fraction = _locked_fraction(args.materiality_fraction)
    architecture = Architecture(args.architecture)
    if architecture not in (Architecture.TES, Architecture.HYBRID):
        raise ValueError("D35 only runs TES and Hybrid architectures")
    service = SERVICES[args.service]
    rows = load_e0d17_inputs(args.heat_path, args.vre_path)
    selected = _window(rows, datetime.fromisoformat(SAMPLE_START), SAMPLE_HOURS)
    materiality = build_e0d35_materiality_policy(fraction)
    planning_inputs = _planning_inputs(
        args.price_basis_path,
        tes_materiality=materiality,
    )
    case = _case(
        architecture,
        selected,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=COAL_PRICE_CNY_PER_TCE,
            curtailment_penalty_cny_per_mwh=0.0,
        ),
        service=AnnualCurtailmentServiceSpec(
            service_id=service.service_id,
            maximum_curtailment_mwh=service.curtailment_ceiling_mwh,
        ),
        pcc_service=AnnualPCCExportServiceSpec(
            service_id=service.service_id,
            target_export_mwh=service.pcc_export_target_mwh,
        ),
        planning_inputs=planning_inputs,
    )
    solver = create_highs_solver(
        threads=args.solver_threads,
        random_seed=0,
        mip_rel_gap=args.mip_rel_gap,
    )
    started = perf_counter()
    result = solve_endogenous_capacity(case, solver=solver)
    runtime_seconds = perf_counter() - started
    audit = audit_materiality_result(
        result,
        fraction=fraction,
        service=service,
    )
    return {
        "schema_id": SCHEMA_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "claim_scope": "controlled_public_cost_materiality_sensitivity_not_formal_project_tac",
        "formal_project_tac_ready": False,
        "project_minimum_scale_claimed": False,
        "data_scope": "formal_2024_heat_plus_legacy_2019_vre_shapes",
        "formal_heat_sha256": FORMAL_HEAT_SHA256,
        "legacy_vre_sha256": LEGACY_VRE_SHA256,
        "start": SAMPLE_START,
        "hours": SAMPLE_HOURS,
        "service_name": args.service,
        "service": asdict(service),
        "materiality_grid": list(MATERIALITY_GRID),
        "materiality_fraction": fraction,
        "materiality_enabled": materiality is not None,
        "reference_port_applies_to_all_active_ports": True,
        "reference": reference_materiality_payload(),
        "materiality_policy": None if materiality is None else asdict(materiality),
        "solver": {
            "name": "appsi_highs",
            "threads": args.solver_threads,
            "random_seed": 0,
            "mip_rel_gap": args.mip_rel_gap,
        },
        "result": _result_payload(result, runtime_seconds),
        "materiality_audit": audit,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heat-path", type=Path, required=True)
    parser.add_argument("--vre-path", type=Path, required=True)
    parser.add_argument("--price-basis-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--service", choices=tuple(SERVICES), required=True)
    parser.add_argument("--materiality-fraction", type=float, required=True)
    parser.add_argument(
        "--architecture",
        choices=(Architecture.TES.value, Architecture.HYBRID.value),
        required=True,
    )
    parser.add_argument("--solver-threads", type=int, default=1)
    parser.add_argument("--mip-rel-gap", type=float, default=0.001)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = run_probe(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
