"""Validate and bundle the sixteen pre-registered E0-D-35 probes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path

from tes_bess_boundary.e0d35_tes_materiality import (
    MATERIALITY_GRID,
    SCHEMA_ID as PROBE_SCHEMA_ID,
    SERVICES,
    reference_materiality_payload,
)


SCHEMA_ID = "tes_bess_boundary.e0d35_materiality_bundle.v1"
CSV_NAME = "e0d35_tes_materiality_grid.csv"
MANIFEST_NAME = "manifest.json"
EXECUTION_NAME = "execution.json"
ARCHITECTURES = ("tes", "hybrid")
REFINED_ZERO_GAP_IDENTITIES = {
    ("natural", "tes", 0.05),
    ("natural", "tes", 0.10),
    ("natural", "hybrid", 0.05),
    ("natural", "hybrid", 0.10),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fraction_label(fraction: float) -> str:
    if fraction == 0.0:
        return "0"
    return f"{fraction:.2f}".replace(".", "p")


def _finite(payload: dict, key: str) -> float:
    value = float(payload[key])
    if not math.isfinite(value):
        raise ValueError(f"{key} must be finite")
    return value


def _source_path(input_dir: Path, identity: tuple[str, str, float]) -> Path:
    service, architecture, fraction = identity
    stem = f"{service}_{architecture}_f{_fraction_label(fraction)}"
    if identity in REFINED_ZERO_GAP_IDENTITIES:
        return input_dir / "refined" / f"{stem}_g000.json"
    return input_dir / f"{stem}.json"


def _load_probe(path: Path, identity: tuple[str, str, float]) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    service, architecture, fraction = identity
    if payload.get("schema_id") != PROBE_SCHEMA_ID:
        raise ValueError(f"probe schema mismatch: {path.name}")
    if payload.get("service_name") != service:
        raise ValueError(f"service mismatch: {path.name}")
    if payload.get("result", {}).get("architecture") != architecture:
        raise ValueError(f"architecture mismatch: {path.name}")
    if not math.isclose(
        float(payload.get("materiality_fraction")),
        fraction,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError(f"materiality fraction mismatch: {path.name}")
    if payload.get("materiality_grid") != list(MATERIALITY_GRID):
        raise ValueError(f"materiality grid mismatch: {path.name}")
    if payload.get("materiality_audit", {}).get("passed") is not True:
        raise ValueError(f"materiality audit failed: {path.name}")
    result = payload["result"]
    if "optimal" not in str(result.get("termination_condition", "")).lower():
        raise ValueError(f"probe is not solver-optimal within tolerance: {path.name}")
    lower = _finite(result, "objective_lower_bound_cny")
    upper = _finite(result, "objective_upper_bound_cny")
    total = _finite(result, "annual_total_cost_cny")
    if lower > upper + 1e-3 or abs(total - upper) > 1e-2:
        raise ValueError(f"objective bounds are inconsistent: {path.name}")
    if identity in REFINED_ZERO_GAP_IDENTITIES:
        if _finite(result, "relative_mip_gap") > 1e-10:
            raise ValueError(f"refined probe is not zero-gap: {path.name}")
        if _finite(result, "tes_salt_mass_t") > 1e-7:
            raise ValueError(f"refined natural probe is not zero-TES: {path.name}")
    return payload


def _collapse_label(result: dict) -> str:
    tes_active = _finite(result, "tes_salt_mass_t") > 1e-7
    bess_value = result.get("bess_common_pcs_power_capacity_mw")
    bess_active = bess_value is not None and float(bess_value) > 1e-7
    if tes_active and bess_active:
        return "hybrid"
    if tes_active:
        return "tes"
    if bess_active:
        return "bess"
    return "no_storage"


def _canonical_row(payload: dict) -> dict:
    result = payload["result"]
    audit = payload["materiality_audit"]
    reference = payload["reference"]
    port_bins = audit["ports"]
    salt = _finite(result, "tes_salt_mass_t")
    return {
        "service": payload["service_name"],
        "architecture": result["architecture"],
        "materiality_fraction": payload["materiality_fraction"],
        "materiality_enabled": str(payload["materiality_enabled"]).lower(),
        "collapsed_architecture": _collapse_label(result),
        "objective_lower_bound_cny": _finite(result, "objective_lower_bound_cny"),
        "objective_upper_bound_cny": _finite(result, "objective_upper_bound_cny"),
        "relative_mip_gap": _finite(result, "relative_mip_gap"),
        "annual_total_cost_cny": _finite(result, "annual_total_cost_cny"),
        "annual_operating_cost_cny": _finite(result, "annual_operating_cost_cny"),
        "annual_storage_capacity_cost_cny": _finite(
            result,
            "annual_storage_capacity_cost_cny",
        ),
        "annual_bess_cycle_cost_cny": _finite(
            result,
            "annual_bess_cycle_cost_cny",
        ),
        "annual_bess_variable_om_cost_cny": _finite(
            result,
            "annual_bess_variable_om_cost_cny",
        ),
        "weighted_fuel_tce": _finite(result, "weighted_fuel_tce"),
        "weighted_curtailment_mwh": _finite(result, "weighted_curtailment_mwh"),
        "weighted_pcc_export_mwh": _finite(result, "weighted_pcc_export_mwh"),
        "tes_salt_mass_t": salt,
        "tes_salt_reference_fraction": salt / reference["salt_mass_t"],
        "tes_ht_service_salt_mass_t": _finite(
            result,
            "tes_ht_service_salt_mass_t",
        ),
        "tes_mt_service_salt_mass_t": _finite(
            result,
            "tes_mt_service_salt_mass_t",
        ),
        "tes_electric_charge_input_capacity_mw": _finite(
            result,
            "tes_electric_charge_input_capacity_mw",
        ),
        "tes_steam_to_ht_input_capacity_mw": _finite(
            result,
            "tes_steam_to_ht_input_capacity_mw",
        ),
        "tes_steam_to_mt_input_capacity_mw": _finite(
            result,
            "tes_steam_to_mt_input_capacity_mw",
        ),
        "tes_electric_output_capacity_mw": _finite(
            result,
            "tes_electric_output_capacity_mw",
        ),
        "tes_heat_output_capacity_mw": _finite(
            result,
            "tes_heat_output_capacity_mw",
        ),
        "tes_installation_binary": result["tes_installation_binary"],
        "electric_charge_installation_binary": port_bins[
            "electric_charge_input"
        ]["installation_binary"],
        "steam_to_ht_installation_binary": port_bins["steam_to_ht_input"][
            "installation_binary"
        ],
        "steam_to_mt_installation_binary": port_bins["steam_to_mt_input"][
            "installation_binary"
        ],
        "electric_output_installation_binary": port_bins["electric_output"][
            "installation_binary"
        ],
        "heat_output_installation_binary": port_bins["heat_output"][
            "installation_binary"
        ],
        "bess_common_pcs_power_capacity_mw": result[
            "bess_common_pcs_power_capacity_mw"
        ],
        "bess_energy_capacity_mwh": result["bess_energy_capacity_mwh"],
        "tes_auxiliary_mwh": _finite(result, "tes_auxiliary_mwh"),
        "curtailment_margin_mwh": _finite(audit, "curtailment_margin_mwh"),
        "pcc_export_residual_mwh": _finite(audit, "pcc_export_residual_mwh"),
        "formal_project_tac_ready": "false",
        "project_minimum_scale_claimed": "false",
    }


def build_bundle(input_dir: Path, output_dir: Path) -> dict:
    identities = tuple(
        (service, architecture, fraction)
        for service in SERVICES
        for architecture in ARCHITECTURES
        for fraction in MATERIALITY_GRID
    )
    probes = []
    execution_sources = []
    for identity in identities:
        path = _source_path(input_dir, identity)
        payload = _load_probe(path, identity)
        probes.append(payload)
        execution_sources.append(
            {
                "identity": list(identity),
                "source_file": path.relative_to(input_dir).as_posix(),
                "source_sha256": _sha256(path),
                "generated_at": payload["generated_at"],
                "runtime_seconds": payload["result"]["runtime_seconds"],
                "solver": payload["solver"],
            }
        )

    rows = [_canonical_row(payload) for payload in probes]
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / CSV_NAME
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "schema_id": SCHEMA_ID,
        "probe_schema_id": PROBE_SCHEMA_ID,
        "row_count": len(rows),
        "materiality_grid": list(MATERIALITY_GRID),
        "services": {name: asdict(service) for name, service in SERVICES.items()},
        "architectures": list(ARCHITECTURES),
        "reference": reference_materiality_payload(),
        "canonical_csv": CSV_NAME,
        "canonical_csv_sha256": _sha256(csv_path),
        "refined_zero_gap_identities": [
            list(identity) for identity in sorted(REFINED_ZERO_GAP_IDENTITIES)
        ],
        "claim_scope": "controlled_public_cost_materiality_sensitivity_not_formal_project_tac",
        "formal_project_tac_ready": False,
        "project_minimum_scale_claimed": False,
        "all_materiality_audits_passed": True,
    }
    manifest_path = output_dir / MANIFEST_NAME
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    execution = {
        "schema_id": f"{SCHEMA_ID}.execution",
        "canonical_manifest_sha256": _sha256(manifest_path),
        "sources": execution_sources,
    }
    with (output_dir / EXECUTION_NAME).open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(
            json.dumps(execution, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(
        json.dumps(
            build_bundle(args.input_dir, args.output_dir),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
