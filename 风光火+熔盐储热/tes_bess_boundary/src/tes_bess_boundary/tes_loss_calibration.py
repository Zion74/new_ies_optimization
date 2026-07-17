"""Aggregate evidence anchors and author calibration for E0-D-9B TES losses."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from tes_bess_boundary.tes_loss_auxiliary import TESPumpAuxiliarySpec
from tes_bess_boundary.tes_temperature_scenarios import MTScenarioPoint


TREVISAN_2022_DOI = "10.1016/j.enconman.2022.116362"
KLASING_2025_DOI = "10.1016/j.apenergy.2024.124524"
WANG_2025_DOI = "10.1016/j.apenergy.2025.126876"


def _require_finite_positive(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and positive")


@dataclass(frozen=True)
class TESAggregateLossPumpAnchor:
    """Published system aggregates; not direct three-tank model coefficients."""

    source_doi: str
    thermal_capacity_mwh: float
    gross_annual_thermal_loss_mwh: float
    fixed_loss_compensation_fraction: float
    annual_electricity_consumption_mwh: float
    pump_electricity_fraction: float
    annual_hours: float = 8760.0

    def __post_init__(self) -> None:
        if not self.source_doi.startswith("10."):
            raise ValueError("aggregate anchor requires a DOI source")
        for value, label in (
            (self.thermal_capacity_mwh, "thermal capacity"),
            (self.gross_annual_thermal_loss_mwh, "gross annual thermal loss"),
            (self.annual_electricity_consumption_mwh, "annual electricity"),
            (self.annual_hours, "annual hours"),
        ):
            _require_finite_positive(value, label)
        for value, label in (
            (self.fixed_loss_compensation_fraction, "loss compensation fraction"),
            (self.pump_electricity_fraction, "pump electricity fraction"),
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{label} must lie in [0, 1]")

    @property
    def gross_capacity_normalized_loss_fraction_per_hour(self) -> float:
        """Annual aggregate divided by rated capacity and annual hours."""

        return (
            self.gross_annual_thermal_loss_mwh
            / self.thermal_capacity_mwh
            / self.annual_hours
        )

    @property
    def net_annual_thermal_loss_mwh(self) -> float:
        return self.gross_annual_thermal_loss_mwh * (
            1.0 - self.fixed_loss_compensation_fraction
        )

    @property
    def net_capacity_normalized_loss_fraction_per_hour(self) -> float:
        """Capacity-normalized screening intensity after fixed compensation."""

        return (
            self.net_annual_thermal_loss_mwh
            / self.thermal_capacity_mwh
            / self.annual_hours
        )

    @property
    def pump_electricity_target_mwh(self) -> float:
        return self.annual_electricity_consumption_mwh * self.pump_electricity_fraction

    def aggregate_implied_uniform_pump_spec(
        self,
        *,
        total_salt_throughput_t: float,
    ) -> TESPumpAuxiliarySpec:
        """Infer a uniform coefficient from an aggregate after throughput is known.

        This is an aggregate-implied audit quantity, not a bottom-up hydraulic
        coefficient. The publication does not identify the five Yangling paths.
        """

        _require_finite_positive(total_salt_throughput_t, "total salt throughput")
        specific_energy = (
            self.pump_electricity_target_mwh * 1000.0 / total_salt_throughput_t
        )
        return TESPumpAuxiliarySpec(
            electric_lt_to_ht_kwh_per_tonne=specific_energy,
            steam_lt_to_ht_kwh_per_tonne=specific_energy,
            steam_lt_to_mt_kwh_per_tonne=specific_energy,
            power_ht_to_mt_kwh_per_tonne=specific_energy,
            heat_mt_to_lt_kwh_per_tonne=specific_energy,
        )


@dataclass(frozen=True)
class TESDailyRetentionAnchor:
    """A published full-charge daily retention quantity."""

    source_doi: str
    full_charge_retention: float
    hold_hours: int
    basis: str

    def __post_init__(self) -> None:
        if not self.source_doi.startswith("10."):
            raise ValueError("daily retention anchor requires a DOI source")
        if not math.isfinite(self.full_charge_retention) or not (
            0.0 < self.full_charge_retention <= 1.0
        ):
            raise ValueError("full-charge retention must lie in (0, 1]")
        if (
            isinstance(self.hold_hours, bool)
            or not isinstance(self.hold_hours, int)
            or self.hold_hours < 2
        ):
            raise ValueError("hold_hours must be an integer of at least two")
        if not self.basis.strip():
            raise ValueError("daily retention basis is required")

    @property
    def equivalent_uniform_hourly_loss_fraction(self) -> float:
        """Equivalent one-state hourly rate, reported only as an audit quantity."""

        return 1.0 - self.full_charge_retention ** (1.0 / self.hold_hours)


class E0D9BLossLevel(str, Enum):
    """Pre-registered author screening levels."""

    LOW = "low"
    BASE = "base"
    HIGH = "high"


@dataclass(frozen=True)
class E0D9BLossScenario:
    """One aggregate target before conversion to an MT-specific flow rate."""

    level: E0D9BLossLevel
    target_full_charge_retention: float
    hold_hours: int
    loss_compensation_fraction: float
    parameter_source_id: str
    evidence_source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.level, E0D9BLossLevel):
            raise TypeError("level must use E0D9BLossLevel")
        if not math.isfinite(self.target_full_charge_retention) or not (
            0.0 < self.target_full_charge_retention <= 1.0
        ):
            raise ValueError("target full-charge retention must lie in (0, 1]")
        if (
            isinstance(self.hold_hours, bool)
            or not isinstance(self.hold_hours, int)
            or self.hold_hours < 2
        ):
            raise ValueError("hold_hours must be an integer of at least two")
        if not math.isfinite(self.loss_compensation_fraction) or not (
            0.0 <= self.loss_compensation_fraction < 1.0
        ):
            raise ValueError("loss compensation fraction must lie in [0, 1)")
        if not self.parameter_source_id.startswith("author:"):
            raise ValueError("E0-D-9B scenarios require an author: value source")
        if not self.evidence_source_ids or any(
            not source.startswith("doi:10.") for source in self.evidence_source_ids
        ):
            raise ValueError("E0-D-9B evidence ids must be DOI-prefixed")


@dataclass(frozen=True)
class MTLossCalibration:
    """MT-specific rate that reproduces one common aggregate retention target."""

    scenario: E0D9BLossScenario
    mt_scenario_id: str
    temperature_lt_c: float
    temperature_mt_c: float
    temperature_ht_c: float
    net_hourly_downgrade_fraction: float
    raw_hourly_downgrade_fraction: float

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, E0D9BLossScenario):
            raise TypeError("scenario must be an E0D9BLossScenario")
        if not self.mt_scenario_id.strip():
            raise ValueError("MT scenario id is required")
        if not self.temperature_ht_c > self.temperature_mt_c > self.temperature_lt_c:
            raise ValueError("calibration temperatures must satisfy HT > MT > LT")
        for value, label in (
            (self.net_hourly_downgrade_fraction, "net hourly downgrade fraction"),
            (self.raw_hourly_downgrade_fraction, "raw hourly downgrade fraction"),
        ):
            if not math.isfinite(value) or not 0.0 <= value < 1.0:
                raise ValueError(f"{label} must lie in [0, 1)")


def build_trevisan_2022_aggregate_anchor() -> TESAggregateLossPumpAnchor:
    """Return Table-10/base-case aggregates in consistent MWh units."""

    return TESAggregateLossPumpAnchor(
        source_doi=TREVISAN_2022_DOI,
        thermal_capacity_mwh=45.0,
        gross_annual_thermal_loss_mwh=797.0,
        fixed_loss_compensation_fraction=0.734,
        annual_electricity_consumption_mwh=21_110.0,
        pump_electricity_fraction=0.005,
    )


def build_klasing_2025_daily_retention_anchor() -> TESDailyRetentionAnchor:
    """Return the published 99% full-charge, one-cycle-per-day anchor."""

    return TESDailyRetentionAnchor(
        source_doi=KLASING_2025_DOI,
        full_charge_retention=0.99,
        hold_hours=24,
        basis="fully charged storage; one cycle per day",
    )


def build_e0d9b_loss_scenarios() -> tuple[E0D9BLossScenario, ...]:
    """Build low/base/high author normalizations without claiming site values."""

    trevisan = build_trevisan_2022_aggregate_anchor()
    klasing = build_klasing_2025_daily_retention_anchor()
    hold_hours = klasing.hold_hours
    base_retention = 1.0 - (
        hold_hours * trevisan.net_capacity_normalized_loss_fraction_per_hour
    )
    high_retention = 1.0 - (
        hold_hours * trevisan.gross_capacity_normalized_loss_fraction_per_hour
    )
    trevisan_evidence = f"doi:{trevisan.source_doi}"
    klasing_evidence = f"doi:{klasing.source_doi}"
    return (
        E0D9BLossScenario(
            level=E0D9BLossLevel.LOW,
            target_full_charge_retention=klasing.full_charge_retention,
            hold_hours=hold_hours,
            loss_compensation_fraction=trevisan.fixed_loss_compensation_fraction,
            parameter_source_id=(
                "author:e0-d-9b-low-klasing-retention-trevisan-compensation-v1"
            ),
            evidence_source_ids=(klasing_evidence, trevisan_evidence),
        ),
        E0D9BLossScenario(
            level=E0D9BLossLevel.BASE,
            target_full_charge_retention=base_retention,
            hold_hours=hold_hours,
            loss_compensation_fraction=trevisan.fixed_loss_compensation_fraction,
            parameter_source_id=(
                "author:e0-d-9b-base-trevisan-net-capacity-normalization-v1"
            ),
            evidence_source_ids=(trevisan_evidence,),
        ),
        E0D9BLossScenario(
            level=E0D9BLossLevel.HIGH,
            target_full_charge_retention=high_retention,
            hold_hours=hold_hours,
            loss_compensation_fraction=0.0,
            parameter_source_id=(
                "author:e0-d-9b-high-trevisan-uncompensated-stress-v1"
            ),
            evidence_source_ids=(trevisan_evidence,),
        ),
    )


def full_charge_retention(
    mt_point: MTScenarioPoint,
    *,
    net_hourly_downgrade_fraction: float,
    hold_hours: int,
) -> float:
    """Return discrete two-stage stored-energy retention after an hourly hold.

    All salt starts in HT. A common net fraction downgrades HT to MT and MT to
    LT each hour. The MT enthalpy partition is therefore kept explicit.
    """

    if not isinstance(mt_point, MTScenarioPoint):
        raise TypeError("mt_point must be an MTScenarioPoint")
    if not math.isfinite(net_hourly_downgrade_fraction) or not (
        0.0 <= net_hourly_downgrade_fraction < 1.0
    ):
        raise ValueError("net hourly downgrade fraction must lie in [0, 1)")
    if (
        isinstance(hold_hours, bool)
        or not isinstance(hold_hours, int)
        or hold_hours < 2
    ):
        raise ValueError("hold_hours must be an integer of at least two")

    retained = 1.0 - net_hourly_downgrade_fraction
    ht_mass_fraction = retained**hold_hours
    mt_mass_fraction = (
        hold_hours
        * net_hourly_downgrade_fraction
        * retained ** (hold_hours - 1)
    )
    return ht_mass_fraction + (
        mt_point.low_grade_enthalpy_fraction * mt_mass_fraction
    )


def solve_net_hourly_downgrade_fraction(
    mt_point: MTScenarioPoint,
    *,
    target_full_charge_retention: float,
    hold_hours: int,
    absolute_tolerance: float = 1e-14,
) -> float:
    """Solve the MT-specific net fraction by deterministic bisection."""

    if not math.isfinite(target_full_charge_retention) or not (
        0.0 < target_full_charge_retention <= 1.0
    ):
        raise ValueError("target full-charge retention must lie in (0, 1]")
    _require_finite_positive(absolute_tolerance, "absolute tolerance")
    if target_full_charge_retention == 1.0:
        return 0.0

    lower = 0.0
    upper = 1.0 - 1e-12
    for _ in range(200):
        midpoint = 0.5 * (lower + upper)
        retention = full_charge_retention(
            mt_point,
            net_hourly_downgrade_fraction=midpoint,
            hold_hours=hold_hours,
        )
        if retention > target_full_charge_retention:
            lower = midpoint
        else:
            upper = midpoint
        if upper - lower <= absolute_tolerance:
            break
    return 0.5 * (lower + upper)


def calibrate_loss_for_mt(
    scenario: E0D9BLossScenario,
    mt_point: MTScenarioPoint,
) -> MTLossCalibration:
    """Convert one aggregate author scenario to equal raw HT/MT hourly rates."""

    if not isinstance(scenario, E0D9BLossScenario):
        raise TypeError("scenario must be an E0D9BLossScenario")
    if not isinstance(mt_point, MTScenarioPoint):
        raise TypeError("mt_point must be an MTScenarioPoint")
    net_fraction = solve_net_hourly_downgrade_fraction(
        mt_point,
        target_full_charge_retention=scenario.target_full_charge_retention,
        hold_hours=scenario.hold_hours,
    )
    raw_fraction = net_fraction / (1.0 - scenario.loss_compensation_fraction)
    if raw_fraction >= 1.0:
        raise ValueError("calibrated raw hourly downgrade fraction is not physical")
    return MTLossCalibration(
        scenario=scenario,
        mt_scenario_id=mt_point.scenario_id,
        temperature_lt_c=mt_point.temperature_lt_c,
        temperature_mt_c=mt_point.temperature_mt_c,
        temperature_ht_c=mt_point.temperature_ht_c,
        net_hourly_downgrade_fraction=net_fraction,
        raw_hourly_downgrade_fraction=raw_fraction,
    )
