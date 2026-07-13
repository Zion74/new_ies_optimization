"""Closed-form BESS physics on the PCC AC power basis."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BESSPhysics:
    energy_capacity_mwh: float
    charge_power_mw: float
    discharge_power_mw: float
    soc_min: float
    soc_max: float
    charge_efficiency: float
    discharge_efficiency: float
    hourly_loss: float = 0.0

    def __post_init__(self) -> None:
        numeric_values = (
            self.energy_capacity_mwh,
            self.charge_power_mw,
            self.discharge_power_mw,
            self.soc_min,
            self.soc_max,
            self.charge_efficiency,
            self.discharge_efficiency,
            self.hourly_loss,
        )
        if not all(math.isfinite(value) for value in numeric_values):
            raise ValueError("BESS parameters must be finite")
        if min(
            self.energy_capacity_mwh,
            self.charge_power_mw,
            self.discharge_power_mw,
        ) < 0:
            raise ValueError("BESS capacities must be non-negative")
        if not 0.0 <= self.soc_min < self.soc_max <= 1.0:
            raise ValueError("SOC bounds must satisfy 0 <= min < max <= 1")
        for name, efficiency in (
            ("charge_efficiency", self.charge_efficiency),
            ("discharge_efficiency", self.discharge_efficiency),
        ):
            if not 0.0 < efficiency <= 1.0:
                raise ValueError(f"{name} must lie in (0, 1]")
        if not 0.0 <= self.hourly_loss < 1.0:
            raise ValueError("hourly_loss must lie in [0, 1)")

    @property
    def internal_usable_energy_mwh(self) -> float:
        return (self.soc_max - self.soc_min) * self.energy_capacity_mwh

    @property
    def ac_deliverable_energy_mwh(self) -> float:
        return self.discharge_efficiency * self.internal_usable_energy_mwh

    @property
    def discharge_duration_hours(self) -> float:
        if self.discharge_power_mw == 0:
            return 0.0
        return self.ac_deliverable_energy_mwh / self.discharge_power_mw

    def step(
        self,
        stored_energy_mwh: float,
        charge_ac_mw: float,
        discharge_ac_mw: float,
        dt_hours: float,
        *,
        tolerance: float = 1e-9,
    ) -> float:
        if not all(
            math.isfinite(value)
            for value in (
                stored_energy_mwh,
                charge_ac_mw,
                discharge_ac_mw,
                dt_hours,
            )
        ):
            raise ValueError("BESS state, power, and time step must be finite")
        if dt_hours <= 0:
            raise ValueError("dt_hours must be positive")
        if charge_ac_mw < -tolerance or discharge_ac_mw < -tolerance:
            raise ValueError("charge and discharge powers must be non-negative")
        if charge_ac_mw > self.charge_power_mw + tolerance:
            raise ValueError("charge power exceeds installed capacity")
        if discharge_ac_mw > self.discharge_power_mw + tolerance:
            raise ValueError("discharge power exceeds installed capacity")
        if charge_ac_mw > tolerance and discharge_ac_mw > tolerance:
            raise ValueError("simultaneous charge and discharge is not allowed")

        minimum = self.soc_min * self.energy_capacity_mwh
        maximum = self.soc_max * self.energy_capacity_mwh
        if (
            stored_energy_mwh < minimum - tolerance
            or stored_energy_mwh > maximum + tolerance
        ):
            raise ValueError("initial stored energy violates SOC bounds")
        updated = (
            (1.0 - self.hourly_loss) ** dt_hours * stored_energy_mwh
            + self.charge_efficiency * charge_ac_mw * dt_hours
            - discharge_ac_mw * dt_hours / self.discharge_efficiency
        )
        if updated < minimum - tolerance or updated > maximum + tolerance:
            raise ValueError("updated stored energy violates SOC bounds")
        return updated


def add_bess_dispatch(
    block: object,
    periods: object,
    physics: BESSPhysics,
    *,
    initial_energy_mwh: float,
    dt_hours: float = 1.0,
    cyclic: bool = False,
) -> object:
    """Attach a fixed-capacity, linear BESS dispatch model to a Pyomo block."""

    from pyomo.environ import Binary, Constraint, RangeSet, Var

    period_values = tuple(periods)
    if not period_values:
        raise ValueError("at least one dispatch period is required")
    if dt_hours <= 0:
        raise ValueError("dt_hours must be positive")
    minimum_energy = physics.soc_min * physics.energy_capacity_mwh
    maximum_energy = physics.soc_max * physics.energy_capacity_mwh
    if not minimum_energy <= initial_energy_mwh <= maximum_energy:
        raise ValueError("initial energy violates SOC bounds")

    block.states = RangeSet(0, len(period_values))
    block.steps = RangeSet(0, len(period_values) - 1)
    block.energy = Var(block.states, bounds=(minimum_energy, maximum_energy))
    block.charge_ac = Var(
        periods,
        bounds=(0.0, physics.charge_power_mw),
    )
    block.discharge_ac = Var(
        periods,
        bounds=(0.0, physics.discharge_power_mw),
    )
    block.charge_mode = Var(periods, domain=Binary)
    block.energy[0].fix(initial_energy_mwh)

    loss_factor = (1.0 - physics.hourly_loss) ** dt_hours

    def energy_balance_rule(model: object, step: int) -> object:
        period = period_values[step]
        return model.energy[step + 1] == (
            loss_factor * model.energy[step]
            + physics.charge_efficiency * model.charge_ac[period] * dt_hours
            - model.discharge_ac[period] * dt_hours
            / physics.discharge_efficiency
        )

    block.energy_balance = Constraint(block.steps, rule=energy_balance_rule)
    block.charge_mode_limit = Constraint(
        periods,
        rule=lambda model, period: model.charge_ac[period]
        <= physics.charge_power_mw * model.charge_mode[period],
    )
    block.discharge_mode_limit = Constraint(
        periods,
        rule=lambda model, period: model.discharge_ac[period]
        <= physics.discharge_power_mw * (1 - model.charge_mode[period]),
    )
    if cyclic:
        block.cyclic_energy = Constraint(
            expr=block.energy[len(period_values)] == block.energy[0]
        )
    return block
