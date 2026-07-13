"""Three-temperature molten-salt mass and enthalpy accounting."""

from __future__ import annotations

import math
from dataclasses import dataclass, fields

from tes_bess_boundary.tes_loss_auxiliary import TESLossAuxiliarySpec


@dataclass(frozen=True)
class SaltInventory:
    ht_mass_t: float
    mt_mass_t: float
    lt_mass_t: float

    @property
    def total_mass_t(self) -> float:
        return self.ht_mass_t + self.mt_mass_t + self.lt_mass_t


@dataclass(frozen=True)
class MoltenSaltFlows:
    electric_lt_to_ht_tph: float = 0.0
    steam_lt_to_ht_tph: float = 0.0
    steam_lt_to_mt_tph: float = 0.0
    power_ht_to_mt_tph: float = 0.0
    heat_mt_to_lt_tph: float = 0.0
    loss_ht_to_mt_tph: float = 0.0
    loss_mt_to_lt_tph: float = 0.0

    def __post_init__(self) -> None:
        if any(getattr(self, field.name) < 0 for field in fields(self)):
            raise ValueError("molten-salt path flows must be non-negative")


@dataclass(frozen=True)
class MoltenSaltPhysics:
    salt_mass_t: float
    ht_tank_capacity_t: float
    mt_tank_capacity_t: float
    lt_tank_capacity_t: float
    specific_heat_mwh_per_tonne_k: float
    temperature_ht: float
    temperature_mt: float
    temperature_lt: float
    electric_heater_efficiency: float
    steam_to_ht_efficiency: float
    steam_to_mt_efficiency: float
    power_block_efficiency: float
    heat_exchanger_efficiency: float

    def __post_init__(self) -> None:
        if (
            min(
                self.salt_mass_t,
                self.ht_tank_capacity_t,
                self.mt_tank_capacity_t,
                self.lt_tank_capacity_t,
            )
            < 0
        ):
            raise ValueError("salt mass and tank capacities must be non-negative")
        if self.specific_heat_mwh_per_tonne_k <= 0:
            raise ValueError("specific heat must be positive")
        if not self.temperature_ht > self.temperature_mt > self.temperature_lt:
            raise ValueError("temperature order must satisfy HT > MT > LT")
        for name, efficiency in (
            ("electric_heater_efficiency", self.electric_heater_efficiency),
            ("steam_to_ht_efficiency", self.steam_to_ht_efficiency),
            ("steam_to_mt_efficiency", self.steam_to_mt_efficiency),
            ("power_block_efficiency", self.power_block_efficiency),
            ("heat_exchanger_efficiency", self.heat_exchanger_efficiency),
        ):
            if not 0.0 < efficiency <= 1.0:
                raise ValueError(f"{name} must lie in (0, 1]")

    @property
    def delta_ht_mt(self) -> float:
        return self.temperature_ht - self.temperature_mt

    @property
    def delta_mt_lt(self) -> float:
        return self.temperature_mt - self.temperature_lt

    def _validate_inventory(
        self,
        inventory: SaltInventory,
        *,
        tolerance: float = 1e-9,
    ) -> None:
        masses = (inventory.ht_mass_t, inventory.mt_mass_t, inventory.lt_mass_t)
        capacities = (
            self.ht_tank_capacity_t,
            self.mt_tank_capacity_t,
            self.lt_tank_capacity_t,
        )
        if any(mass < -tolerance for mass in masses):
            raise ValueError("salt inventory cannot be negative")
        if any(
            mass > capacity + tolerance for mass, capacity in zip(masses, capacities)
        ):
            raise ValueError("salt inventory exceeds tank capacity")
        if abs(inventory.total_mass_t - self.salt_mass_t) > tolerance:
            raise ValueError("HT + MT + LT inventory must equal installed salt mass")

    def high_grade_energy_mwh(self, inventory: SaltInventory) -> float:
        self._validate_inventory(inventory)
        return (
            self.specific_heat_mwh_per_tonne_k * self.delta_ht_mt * inventory.ht_mass_t
        )

    def low_grade_energy_mwh(self, inventory: SaltInventory) -> float:
        self._validate_inventory(inventory)
        return (
            self.specific_heat_mwh_per_tonne_k
            * self.delta_mt_lt
            * (inventory.ht_mass_t + inventory.mt_mass_t)
        )

    def total_stored_energy_mwh(self, inventory: SaltInventory) -> float:
        return self.high_grade_energy_mwh(inventory) + self.low_grade_energy_mwh(
            inventory
        )

    def electric_output_mw(self, mass_flow_tph: float) -> float:
        if mass_flow_tph < 0:
            raise ValueError("mass flow must be non-negative")
        return (
            self.power_block_efficiency
            * self.specific_heat_mwh_per_tonne_k
            * self.delta_ht_mt
            * mass_flow_tph
        )

    def electric_charge_input_mw(self, mass_flow_tph: float) -> float:
        if mass_flow_tph < 0:
            raise ValueError("mass flow must be non-negative")
        thermal_rate = (
            self.specific_heat_mwh_per_tonne_k
            * (self.temperature_ht - self.temperature_lt)
            * mass_flow_tph
        )
        return thermal_rate / self.electric_heater_efficiency

    def steam_to_ht_input_mw(self, mass_flow_tph: float) -> float:
        if mass_flow_tph < 0:
            raise ValueError("mass flow must be non-negative")
        thermal_rate = (
            self.specific_heat_mwh_per_tonne_k
            * (self.temperature_ht - self.temperature_lt)
            * mass_flow_tph
        )
        return thermal_rate / self.steam_to_ht_efficiency

    def steam_to_mt_input_mw(self, mass_flow_tph: float) -> float:
        if mass_flow_tph < 0:
            raise ValueError("mass flow must be non-negative")
        thermal_rate = (
            self.specific_heat_mwh_per_tonne_k * self.delta_mt_lt * mass_flow_tph
        )
        return thermal_rate / self.steam_to_mt_efficiency

    def heat_output_mw(self, mass_flow_tph: float) -> float:
        if mass_flow_tph < 0:
            raise ValueError("mass flow must be non-negative")
        return (
            self.heat_exchanger_efficiency
            * self.specific_heat_mwh_per_tonne_k
            * self.delta_mt_lt
            * mass_flow_tph
        )

    def step(
        self,
        inventory: SaltInventory,
        flows: MoltenSaltFlows,
        dt_hours: float,
    ) -> SaltInventory:
        if dt_hours <= 0:
            raise ValueError("dt_hours must be positive")
        self._validate_inventory(inventory)

        ht_mass = inventory.ht_mass_t + dt_hours * (
            flows.electric_lt_to_ht_tph
            + flows.steam_lt_to_ht_tph
            - flows.power_ht_to_mt_tph
            - flows.loss_ht_to_mt_tph
        )
        mt_mass = inventory.mt_mass_t + dt_hours * (
            flows.steam_lt_to_mt_tph
            + flows.power_ht_to_mt_tph
            + flows.loss_ht_to_mt_tph
            - flows.heat_mt_to_lt_tph
            - flows.loss_mt_to_lt_tph
        )
        lt_mass = self.salt_mass_t - ht_mass - mt_mass
        updated = SaltInventory(ht_mass, mt_mass, lt_mass)
        self._validate_inventory(updated)
        return updated


def add_molten_salt_dispatch(
    block: object,
    periods: object,
    physics: MoltenSaltPhysics,
    *,
    initial_inventory: SaltInventory,
    dt_hours: float = 1.0,
    cyclic: bool = False,
    loss_auxiliary: TESLossAuxiliarySpec | None = None,
    ambient_temperature_c: tuple[float, ...] | None = None,
) -> object:
    """Attach linear HT/MT/LT mass balances and allowed path flows."""

    from pyomo.environ import Binary, Constraint, Expression, RangeSet, Var

    physics._validate_inventory(initial_inventory)
    period_values = tuple(periods)
    if not period_values:
        raise ValueError("at least one dispatch period is required")
    if dt_hours <= 0:
        raise ValueError("dt_hours must be positive")
    if ambient_temperature_c is not None:
        if len(ambient_temperature_c) != len(period_values):
            raise ValueError(
                "ambient-temperature vector must align with dispatch periods"
            )
        if not all(math.isfinite(value) for value in ambient_temperature_c):
            raise ValueError("ambient temperatures must be finite")

    block.states = RangeSet(0, len(period_values))
    block.steps = RangeSet(0, len(period_values) - 1)
    block.ht_mass = Var(
        block.states,
        bounds=(0.0, physics.ht_tank_capacity_t),
    )
    block.mt_mass = Var(
        block.states,
        bounds=(0.0, physics.mt_tank_capacity_t),
    )
    block.lt_mass = Var(
        block.states,
        bounds=(0.0, physics.lt_tank_capacity_t),
    )
    flow_bound = physics.salt_mass_t / dt_hours
    for name in (
        "electric_lt_to_ht",
        "steam_lt_to_ht",
        "steam_lt_to_mt",
        "power_ht_to_mt",
        "heat_mt_to_lt",
    ):
        setattr(block, name, Var(periods, bounds=(0.0, flow_bound)))
    period_to_step = {period: step for step, period in enumerate(period_values)}
    if loss_auxiliary is None:
        block.raw_loss_ht_to_mt = Expression(periods, rule=lambda _model, _period: 0.0)
        block.raw_loss_mt_to_lt = Expression(periods, rule=lambda _model, _period: 0.0)
        block.compensated_loss_ht_to_mt = Expression(
            periods, rule=lambda _model, _period: 0.0
        )
        block.compensated_loss_mt_to_lt = Expression(
            periods, rule=lambda _model, _period: 0.0
        )
    else:
        ambient_values = (
            ambient_temperature_c
            if ambient_temperature_c is not None
            else (loss_auxiliary.reference_ambient_temperature_c,) * len(period_values)
        )
        ht_loss_coefficients = tuple(
            loss_auxiliary.ht_loss_flow_coefficient(
                dt_hours=dt_hours,
                state_temperature_c=physics.temperature_ht,
                ambient_temperature_c=ambient,
            )
            for ambient in ambient_values
        )
        mt_loss_coefficients = tuple(
            loss_auxiliary.mt_loss_flow_coefficient(
                dt_hours=dt_hours,
                state_temperature_c=physics.temperature_mt,
                ambient_temperature_c=ambient,
            )
            for ambient in ambient_values
        )
        block.raw_loss_ht_to_mt = Expression(
            periods,
            rule=lambda model, period: (
                ht_loss_coefficients[period_to_step[period]]
                * model.ht_mass[period_to_step[period]]
            ),
        )
        block.raw_loss_mt_to_lt = Expression(
            periods,
            rule=lambda model, period: (
                mt_loss_coefficients[period_to_step[period]]
                * model.mt_mass[period_to_step[period]]
            ),
        )
        block.compensated_loss_ht_to_mt = Expression(
            periods,
            rule=lambda model, period: (
                loss_auxiliary.ht_loss_compensation_fraction
                * model.raw_loss_ht_to_mt[period]
            ),
        )
        block.compensated_loss_mt_to_lt = Expression(
            periods,
            rule=lambda model, period: (
                loss_auxiliary.mt_loss_compensation_fraction
                * model.raw_loss_mt_to_lt[period]
            ),
        )
    block.loss_ht_to_mt = Expression(
        periods,
        rule=lambda model, period: (
            model.raw_loss_ht_to_mt[period] - model.compensated_loss_ht_to_mt[period]
        ),
    )
    block.loss_mt_to_lt = Expression(
        periods,
        rule=lambda model, period: (
            model.raw_loss_mt_to_lt[period] - model.compensated_loss_mt_to_lt[period]
        ),
    )
    block.ht_receiving_mode = Var(periods, domain=Binary)
    block.ht_receiving_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.electric_lt_to_ht[period] + model.steam_lt_to_ht[period]
            <= flow_bound * model.ht_receiving_mode[period]
        ),
    )
    block.ht_sending_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.power_ht_to_mt[period]
            <= flow_bound * (1 - model.ht_receiving_mode[period])
        ),
    )
    block.mt_direct_charge_mode = Var(periods, domain=Binary)
    block.mt_direct_charge_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.steam_lt_to_mt[period]
            <= flow_bound * model.mt_direct_charge_mode[period]
        ),
    )
    block.mt_heat_discharge_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.heat_mt_to_lt[period]
            <= flow_bound * (1 - model.mt_direct_charge_mode[period])
        ),
    )

    block.ht_mass[0].fix(initial_inventory.ht_mass_t)
    block.mt_mass[0].fix(initial_inventory.mt_mass_t)
    block.lt_mass[0].fix(initial_inventory.lt_mass_t)
    block.total_mass = Constraint(
        block.states,
        rule=lambda model, state: (
            model.ht_mass[state] + model.mt_mass[state] + model.lt_mass[state]
            == physics.salt_mass_t
        ),
    )

    def ht_balance_rule(model: object, step: int) -> object:
        period = period_values[step]
        return model.ht_mass[step + 1] == model.ht_mass[step] + dt_hours * (
            model.electric_lt_to_ht[period]
            + model.steam_lt_to_ht[period]
            - model.power_ht_to_mt[period]
            - model.loss_ht_to_mt[period]
        )

    def mt_balance_rule(model: object, step: int) -> object:
        period = period_values[step]
        return model.mt_mass[step + 1] == model.mt_mass[step] + dt_hours * (
            model.steam_lt_to_mt[period]
            + model.power_ht_to_mt[period]
            + model.loss_ht_to_mt[period]
            - model.heat_mt_to_lt[period]
            - model.loss_mt_to_lt[period]
        )

    def lt_balance_rule(model: object, step: int) -> object:
        period = period_values[step]
        return model.lt_mass[step + 1] == model.lt_mass[step] + dt_hours * (
            -model.electric_lt_to_ht[period]
            - model.steam_lt_to_ht[period]
            - model.steam_lt_to_mt[period]
            + model.heat_mt_to_lt[period]
            + model.loss_mt_to_lt[period]
        )

    block.ht_balance = Constraint(block.steps, rule=ht_balance_rule)
    block.mt_balance = Constraint(block.steps, rule=mt_balance_rule)
    block.lt_balance = Constraint(block.steps, rule=lt_balance_rule)
    block.electric_charge_input = Expression(
        periods,
        rule=lambda model, period: (
            physics.specific_heat_mwh_per_tonne_k
            * (physics.temperature_ht - physics.temperature_lt)
            * model.electric_lt_to_ht[period]
            / physics.electric_heater_efficiency
        ),
    )
    block.steam_to_ht_input = Expression(
        periods,
        rule=lambda model, period: (
            physics.specific_heat_mwh_per_tonne_k
            * (physics.temperature_ht - physics.temperature_lt)
            * model.steam_lt_to_ht[period]
            / physics.steam_to_ht_efficiency
        ),
    )
    block.steam_to_mt_input = Expression(
        periods,
        rule=lambda model, period: (
            physics.specific_heat_mwh_per_tonne_k
            * physics.delta_mt_lt
            * model.steam_lt_to_mt[period]
            / physics.steam_to_mt_efficiency
        ),
    )
    block.electric_output = Expression(
        periods,
        rule=lambda model, period: (
            physics.power_block_efficiency
            * physics.specific_heat_mwh_per_tonne_k
            * physics.delta_ht_mt
            * model.power_ht_to_mt[period]
        ),
    )
    block.heat_output = Expression(
        periods,
        rule=lambda model, period: (
            physics.heat_exchanger_efficiency
            * physics.specific_heat_mwh_per_tonne_k
            * physics.delta_mt_lt
            * model.heat_mt_to_lt[period]
        ),
    )
    if loss_auxiliary is None:
        block.tracing_auxiliary = Expression(periods, rule=lambda _model, _period: 0.0)
        block.pump_auxiliary = Expression(periods, rule=lambda _model, _period: 0.0)
    else:
        block.tracing_auxiliary = Expression(
            periods,
            rule=lambda model, period: (
                physics.specific_heat_mwh_per_tonne_k
                * (
                    physics.delta_ht_mt * model.compensated_loss_ht_to_mt[period]
                    + physics.delta_mt_lt * model.compensated_loss_mt_to_lt[period]
                )
                / loss_auxiliary.tracing_heater_efficiency
            ),
        )
        pump = loss_auxiliary.pump
        block.pump_auxiliary = Expression(
            periods,
            rule=lambda model, period: pump.electric_power_mw(
                electric_lt_to_ht_tph=model.electric_lt_to_ht[period],
                steam_lt_to_ht_tph=model.steam_lt_to_ht[period],
                steam_lt_to_mt_tph=model.steam_lt_to_mt[period],
                power_ht_to_mt_tph=model.power_ht_to_mt[period],
                heat_mt_to_lt_tph=model.heat_mt_to_lt[period],
            ),
        )
    block.auxiliary_power = Expression(
        periods,
        rule=lambda model, period: (
            model.tracing_auxiliary[period] + model.pump_auxiliary[period]
        ),
    )
    if cyclic:
        final_state = len(period_values)
        block.cyclic_ht = Constraint(
            expr=block.ht_mass[final_state] == block.ht_mass[0]
        )
        block.cyclic_mt = Constraint(
            expr=block.mt_mass[final_state] == block.mt_mass[0]
        )
        block.cyclic_lt = Constraint(
            expr=block.lt_mass[final_state] == block.lt_mass[0]
        )
    return block
