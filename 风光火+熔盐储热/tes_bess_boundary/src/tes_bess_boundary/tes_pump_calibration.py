"""Bottom-up E0-D-9B-2 TES pump screening and reproducible audit artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from tes_bess_boundary.tes_loss_auxiliary import (
    TESPumpAuxiliarySpec,
    TESSaltPathThroughput,
)
from tes_bess_boundary.tes_loss_calibration import (
    TREVISAN_2022_DOI,
    build_trevisan_2022_aggregate_anchor,
)
from tes_bess_boundary.tes_temperature_scenarios import (
    MTScenarioPoint,
    build_e0d8_hitec_normalized_mt_scenarios,
)


WANG_2025_DOI = "10.1016/j.apenergy.2025.126876"
ARTIFACT_SCHEMA_ID = "e0-d-9b-2-pump-calibration-v1"


def _require_finite_positive(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and positive")


def _require_temperature_c(temperature_c: float) -> None:
    if (
        isinstance(temperature_c, bool)
        or not math.isfinite(temperature_c)
        or temperature_c <= -273.15
    ):
        raise ValueError("temperature must be finite and above absolute zero")


def hitec_density_kg_per_m3(temperature_c: float) -> float:
    """Return Wang et al.'s HITEC density correlation, ``2288 - 0.748 T``."""

    _require_temperature_c(temperature_c)
    density = 2288.0 - 0.748 * temperature_c
    _require_finite_positive(density, "HITEC density")
    return density


def hitec_specific_heat_j_per_kg_k(temperature_c: float) -> float:
    """Return Wang et al.'s HITEC heat-capacity correlation, ``1507 - 0.1 T``."""

    _require_temperature_c(temperature_c)
    specific_heat = 1507.0 - 0.1 * temperature_c
    _require_finite_positive(specific_heat, "HITEC specific heat")
    return specific_heat


def hitec_sensible_energy_mwh_per_tonne(
    temperature_low_c: float,
    temperature_high_c: float,
) -> float:
    """Integrate the linear HITEC heat capacity exactly between two states."""

    _require_temperature_c(temperature_low_c)
    _require_temperature_c(temperature_high_c)
    if temperature_high_c <= temperature_low_c:
        raise ValueError("high temperature must exceed low temperature")
    delta = temperature_high_c - temperature_low_c
    integral_j_per_kg = 1507.0 * delta - 0.05 * (
        temperature_high_c**2 - temperature_low_c**2
    )
    _require_finite_positive(integral_j_per_kg, "integrated HITEC sensible heat")
    return integral_j_per_kg / 3_600_000.0


def hydraulic_pump_specific_energy_kwh_per_tonne(
    pressure_drop_pa: float,
    density_kg_per_m3: float,
    pump_efficiency: float,
) -> float:
    """Convert ``delta_p / (rho eta)`` to kWh per tonne of transported salt."""

    _require_finite_positive(pressure_drop_pa, "pressure drop")
    _require_finite_positive(density_kg_per_m3, "density")
    if (
        isinstance(pump_efficiency, bool)
        or not math.isfinite(pump_efficiency)
        or not 0.0 < pump_efficiency <= 1.0
    ):
        raise ValueError("pump efficiency must lie in (0, 1]")
    return pressure_drop_pa / (density_kg_per_m3 * pump_efficiency * 3600.0)


@dataclass(frozen=True)
class TESPumpHydraulicAnchor:
    """Published hydraulic quantities before author scenario construction."""

    source_doi: str
    operating_pressure_pa: float
    loop_pressure_loss_fraction: float
    active_component_pressure_loss_fraction: float
    pump_efficiency: float

    def __post_init__(self) -> None:
        if not self.source_doi.startswith("10."):
            raise ValueError("hydraulic anchor requires a DOI source")
        _require_finite_positive(self.operating_pressure_pa, "operating pressure")
        for value, label in (
            (self.loop_pressure_loss_fraction, "loop pressure-loss fraction"),
            (
                self.active_component_pressure_loss_fraction,
                "active-component pressure-loss fraction",
            ),
            (self.pump_efficiency, "pump efficiency"),
        ):
            if not math.isfinite(value) or not 0.0 < value <= 1.0:
                raise ValueError(f"{label} must lie in (0, 1]")

    @property
    def loop_pressure_drop_pa(self) -> float:
        return self.operating_pressure_pa * self.loop_pressure_loss_fraction

    @property
    def active_component_pressure_drop_pa(self) -> float:
        return self.operating_pressure_pa * self.active_component_pressure_loss_fraction


class E0D9B2PumpLevel(str, Enum):
    """Pre-registered bottom-up hydraulic screening levels."""

    LOW = "low"
    BASE = "base"
    HIGH = "high"


@dataclass(frozen=True)
class TESPumpPressureScenario:
    """One author pressure-drop mapping supported by published anchors."""

    level: E0D9B2PumpLevel
    pressure_drop_pa: float
    pump_efficiency: float
    parameter_source_id: str
    evidence_source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.level, E0D9B2PumpLevel):
            raise TypeError("level must use E0D9B2PumpLevel")
        _require_finite_positive(self.pressure_drop_pa, "pressure drop")
        if not math.isfinite(self.pump_efficiency) or not (
            0.0 < self.pump_efficiency <= 1.0
        ):
            raise ValueError("pump efficiency must lie in (0, 1]")
        if not self.parameter_source_id.startswith("author:"):
            raise ValueError("pump scenarios require an author: value source")
        if not self.evidence_source_ids or any(
            not source.startswith("doi:10.") for source in self.evidence_source_ids
        ):
            raise ValueError("pump evidence ids must be DOI-prefixed")


@dataclass(frozen=True)
class TESPathPumpCalibration:
    """Five path-specific coefficients for one pressure and MT scenario."""

    scenario: TESPumpPressureScenario
    mt_scenario_id: str
    temperature_lt_c: float
    temperature_mt_c: float
    temperature_ht_c: float
    pump: TESPumpAuxiliarySpec

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, TESPumpPressureScenario):
            raise TypeError("scenario must be a TESPumpPressureScenario")
        if not self.mt_scenario_id.strip():
            raise ValueError("MT scenario id is required")
        if not self.temperature_ht_c > self.temperature_mt_c > self.temperature_lt_c:
            raise ValueError("calibration temperatures must satisfy HT > MT > LT")
        if not isinstance(self.pump, TESPumpAuxiliarySpec):
            raise TypeError("pump must be a TESPumpAuxiliarySpec")


@dataclass(frozen=True)
class TESStandardDualServiceCycle:
    """Pre-registered 45-MWhth cycle used only for cross-project screening."""

    mt_scenario_id: str
    thermal_capacity_mwh: float
    cycles_per_year: float
    salt_mass_t: float
    path_throughput: TESSaltPathThroughput

    def __post_init__(self) -> None:
        if not self.mt_scenario_id.strip():
            raise ValueError("MT scenario id is required")
        for value, label in (
            (self.thermal_capacity_mwh, "thermal capacity"),
            (self.cycles_per_year, "cycles per year"),
            (self.salt_mass_t, "salt mass"),
        ):
            _require_finite_positive(value, label)
        if not isinstance(self.path_throughput, TESSaltPathThroughput):
            raise TypeError("path throughput must be a TESSaltPathThroughput")


@dataclass(frozen=True)
class TESStandardCyclePumpAudit:
    """Bottom-up standard-cycle result beside the non-binding aggregate anchor."""

    path_calibration: TESPathPumpCalibration
    cycle: TESStandardDualServiceCycle
    annual_pump_electricity_mwh: float
    trevisan_total_electricity_mwh: float
    trevisan_aggregate_pump_anchor_mwh: float
    aggregate_implied_uniform_kwh_per_tonne: float

    @property
    def fraction_of_trevisan_pump_anchor(self) -> float:
        return self.annual_pump_electricity_mwh / self.trevisan_aggregate_pump_anchor_mwh

    @property
    def share_of_trevisan_total_electricity(self) -> float:
        return self.annual_pump_electricity_mwh / self.trevisan_total_electricity_mwh


@dataclass(frozen=True)
class TESPumpCalibrationArtifacts:
    """Paths returned by the deterministic artifact writer."""

    csv_path: Path
    manifest_path: Path


def build_trevisan_2022_pump_hydraulic_anchor() -> TESPumpHydraulicAnchor:
    """Return the published pressure, loss-share, and pump-efficiency values."""

    return TESPumpHydraulicAnchor(
        source_doi=TREVISAN_2022_DOI,
        operating_pressure_pa=200_000.0,
        loop_pressure_loss_fraction=0.20,
        active_component_pressure_loss_fraction=0.05,
        pump_efficiency=0.90,
    )


def build_e0d9b2_pump_pressure_scenarios() -> tuple[TESPumpPressureScenario, ...]:
    """Build loop-only, loop-plus-component, and full-pressure stress levels."""

    anchor = build_trevisan_2022_pump_hydraulic_anchor()
    evidence = (f"doi:{anchor.source_doi}", f"doi:{WANG_2025_DOI}")
    definitions = (
        (
            E0D9B2PumpLevel.LOW,
            anchor.loop_pressure_drop_pa,
            "author:e0-d-9b-2-loop-only-pressure-drop-v1",
        ),
        (
            E0D9B2PumpLevel.BASE,
            anchor.loop_pressure_drop_pa + anchor.active_component_pressure_drop_pa,
            "author:e0-d-9b-2-loop-plus-one-active-component-v1",
        ),
        (
            E0D9B2PumpLevel.HIGH,
            anchor.operating_pressure_pa,
            "author:e0-d-9b-2-full-operating-pressure-stress-v1",
        ),
    )
    return tuple(
        TESPumpPressureScenario(
            level=level,
            pressure_drop_pa=pressure_drop,
            pump_efficiency=anchor.pump_efficiency,
            parameter_source_id=source_id,
            evidence_source_ids=evidence,
        )
        for level, pressure_drop, source_id in definitions
    )


def calibrate_pump_for_mt(
    scenario: TESPumpPressureScenario,
    mt_point: MTScenarioPoint,
) -> TESPathPumpCalibration:
    """Map the same disclosed pressure scenario to five path temperatures."""

    if not isinstance(scenario, TESPumpPressureScenario):
        raise TypeError("scenario must be a TESPumpPressureScenario")
    if not isinstance(mt_point, MTScenarioPoint):
        raise TypeError("mt_point must be an MTScenarioPoint")

    def coefficient(temperature_c: float) -> float:
        return hydraulic_pump_specific_energy_kwh_per_tonne(
            scenario.pressure_drop_pa,
            hitec_density_kg_per_m3(temperature_c),
            scenario.pump_efficiency,
        )

    lt_coefficient = coefficient(mt_point.temperature_lt_c)
    return TESPathPumpCalibration(
        scenario=scenario,
        mt_scenario_id=mt_point.scenario_id,
        temperature_lt_c=mt_point.temperature_lt_c,
        temperature_mt_c=mt_point.temperature_mt_c,
        temperature_ht_c=mt_point.temperature_ht_c,
        pump=TESPumpAuxiliarySpec(
            electric_lt_to_ht_kwh_per_tonne=lt_coefficient,
            steam_lt_to_ht_kwh_per_tonne=lt_coefficient,
            steam_lt_to_mt_kwh_per_tonne=lt_coefficient,
            power_ht_to_mt_kwh_per_tonne=coefficient(mt_point.temperature_ht_c),
            heat_mt_to_lt_kwh_per_tonne=coefficient(mt_point.temperature_mt_c),
        ),
    )


def build_standard_dual_service_cycle(
    mt_point: MTScenarioPoint,
    *,
    thermal_capacity_mwh: float = 45.0,
    cycles_per_year: float = 365.0,
) -> TESStandardDualServiceCycle:
    """Build one full charge, electric downgrade, and heat downgrade per cycle."""

    if not isinstance(mt_point, MTScenarioPoint):
        raise TypeError("mt_point must be an MTScenarioPoint")
    _require_finite_positive(thermal_capacity_mwh, "thermal capacity")
    _require_finite_positive(cycles_per_year, "cycles per year")
    energy_per_tonne = hitec_sensible_energy_mwh_per_tonne(
        mt_point.temperature_lt_c,
        mt_point.temperature_ht_c,
    )
    salt_mass_t = thermal_capacity_mwh / energy_per_tonne
    annual_path_mass_t = salt_mass_t * cycles_per_year
    return TESStandardDualServiceCycle(
        mt_scenario_id=mt_point.scenario_id,
        thermal_capacity_mwh=thermal_capacity_mwh,
        cycles_per_year=cycles_per_year,
        salt_mass_t=salt_mass_t,
        path_throughput=TESSaltPathThroughput(
            electric_lt_to_ht_t=annual_path_mass_t,
            power_ht_to_mt_t=annual_path_mass_t,
            heat_mt_to_lt_t=annual_path_mass_t,
        ),
    )


def audit_standard_dual_service_cycle(
    scenario: TESPumpPressureScenario,
    mt_point: MTScenarioPoint,
) -> TESStandardCyclePumpAudit:
    """Audit bottom-up pump energy without fitting it to the aggregate target."""

    calibration = calibrate_pump_for_mt(scenario, mt_point)
    cycle = build_standard_dual_service_cycle(mt_point)
    aggregate = build_trevisan_2022_aggregate_anchor()
    uniform = aggregate.aggregate_implied_uniform_pump_spec(
        total_salt_throughput_t=cycle.path_throughput.total_t
    )
    return TESStandardCyclePumpAudit(
        path_calibration=calibration,
        cycle=cycle,
        annual_pump_electricity_mwh=cycle.path_throughput.pump_energy_mwh(
            calibration.pump
        ),
        trevisan_total_electricity_mwh=aggregate.annual_electricity_consumption_mwh,
        trevisan_aggregate_pump_anchor_mwh=aggregate.pump_electricity_target_mwh,
        aggregate_implied_uniform_kwh_per_tonne=(
            uniform.electric_lt_to_ht_kwh_per_tonne
        ),
    )


_CSV_COLUMNS = (
    "pump_level",
    "mt_scenario_id",
    "temperature_lt_c",
    "temperature_mt_c",
    "temperature_ht_c",
    "pressure_drop_pa",
    "pump_efficiency",
    "electric_lt_to_ht_kwh_per_tonne",
    "steam_lt_to_ht_kwh_per_tonne",
    "steam_lt_to_mt_kwh_per_tonne",
    "power_ht_to_mt_kwh_per_tonne",
    "heat_mt_to_lt_kwh_per_tonne",
    "standard_cycle_capacity_mwh_th",
    "standard_cycle_cycles_per_year",
    "standard_cycle_salt_mass_t",
    "standard_cycle_total_path_throughput_t",
    "annual_pump_electricity_mwh",
    "trevisan_total_electricity_mwh",
    "trevisan_aggregate_pump_anchor_mwh",
    "pump_share_of_trevisan_total_electricity",
    "fraction_of_trevisan_pump_anchor",
    "aggregate_implied_uniform_kwh_per_tonne",
    "parameter_source_id",
    "evidence_source_ids",
)


def _format_csv_value(value: object) -> object:
    if isinstance(value, float):
        return format(value, ".15g")
    return value


def _artifact_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    mt_points = build_e0d8_hitec_normalized_mt_scenarios().points
    for scenario in build_e0d9b2_pump_pressure_scenarios():
        for point in mt_points:
            audit = audit_standard_dual_service_cycle(scenario, point)
            pump = audit.path_calibration.pump
            cycle = audit.cycle
            row: dict[str, object] = {
                "pump_level": scenario.level.value,
                "mt_scenario_id": point.scenario_id,
                "temperature_lt_c": point.temperature_lt_c,
                "temperature_mt_c": point.temperature_mt_c,
                "temperature_ht_c": point.temperature_ht_c,
                "pressure_drop_pa": scenario.pressure_drop_pa,
                "pump_efficiency": scenario.pump_efficiency,
                "electric_lt_to_ht_kwh_per_tonne": (
                    pump.electric_lt_to_ht_kwh_per_tonne
                ),
                "steam_lt_to_ht_kwh_per_tonne": pump.steam_lt_to_ht_kwh_per_tonne,
                "steam_lt_to_mt_kwh_per_tonne": pump.steam_lt_to_mt_kwh_per_tonne,
                "power_ht_to_mt_kwh_per_tonne": pump.power_ht_to_mt_kwh_per_tonne,
                "heat_mt_to_lt_kwh_per_tonne": pump.heat_mt_to_lt_kwh_per_tonne,
                "standard_cycle_capacity_mwh_th": cycle.thermal_capacity_mwh,
                "standard_cycle_cycles_per_year": cycle.cycles_per_year,
                "standard_cycle_salt_mass_t": cycle.salt_mass_t,
                "standard_cycle_total_path_throughput_t": (
                    cycle.path_throughput.total_t
                ),
                "annual_pump_electricity_mwh": audit.annual_pump_electricity_mwh,
                "trevisan_total_electricity_mwh": (
                    audit.trevisan_total_electricity_mwh
                ),
                "trevisan_aggregate_pump_anchor_mwh": (
                    audit.trevisan_aggregate_pump_anchor_mwh
                ),
                "pump_share_of_trevisan_total_electricity": (
                    audit.share_of_trevisan_total_electricity
                ),
                "fraction_of_trevisan_pump_anchor": (
                    audit.fraction_of_trevisan_pump_anchor
                ),
                "aggregate_implied_uniform_kwh_per_tonne": (
                    audit.aggregate_implied_uniform_kwh_per_tonne
                ),
                "parameter_source_id": scenario.parameter_source_id,
                "evidence_source_ids": "|".join(scenario.evidence_source_ids),
            }
            rows.append({key: _format_csv_value(value) for key, value in row.items()})
    return rows


def write_e0d9b2_pump_calibration_artifacts(
    output_dir: str | Path,
) -> TESPumpCalibrationArtifacts:
    """Write byte-stable CSV and manifest files for all 3 x 3 scenarios."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    csv_path = root / "e0d9b2_pump_calibration.csv"
    manifest_path = root / "manifest.json"

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    rows = _artifact_rows()
    writer.writerows(rows)
    csv_bytes = buffer.getvalue().encode("utf-8")
    csv_path.write_bytes(csv_bytes)

    manifest = {
        "csv_file": csv_path.name,
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "row_count": len(rows),
        "schema_id": ARTIFACT_SCHEMA_ID,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return TESPumpCalibrationArtifacts(csv_path=csv_path, manifest_path=manifest_path)


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    artifacts = write_e0d9b2_pump_calibration_artifacts(args.output)
    print(artifacts.csv_path)
    print(artifacts.manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
