"""Linear endogenous-capacity kernels for BESS and three-state molten-salt TES.

The kernels are intentionally smaller than the complete E0 CHP/PCC model.  They
establish auditable design variables, fixed engineering Big-M bounds, state
balances, duration constraints, and annual capacity-cost expressions that can
be integrated into the full model without introducing variable-by-binary or
capacity-by-binary products.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from tes_bess_boundary.components.molten_salt import MoltenSaltPhysics
from tes_bess_boundary.public_tes_costs import PublicTESCostPortfolio
from tes_bess_boundary.tes_cost_mapping import TESCapacityBasis


def _finite_non_negative(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")


def _finite_positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class BESSPlanningBounds:
    """Finite engineering bounds used both for sizing and MILP disjunctions."""

    energy_capacity_upper_mwh: float
    charge_power_upper_mw: float
    discharge_power_upper_mw: float

    def __post_init__(self) -> None:
        _finite_positive(
            self.energy_capacity_upper_mwh,
            "energy_capacity_upper_mwh",
        )
        _finite_positive(self.charge_power_upper_mw, "charge_power_upper_mw")
        _finite_positive(
            self.discharge_power_upper_mw,
            "discharge_power_upper_mw",
        )


@dataclass(frozen=True)
class BESSPlanningSpec:
    """Endogenous BESS sizing and state-boundary assumptions."""

    bounds: BESSPlanningBounds
    soc_min: float
    soc_max: float
    charge_efficiency: float
    discharge_efficiency: float
    initial_soc_fraction: float
    hourly_loss: float = 0.0
    minimum_discharge_duration_hours: float = 2.0
    maximum_discharge_duration_hours: float = 24.0
    cyclic: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.bounds, BESSPlanningBounds):
            raise ValueError("bounds must be BESSPlanningBounds")
        if not 0.0 <= self.soc_min < self.soc_max <= 1.0:
            raise ValueError("SOC bounds must satisfy 0 <= min < max <= 1")
        if not self.soc_min <= self.initial_soc_fraction <= self.soc_max:
            raise ValueError("initial_soc_fraction must lie inside the SOC interval")
        for name, efficiency in (
            ("charge_efficiency", self.charge_efficiency),
            ("discharge_efficiency", self.discharge_efficiency),
        ):
            if not 0.0 < efficiency <= 1.0:
                raise ValueError(f"{name} must lie in (0, 1]")
        if not 0.0 <= self.hourly_loss < 1.0:
            raise ValueError("hourly_loss must lie in [0, 1)")
        _finite_positive(
            self.minimum_discharge_duration_hours,
            "minimum_discharge_duration_hours",
        )
        _finite_positive(
            self.maximum_discharge_duration_hours,
            "maximum_discharge_duration_hours",
        )
        if (
            self.minimum_discharge_duration_hours
            > self.maximum_discharge_duration_hours
        ):
            raise ValueError("BESS duration bounds are reversed")


@dataclass(frozen=True)
class BESSAnnualCapacityCost:
    """Annualized CNY coefficients on the three endogenous BESS capacities."""

    energy_cny_per_mwh_year: float = 0.0
    charge_power_cny_per_mw_year: float = 0.0
    discharge_power_cny_per_mw_year: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("energy_cny_per_mwh_year", self.energy_cny_per_mwh_year),
            ("charge_power_cny_per_mw_year", self.charge_power_cny_per_mw_year),
            ("discharge_power_cny_per_mw_year", self.discharge_power_cny_per_mw_year),
        ):
            _finite_non_negative(value, name)


def add_endogenous_bess_dispatch(
    block: object,
    periods: object,
    spec: BESSPlanningSpec,
    *,
    dt_hours: float = 1.0,
    annual_capacity_cost: BESSAnnualCapacityCost | None = None,
) -> object:
    """Attach a linear endogenous-capacity BESS model to a Pyomo block."""

    from pyomo.environ import Binary, Constraint, Expression, RangeSet, Var

    if not isinstance(spec, BESSPlanningSpec):
        raise ValueError("spec must be BESSPlanningSpec")
    _finite_positive(dt_hours, "dt_hours")
    period_values = tuple(periods)
    if not period_values:
        raise ValueError("at least one dispatch period is required")
    costs = annual_capacity_cost or BESSAnnualCapacityCost()
    if not isinstance(costs, BESSAnnualCapacityCost):
        raise ValueError("annual_capacity_cost must be BESSAnnualCapacityCost")

    bounds = spec.bounds
    block.states = RangeSet(0, len(period_values))
    block.steps = RangeSet(0, len(period_values) - 1)
    block.energy_capacity_mwh = Var(
        bounds=(0.0, bounds.energy_capacity_upper_mwh)
    )
    block.charge_power_capacity_mw = Var(
        bounds=(0.0, bounds.charge_power_upper_mw)
    )
    block.discharge_power_capacity_mw = Var(
        bounds=(0.0, bounds.discharge_power_upper_mw)
    )
    block.energy_mwh = Var(
        block.states,
        bounds=(0.0, spec.soc_max * bounds.energy_capacity_upper_mwh),
    )
    block.charge_ac_mw = Var(
        periods,
        bounds=(0.0, bounds.charge_power_upper_mw),
    )
    block.discharge_ac_mw = Var(
        periods,
        bounds=(0.0, bounds.discharge_power_upper_mw),
    )
    block.charge_mode = Var(periods, domain=Binary)

    block.energy_lower = Constraint(
        block.states,
        rule=lambda model, state: (
            model.energy_mwh[state] >= spec.soc_min * model.energy_capacity_mwh
        ),
    )
    block.energy_upper = Constraint(
        block.states,
        rule=lambda model, state: (
            model.energy_mwh[state] <= spec.soc_max * model.energy_capacity_mwh
        ),
    )
    block.initial_energy = Constraint(
        expr=(
            block.energy_mwh[0]
            == spec.initial_soc_fraction * block.energy_capacity_mwh
        )
    )
    loss_factor = (1.0 - spec.hourly_loss) ** dt_hours

    def energy_balance_rule(model: object, step: int) -> object:
        period = period_values[step]
        return model.energy_mwh[step + 1] == (
            loss_factor * model.energy_mwh[step]
            + spec.charge_efficiency * model.charge_ac_mw[period] * dt_hours
            - model.discharge_ac_mw[period]
            * dt_hours
            / spec.discharge_efficiency
        )

    block.energy_balance = Constraint(block.steps, rule=energy_balance_rule)
    block.charge_capacity_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.charge_ac_mw[period] <= model.charge_power_capacity_mw
        ),
    )
    block.discharge_capacity_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.discharge_ac_mw[period] <= model.discharge_power_capacity_mw
        ),
    )
    block.charge_mode_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.charge_ac_mw[period]
            <= bounds.charge_power_upper_mw * model.charge_mode[period]
        ),
    )
    block.discharge_mode_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.discharge_ac_mw[period]
            <= bounds.discharge_power_upper_mw * (1 - model.charge_mode[period])
        ),
    )
    usable_fraction = (spec.soc_max - spec.soc_min) * spec.discharge_efficiency
    block.minimum_duration = Constraint(
        expr=(
            usable_fraction * block.energy_capacity_mwh
            >= spec.minimum_discharge_duration_hours
            * block.discharge_power_capacity_mw
        )
    )
    block.maximum_duration = Constraint(
        expr=(
            usable_fraction * block.energy_capacity_mwh
            <= spec.maximum_discharge_duration_hours
            * block.discharge_power_capacity_mw
        )
    )
    if spec.cyclic:
        block.cyclic_energy = Constraint(
            expr=block.energy_mwh[len(period_values)] == block.energy_mwh[0]
        )
    block.annual_capacity_cost_cny = Expression(
        expr=(
            costs.energy_cny_per_mwh_year * block.energy_capacity_mwh
            + costs.charge_power_cny_per_mw_year
            * block.charge_power_capacity_mw
            + costs.discharge_power_cny_per_mw_year
            * block.discharge_power_capacity_mw
        )
    )
    return block


@dataclass(frozen=True)
class TESPlanningBounds:
    """Finite engineering bounds for the endogenous three-state TES."""

    salt_mass_upper_t: float
    ht_tank_capacity_upper_t: float
    mt_tank_capacity_upper_t: float
    lt_tank_capacity_upper_t: float
    electric_charge_input_upper_mw: float
    steam_to_ht_input_upper_mw: float
    steam_to_mt_input_upper_mw: float
    electric_output_upper_mw: float
    heat_output_upper_mw: float

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            _finite_positive(value, name)
        if any(
            tank_upper < self.salt_mass_upper_t
            for tank_upper in (
                self.ht_tank_capacity_upper_t,
                self.mt_tank_capacity_upper_t,
                self.lt_tank_capacity_upper_t,
            )
        ):
            raise ValueError("each state tank upper bound must hold all installed salt")


@dataclass(frozen=True)
class TESPlanningSpec:
    """Physics and service-duration policy for endogenous molten-salt TES."""

    physics_template: MoltenSaltPhysics
    bounds: TESPlanningBounds
    initial_inventory_fractions: tuple[float, float, float]
    minimum_service_duration_hours: float = 2.0
    maximum_service_duration_hours: float = 24.0
    cyclic: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.physics_template, MoltenSaltPhysics):
            raise ValueError("physics_template must be MoltenSaltPhysics")
        if not isinstance(self.bounds, TESPlanningBounds):
            raise ValueError("bounds must be TESPlanningBounds")
        if (
            not isinstance(self.initial_inventory_fractions, tuple)
            or len(self.initial_inventory_fractions) != 3
            or any(
                not math.isfinite(value) or value < 0.0
                for value in self.initial_inventory_fractions
            )
            or not math.isclose(
                math.fsum(self.initial_inventory_fractions),
                1.0,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            raise ValueError("initial inventory fractions must be non-negative and sum to one")
        _finite_positive(
            self.minimum_service_duration_hours,
            "minimum_service_duration_hours",
        )
        _finite_positive(
            self.maximum_service_duration_hours,
            "maximum_service_duration_hours",
        )
        if self.minimum_service_duration_hours > self.maximum_service_duration_hours:
            raise ValueError("TES duration bounds are reversed")


def _tes_quantity_expressions(block: object, physics: MoltenSaltPhysics) -> dict:
    return {
        TESCapacityBasis.SALT_INVENTORY_KG: block.salt_mass_t * 1_000.0,
        TESCapacityBasis.FULL_SENSIBLE_HEAT_KWH_TH: (
            block.salt_mass_t
            * physics.specific_heat_mwh_per_tonne_k
            * (physics.temperature_ht - physics.temperature_lt)
            * 1_000.0
        ),
        TESCapacityBasis.HT_TANK_CAPACITY_T: block.ht_tank_capacity_t,
        TESCapacityBasis.MT_TANK_CAPACITY_T: block.mt_tank_capacity_t,
        TESCapacityBasis.LT_TANK_CAPACITY_T: block.lt_tank_capacity_t,
        TESCapacityBasis.ELECTRIC_HEATER_INPUT_KW_EL: (
            block.electric_charge_input_capacity_mw * 1_000.0
        ),
        TESCapacityBasis.HIGH_GRADE_STEAM_HX_INPUT_KW_TH: (
            block.steam_to_ht_input_capacity_mw * 1_000.0
        ),
        TESCapacityBasis.MEDIUM_GRADE_STEAM_HX_INPUT_KW_TH: (
            block.steam_to_mt_input_capacity_mw * 1_000.0
        ),
        TESCapacityBasis.SALT_TO_STEAM_GENERATOR_INPUT_KW_TH: (
            block.electric_output_capacity_mw
            / physics.power_block_efficiency
            * 1_000.0
        ),
        TESCapacityBasis.HEAT_DELIVERY_HX_INPUT_KW_TH: (
            block.heat_output_capacity_mw
            / physics.heat_exchanger_efficiency
            * 1_000.0
        ),
        TESCapacityBasis.ELECTRIC_OUTPUT_KW_EL: (
            block.electric_output_capacity_mw * 1_000.0
        ),
        TESCapacityBasis.USEFUL_HEAT_OUTPUT_KW_TH: (
            block.heat_output_capacity_mw * 1_000.0
        ),
        TESCapacityBasis.SYSTEM_COUNT: 0.0,
    }


def add_endogenous_tes_dispatch(
    block: object,
    periods: object,
    spec: TESPlanningSpec,
    *,
    dt_hours: float = 1.0,
    cost_portfolio: PublicTESCostPortfolio | None = None,
) -> object:
    """Attach a linear endogenous TES kernel with five capacity-limited ports."""

    from pyomo.environ import Binary, Constraint, Expression, RangeSet, Var

    if not isinstance(spec, TESPlanningSpec):
        raise ValueError("spec must be TESPlanningSpec")
    _finite_positive(dt_hours, "dt_hours")
    period_values = tuple(periods)
    if not period_values:
        raise ValueError("at least one dispatch period is required")
    if cost_portfolio is not None:
        if not isinstance(cost_portfolio, PublicTESCostPortfolio):
            raise ValueError("cost_portfolio must be PublicTESCostPortfolio")
        if not cost_portfolio.public_sensitivity_ready:
            raise ValueError("public TES assumptions must be explicitly acknowledged")

    physics = spec.physics_template
    bounds = spec.bounds
    cp = physics.specific_heat_mwh_per_tonne_k
    full_delta = physics.temperature_ht - physics.temperature_lt
    block.states = RangeSet(0, len(period_values))
    block.steps = RangeSet(0, len(period_values) - 1)
    block.salt_mass_t = Var(bounds=(0.0, bounds.salt_mass_upper_t))
    block.ht_tank_capacity_t = Var(
        bounds=(0.0, bounds.ht_tank_capacity_upper_t)
    )
    block.mt_tank_capacity_t = Var(
        bounds=(0.0, bounds.mt_tank_capacity_upper_t)
    )
    block.lt_tank_capacity_t = Var(
        bounds=(0.0, bounds.lt_tank_capacity_upper_t)
    )
    block.electric_charge_input_capacity_mw = Var(
        bounds=(0.0, bounds.electric_charge_input_upper_mw)
    )
    block.steam_to_ht_input_capacity_mw = Var(
        bounds=(0.0, bounds.steam_to_ht_input_upper_mw)
    )
    block.steam_to_mt_input_capacity_mw = Var(
        bounds=(0.0, bounds.steam_to_mt_input_upper_mw)
    )
    block.electric_output_capacity_mw = Var(
        bounds=(0.0, bounds.electric_output_upper_mw)
    )
    block.heat_output_capacity_mw = Var(
        bounds=(0.0, bounds.heat_output_upper_mw)
    )
    block.ht_service_salt_mass_t = Var(bounds=(0.0, bounds.salt_mass_upper_t))
    block.mt_service_salt_mass_t = Var(bounds=(0.0, bounds.salt_mass_upper_t))

    block.ht_mass_t = Var(
        block.states,
        bounds=(0.0, bounds.ht_tank_capacity_upper_t),
    )
    block.mt_mass_t = Var(
        block.states,
        bounds=(0.0, bounds.mt_tank_capacity_upper_t),
    )
    block.lt_mass_t = Var(
        block.states,
        bounds=(0.0, bounds.lt_tank_capacity_upper_t),
    )
    flow_bounds = {
        "electric_lt_to_ht": min(
            bounds.salt_mass_upper_t / dt_hours,
            bounds.electric_charge_input_upper_mw
            * physics.electric_heater_efficiency
            / (cp * full_delta),
        ),
        "steam_lt_to_ht": min(
            bounds.salt_mass_upper_t / dt_hours,
            bounds.steam_to_ht_input_upper_mw
            * physics.steam_to_ht_efficiency
            / (cp * full_delta),
        ),
        "steam_lt_to_mt": min(
            bounds.salt_mass_upper_t / dt_hours,
            bounds.steam_to_mt_input_upper_mw
            * physics.steam_to_mt_efficiency
            / (cp * physics.delta_mt_lt),
        ),
        "power_ht_to_mt": min(
            bounds.salt_mass_upper_t / dt_hours,
            bounds.electric_output_upper_mw
            / (physics.power_block_efficiency * cp * physics.delta_ht_mt),
        ),
        "heat_mt_to_lt": min(
            bounds.salt_mass_upper_t / dt_hours,
            bounds.heat_output_upper_mw
            / (physics.heat_exchanger_efficiency * cp * physics.delta_mt_lt),
        ),
    }
    for name, upper in flow_bounds.items():
        setattr(block, name, Var(periods, bounds=(0.0, upper)))

    block.ht_receiving_mode = Var(periods, domain=Binary)
    block.mt_direct_charge_mode = Var(periods, domain=Binary)
    block.ht_receiving_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.electric_lt_to_ht[period] + model.steam_lt_to_ht[period]
            <= (
                flow_bounds["electric_lt_to_ht"]
                + flow_bounds["steam_lt_to_ht"]
            )
            * model.ht_receiving_mode[period]
        ),
    )
    block.ht_sending_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.power_ht_to_mt[period]
            <= flow_bounds["power_ht_to_mt"]
            * (1 - model.ht_receiving_mode[period])
        ),
    )
    block.mt_direct_charge_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.steam_lt_to_mt[period]
            <= flow_bounds["steam_lt_to_mt"]
            * model.mt_direct_charge_mode[period]
        ),
    )
    block.mt_heat_discharge_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.heat_mt_to_lt[period]
            <= flow_bounds["heat_mt_to_lt"]
            * (1 - model.mt_direct_charge_mode[period])
        ),
    )

    block.ht_state_capacity = Constraint(
        block.states,
        rule=lambda model, state: (
            model.ht_mass_t[state] <= model.ht_tank_capacity_t
        ),
    )
    block.mt_state_capacity = Constraint(
        block.states,
        rule=lambda model, state: (
            model.mt_mass_t[state] <= model.mt_tank_capacity_t
        ),
    )
    block.lt_state_capacity = Constraint(
        block.states,
        rule=lambda model, state: (
            model.lt_mass_t[state] <= model.lt_tank_capacity_t
        ),
    )
    block.ht_full_inventory_capacity = Constraint(
        expr=block.ht_tank_capacity_t >= block.salt_mass_t
    )
    block.mt_full_inventory_capacity = Constraint(
        expr=block.mt_tank_capacity_t >= block.salt_mass_t
    )
    block.lt_full_inventory_capacity = Constraint(
        expr=block.lt_tank_capacity_t >= block.salt_mass_t
    )
    block.total_mass = Constraint(
        block.states,
        rule=lambda model, state: (
            model.ht_mass_t[state]
            + model.mt_mass_t[state]
            + model.lt_mass_t[state]
            == model.salt_mass_t
        ),
    )
    initial_ht, initial_mt, initial_lt = spec.initial_inventory_fractions
    block.initial_ht = Constraint(
        expr=block.ht_mass_t[0] == initial_ht * block.salt_mass_t
    )
    block.initial_mt = Constraint(
        expr=block.mt_mass_t[0] == initial_mt * block.salt_mass_t
    )
    block.initial_lt = Constraint(
        expr=block.lt_mass_t[0] == initial_lt * block.salt_mass_t
    )

    def ht_balance_rule(model: object, step: int) -> object:
        period = period_values[step]
        return model.ht_mass_t[step + 1] == model.ht_mass_t[step] + dt_hours * (
            model.electric_lt_to_ht[period]
            + model.steam_lt_to_ht[period]
            - model.power_ht_to_mt[period]
        )

    def mt_balance_rule(model: object, step: int) -> object:
        period = period_values[step]
        return model.mt_mass_t[step + 1] == model.mt_mass_t[step] + dt_hours * (
            model.steam_lt_to_mt[period]
            + model.power_ht_to_mt[period]
            - model.heat_mt_to_lt[period]
        )

    def lt_balance_rule(model: object, step: int) -> object:
        period = period_values[step]
        return model.lt_mass_t[step + 1] + dt_hours * (
            model.electric_lt_to_ht[period]
            + model.steam_lt_to_ht[period]
            + model.steam_lt_to_mt[period]
            - model.heat_mt_to_lt[period]
        ) == model.lt_mass_t[step]

    block.ht_balance = Constraint(block.steps, rule=ht_balance_rule)
    block.mt_balance = Constraint(block.steps, rule=mt_balance_rule)
    block.lt_balance = Constraint(block.steps, rule=lt_balance_rule)
    block.electric_charge_input_mw = Expression(
        periods,
        rule=lambda model, period: (
            cp
            * full_delta
            * model.electric_lt_to_ht[period]
            / physics.electric_heater_efficiency
        ),
    )
    block.steam_to_ht_input_mw = Expression(
        periods,
        rule=lambda model, period: (
            cp
            * full_delta
            * model.steam_lt_to_ht[period]
            / physics.steam_to_ht_efficiency
        ),
    )
    block.steam_to_mt_input_mw = Expression(
        periods,
        rule=lambda model, period: (
            cp
            * physics.delta_mt_lt
            * model.steam_lt_to_mt[period]
            / physics.steam_to_mt_efficiency
        ),
    )
    block.electric_output_mw = Expression(
        periods,
        rule=lambda model, period: (
            physics.power_block_efficiency
            * cp
            * physics.delta_ht_mt
            * model.power_ht_to_mt[period]
        ),
    )
    block.heat_output_mw = Expression(
        periods,
        rule=lambda model, period: (
            physics.heat_exchanger_efficiency
            * cp
            * physics.delta_mt_lt
            * model.heat_mt_to_lt[period]
        ),
    )
    block.electric_charge_capacity_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.electric_charge_input_mw[period]
            <= model.electric_charge_input_capacity_mw
        ),
    )
    block.steam_to_ht_capacity_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.steam_to_ht_input_mw[period]
            <= model.steam_to_ht_input_capacity_mw
        ),
    )
    block.steam_to_mt_capacity_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.steam_to_mt_input_mw[period]
            <= model.steam_to_mt_input_capacity_mw
        ),
    )
    block.electric_output_capacity_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.electric_output_mw[period] <= model.electric_output_capacity_mw
        ),
    )
    block.heat_output_capacity_limit = Constraint(
        periods,
        rule=lambda model, period: (
            model.heat_output_mw[period] <= model.heat_output_capacity_mw
        ),
    )
    block.ht_service_mass_limit = Constraint(
        expr=block.ht_service_salt_mass_t <= block.salt_mass_t
    )
    block.mt_service_mass_limit = Constraint(
        expr=block.mt_service_salt_mass_t <= block.salt_mass_t
    )
    block.minimum_power_duration = Constraint(
        expr=(
            physics.power_block_efficiency
            * cp
            * physics.delta_ht_mt
            * block.ht_service_salt_mass_t
            >= spec.minimum_service_duration_hours
            * block.electric_output_capacity_mw
        )
    )
    block.maximum_power_duration = Constraint(
        expr=(
            physics.power_block_efficiency
            * cp
            * physics.delta_ht_mt
            * block.ht_service_salt_mass_t
            <= spec.maximum_service_duration_hours
            * block.electric_output_capacity_mw
        )
    )
    block.minimum_heat_duration = Constraint(
        expr=(
            physics.heat_exchanger_efficiency
            * cp
            * physics.delta_mt_lt
            * block.mt_service_salt_mass_t
            >= spec.minimum_service_duration_hours * block.heat_output_capacity_mw
        )
    )
    block.maximum_heat_duration = Constraint(
        expr=(
            physics.heat_exchanger_efficiency
            * cp
            * physics.delta_mt_lt
            * block.mt_service_salt_mass_t
            <= spec.maximum_service_duration_hours * block.heat_output_capacity_mw
        )
    )
    if spec.cyclic:
        final_state = len(period_values)
        block.cyclic_ht = Constraint(
            expr=block.ht_mass_t[final_state] == block.ht_mass_t[0]
        )
        block.cyclic_mt = Constraint(
            expr=block.mt_mass_t[final_state] == block.mt_mass_t[0]
        )
        block.cyclic_lt = Constraint(
            expr=block.lt_mass_t[final_state] == block.lt_mass_t[0]
        )

    quantity_expressions = _tes_quantity_expressions(block, physics)
    annual_cost_expression = 0.0
    if cost_portfolio is not None:
        for coefficient in cost_portfolio.annualized_coefficients():
            if (
                coefficient.item.basis is TESCapacityBasis.SYSTEM_COUNT
                and coefficient.total_eac_cny2024_per_unit_year != 0.0
            ):
                raise ValueError(
                    "non-zero system-count cost requires a separate installation binary"
                )
            annual_cost_expression += (
                coefficient.total_eac_cny2024_per_unit_year
                * quantity_expressions[coefficient.item.basis]
            )
    block.annual_capacity_cost_cny = Expression(expr=annual_cost_expression)
    return block
