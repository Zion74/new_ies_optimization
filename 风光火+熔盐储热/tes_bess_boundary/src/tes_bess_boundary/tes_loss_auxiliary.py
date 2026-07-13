"""Auditable linear TES standing-loss, tracing, and pump assumptions."""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from enum import Enum


class LossCompensationMode(str, Enum):
    """Whether standing heat leakage is electrically replaced."""

    UNCOMPENSATED = "uncompensated"
    FIXED_FRACTION = "fixed_fraction"


class TESParameterIdentity(str, Enum):
    """Identity of the numerical values, separate from supporting evidence."""

    SITE_PRIMARY = "site_primary"
    CORE_PAPER_DIRECT = "core_paper_direct"
    AUTHOR_SENSITIVITY = "author_sensitivity"


@dataclass(frozen=True)
class TESPumpAuxiliarySpec:
    """Specific pump electricity on each salt path, in kWh_e per tonne."""

    electric_lt_to_ht_kwh_per_tonne: float
    steam_lt_to_ht_kwh_per_tonne: float
    steam_lt_to_mt_kwh_per_tonne: float
    power_ht_to_mt_kwh_per_tonne: float
    heat_mt_to_lt_kwh_per_tonne: float

    def __post_init__(self) -> None:
        values = tuple(getattr(self, field.name) for field in fields(self))
        if not all(math.isfinite(value) for value in values):
            raise ValueError("TES pump coefficients must be finite")
        if any(value < 0.0 for value in values):
            raise ValueError("TES pump coefficients must be non-negative")

    def electric_power_mw(
        self,
        *,
        electric_lt_to_ht_tph: object,
        steam_lt_to_ht_tph: object,
        steam_lt_to_mt_tph: object,
        power_ht_to_mt_tph: object,
        heat_mt_to_lt_tph: object,
    ) -> object:
        """Return MW_e; 0.001 converts kWh/t times t/h from kW to MW."""

        return 0.001 * (
            self.electric_lt_to_ht_kwh_per_tonne * electric_lt_to_ht_tph
            + self.steam_lt_to_ht_kwh_per_tonne * steam_lt_to_ht_tph
            + self.steam_lt_to_mt_kwh_per_tonne * steam_lt_to_mt_tph
            + self.power_ht_to_mt_kwh_per_tonne * power_ht_to_mt_tph
            + self.heat_mt_to_lt_kwh_per_tonne * heat_mt_to_lt_tph
        )


@dataclass(frozen=True)
class TESSaltPathThroughput:
    """Integrated salt mass on the five public TES paths, in tonnes."""

    electric_lt_to_ht_t: float = 0.0
    steam_lt_to_ht_t: float = 0.0
    steam_lt_to_mt_t: float = 0.0
    power_ht_to_mt_t: float = 0.0
    heat_mt_to_lt_t: float = 0.0

    def __post_init__(self) -> None:
        values = tuple(getattr(self, field.name) for field in fields(self))
        if not all(math.isfinite(value) for value in values):
            raise ValueError("TES path throughputs must be finite")
        if any(value < 0.0 for value in values):
            raise ValueError("TES path throughputs must be non-negative")

    @property
    def total_t(self) -> float:
        return sum(getattr(self, field.name) for field in fields(self))

    def pump_energy_mwh(self, pump: TESPumpAuxiliarySpec) -> float:
        """Return path-specific pump electricity for the integrated masses."""

        if not isinstance(pump, TESPumpAuxiliarySpec):
            raise TypeError("pump must be a TESPumpAuxiliarySpec")
        return 0.001 * (
            pump.electric_lt_to_ht_kwh_per_tonne * self.electric_lt_to_ht_t
            + pump.steam_lt_to_ht_kwh_per_tonne * self.steam_lt_to_ht_t
            + pump.steam_lt_to_mt_kwh_per_tonne * self.steam_lt_to_mt_t
            + pump.power_ht_to_mt_kwh_per_tonne * self.power_ht_to_mt_t
            + pump.heat_mt_to_lt_kwh_per_tonne * self.heat_mt_to_lt_t
        )


@dataclass(frozen=True)
class TESLossAuxiliarySpec:
    """Linearized three-tank loss and auxiliary-electricity contract.

    Hourly loss fractions are effective values at the disclosed reference
    ambient temperature. They are converted to an interval-equivalent linear
    flow coefficient so non-unit time steps preserve compounded retention.
    """

    ht_standing_loss_fraction_per_hour: float
    mt_standing_loss_fraction_per_hour: float
    ht_loss_compensation_fraction: float
    mt_loss_compensation_fraction: float
    tracing_heater_efficiency: float
    pump: TESPumpAuxiliarySpec
    compensation_mode: LossCompensationMode
    parameter_identity: TESParameterIdentity
    parameter_source_id: str
    evidence_source_ids: tuple[str, ...]
    reference_ambient_temperature_c: float

    def __post_init__(self) -> None:
        if not isinstance(self.pump, TESPumpAuxiliarySpec):
            raise TypeError("pump must be a TESPumpAuxiliarySpec")
        if not isinstance(self.compensation_mode, LossCompensationMode):
            raise TypeError("compensation_mode must be a LossCompensationMode")
        if not isinstance(self.parameter_identity, TESParameterIdentity):
            raise TypeError("parameter_identity must be a TESParameterIdentity")
        fractions = (
            self.ht_standing_loss_fraction_per_hour,
            self.mt_standing_loss_fraction_per_hour,
        )
        if not all(math.isfinite(value) and 0.0 <= value < 1.0 for value in fractions):
            raise ValueError("hourly TES standing-loss fractions must lie in [0, 1)")
        compensation = (
            self.ht_loss_compensation_fraction,
            self.mt_loss_compensation_fraction,
        )
        if not all(
            math.isfinite(value) and 0.0 <= value <= 1.0 for value in compensation
        ):
            raise ValueError("TES loss-compensation fractions must lie in [0, 1]")
        if not math.isfinite(self.tracing_heater_efficiency) or not (
            0.0 < self.tracing_heater_efficiency <= 1.0
        ):
            raise ValueError("tracing heater efficiency must lie in (0, 1]")
        if not math.isfinite(self.reference_ambient_temperature_c):
            raise ValueError("reference ambient temperature must be finite")
        if self.compensation_mode is LossCompensationMode.UNCOMPENSATED and any(
            value != 0.0 for value in compensation
        ):
            raise ValueError("UNCOMPENSATED mode requires zero compensation fractions")
        if not self.parameter_source_id.strip():
            raise ValueError("TES loss/auxiliary parameter source id is required")
        if not self.evidence_source_ids or any(
            not source.strip() for source in self.evidence_source_ids
        ):
            raise ValueError(
                "at least one non-empty TES evidence source id is required"
            )
        if (
            self.parameter_identity is TESParameterIdentity.AUTHOR_SENSITIVITY
            and not self.parameter_source_id.startswith("author:")
        ):
            raise ValueError(
                "author sensitivity values require an author: value source id"
            )

    @staticmethod
    def _interval_flow_coefficient(
        hourly_fraction: float,
        dt_hours: float,
        temperature_scale: float = 1.0,
    ) -> float:
        if not math.isfinite(dt_hours) or dt_hours <= 0.0:
            raise ValueError("dt_hours must be finite and positive")
        if not math.isfinite(temperature_scale) or temperature_scale < 0.0:
            raise ValueError("temperature scale must be finite and non-negative")
        return (
            1.0 - (1.0 - hourly_fraction) ** (dt_hours * temperature_scale)
        ) / dt_hours

    def _temperature_scale(
        self,
        *,
        state_temperature_c: float | None,
        ambient_temperature_c: float | None,
    ) -> float:
        if state_temperature_c is None and ambient_temperature_c is None:
            return 1.0
        if state_temperature_c is None or ambient_temperature_c is None:
            raise ValueError("state and ambient temperatures must be supplied together")
        if not all(
            math.isfinite(value)
            for value in (state_temperature_c, ambient_temperature_c)
        ):
            raise ValueError("state and ambient temperatures must be finite")
        reference_delta = state_temperature_c - self.reference_ambient_temperature_c
        if reference_delta <= 0.0:
            raise ValueError("state temperature must exceed the reference ambient")
        return max(0.0, state_temperature_c - ambient_temperature_c) / reference_delta

    def ht_loss_flow_coefficient(
        self,
        *,
        dt_hours: float,
        state_temperature_c: float | None = None,
        ambient_temperature_c: float | None = None,
    ) -> float:
        return self._interval_flow_coefficient(
            self.ht_standing_loss_fraction_per_hour,
            dt_hours,
            self._temperature_scale(
                state_temperature_c=state_temperature_c,
                ambient_temperature_c=ambient_temperature_c,
            ),
        )

    def mt_loss_flow_coefficient(
        self,
        *,
        dt_hours: float,
        state_temperature_c: float | None = None,
        ambient_temperature_c: float | None = None,
    ) -> float:
        return self._interval_flow_coefficient(
            self.mt_standing_loss_fraction_per_hour,
            dt_hours,
            self._temperature_scale(
                state_temperature_c=state_temperature_c,
                ambient_temperature_c=ambient_temperature_c,
            ),
        )
