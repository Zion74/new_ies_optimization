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
from tes_bess_boundary.tes_loss_auxiliary import TESLossAuxiliarySpec


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
    common_pcs_power_cny_per_mw_year: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("energy_cny_per_mwh_year", self.energy_cny_per_mwh_year),
            ("charge_power_cny_per_mw_year", self.charge_power_cny_per_mw_year),
            ("discharge_power_cny_per_mw_year", self.discharge_power_cny_per_mw_year),
            (
                "common_pcs_power_cny_per_mw_year",
                self.common_pcs_power_cny_per_mw_year,
            ),
        ):
            _finite_non_negative(value, name)


@dataclass(frozen=True)
class BESSPlanningEconomics:
    """Formal BESS linear coefficients for an endogenous common-PCS design.

    The Rahman evidence supports one AC PCS rating rather than independent
    charge- and discharge-side purchases.  The common rating therefore bounds
    both dispatch ports and is either absent or installed inside the disclosed
    source domain.
    """

    annual_capacity_cost: BESSAnnualCapacityCost
    cycle_cost_cny_per_ac_discharge_mwh: float
    variable_om_cny_per_ac_discharge_mwh: float
    reference_annual_ac_efc: float
    ac_deliverable_fraction: float
    minimum_installed_pcs_power_mw: float
    maximum_installed_pcs_power_mw: float
    source_id: str
    currency: str = "CNY"
    price_base_year: int = 2024

    def __post_init__(self) -> None:
        if not isinstance(self.annual_capacity_cost, BESSAnnualCapacityCost):
            raise ValueError("annual_capacity_cost must be BESSAnnualCapacityCost")
        for name, value in (
            (
                "cycle_cost_cny_per_ac_discharge_mwh",
                self.cycle_cost_cny_per_ac_discharge_mwh,
            ),
            (
                "variable_om_cny_per_ac_discharge_mwh",
                self.variable_om_cny_per_ac_discharge_mwh,
            ),
        ):
            _finite_non_negative(value, name)
        for name, value in (
            ("reference_annual_ac_efc", self.reference_annual_ac_efc),
            (
                "minimum_installed_pcs_power_mw",
                self.minimum_installed_pcs_power_mw,
            ),
            (
                "maximum_installed_pcs_power_mw",
                self.maximum_installed_pcs_power_mw,
            ),
        ):
            _finite_positive(value, name)
        if (
            self.minimum_installed_pcs_power_mw
            > self.maximum_installed_pcs_power_mw
        ):
            raise ValueError("BESS PCS source-domain bounds are reversed")
        if not 0.0 < self.ac_deliverable_fraction <= 1.0:
            raise ValueError("ac_deliverable_fraction must lie in (0, 1]")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must be non-empty")
        if self.currency != "CNY" or self.price_base_year != 2024:
            raise ValueError("BESS planning economics must use constant CNY2024")


def add_endogenous_bess_dispatch(
    block: object,
    periods: object,
    spec: BESSPlanningSpec,
    *,
    dt_hours: float = 1.0,
    annual_capacity_cost: BESSAnnualCapacityCost | None = None,
    planning_economics: BESSPlanningEconomics | None = None,
) -> object:
    """Attach a linear endogenous-capacity BESS model to a Pyomo block."""

    from pyomo.environ import Binary, Constraint, Expression, RangeSet, Var

    if not isinstance(spec, BESSPlanningSpec):
        raise ValueError("spec must be BESSPlanningSpec")
    _finite_positive(dt_hours, "dt_hours")
    period_values = tuple(periods)
    if not period_values:
        raise ValueError("at least one dispatch period is required")
    if annual_capacity_cost is not None and planning_economics is not None:
        raise ValueError(
            "provide annual_capacity_cost or planning_economics, not both"
        )
    if planning_economics is not None and not isinstance(
        planning_economics,
        BESSPlanningEconomics,
    ):
        raise ValueError("planning_economics must be BESSPlanningEconomics")
    costs = (
        planning_economics.annual_capacity_cost
        if planning_economics is not None
        else annual_capacity_cost or BESSAnnualCapacityCost()
    )
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
    if planning_economics is not None:
        block.installed = Var(domain=Binary)
        block.pcs_power_capacity_mw = Var(
            bounds=(0.0, planning_economics.maximum_installed_pcs_power_mw)
        )
        block.pcs_installed_lower = Constraint(
            expr=(
                block.pcs_power_capacity_mw
                >= planning_economics.minimum_installed_pcs_power_mw
                * block.installed
            )
        )
        block.pcs_installed_upper = Constraint(
            expr=(
                block.pcs_power_capacity_mw
                <= planning_economics.maximum_installed_pcs_power_mw
                * block.installed
            )
        )
        block.charge_uses_common_pcs = Constraint(
            expr=block.charge_power_capacity_mw <= block.pcs_power_capacity_mw
        )
        block.discharge_uses_common_pcs = Constraint(
            expr=block.discharge_power_capacity_mw <= block.pcs_power_capacity_mw
        )
        block.energy_requires_installation = Constraint(
            expr=(
                block.energy_capacity_mwh
                <= bounds.energy_capacity_upper_mwh * block.installed
            )
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
            + costs.common_pcs_power_cny_per_mw_year
            * (
                block.pcs_power_capacity_mw
                if planning_economics is not None
                else 0.0
            )
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
    loss_auxiliary: TESLossAuxiliarySpec | None = None,
    ambient_temperature_c: tuple[float, ...] | None = None,
    certify_rated_discharge: bool = True,
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
    if loss_auxiliary is not None and not isinstance(
        loss_auxiliary,
        TESLossAuxiliarySpec,
    ):
        raise ValueError("loss_auxiliary must be TESLossAuxiliarySpec")
    if ambient_temperature_c is not None:
        if (
            not isinstance(ambient_temperature_c, tuple)
            or len(ambient_temperature_c) != len(period_values)
            or any(not math.isfinite(value) for value in ambient_temperature_c)
        ):
            raise ValueError("ambient temperatures must align with dispatch periods")
    if not isinstance(certify_rated_discharge, bool):
        raise ValueError("certify_rated_discharge must be boolean")

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

    period_to_step = {period: step for step, period in enumerate(period_values)}
    if loss_auxiliary is None:
        block.raw_loss_ht_to_mt = Expression(
            periods,
            rule=lambda _model, _period: 0.0,
        )
        block.raw_loss_mt_to_lt = Expression(
            periods,
            rule=lambda _model, _period: 0.0,
        )
        block.compensated_loss_ht_to_mt = Expression(
            periods,
            rule=lambda _model, _period: 0.0,
        )
        block.compensated_loss_mt_to_lt = Expression(
            periods,
            rule=lambda _model, _period: 0.0,
        )
    else:
        ambient_values = ambient_temperature_c or (
            loss_auxiliary.reference_ambient_temperature_c,
        ) * len(period_values)
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
                * model.ht_mass_t[period_to_step[period]]
            ),
        )
        block.raw_loss_mt_to_lt = Expression(
            periods,
            rule=lambda model, period: (
                mt_loss_coefficients[period_to_step[period]]
                * model.mt_mass_t[period_to_step[period]]
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
            model.raw_loss_ht_to_mt[period]
            - model.compensated_loss_ht_to_mt[period]
        ),
    )
    block.loss_mt_to_lt = Expression(
        periods,
        rule=lambda model, period: (
            model.raw_loss_mt_to_lt[period]
            - model.compensated_loss_mt_to_lt[period]
        ),
    )

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
            - model.loss_ht_to_mt[period]
        )

    def mt_balance_rule(model: object, step: int) -> object:
        period = period_values[step]
        return model.mt_mass_t[step + 1] == model.mt_mass_t[step] + dt_hours * (
            model.steam_lt_to_mt[period]
            + model.power_ht_to_mt[period]
            + model.loss_ht_to_mt[period]
            - model.heat_mt_to_lt[period]
            - model.loss_mt_to_lt[period]
        )

    def lt_balance_rule(model: object, step: int) -> object:
        period = period_values[step]
        return model.lt_mass_t[step + 1] + dt_hours * (
            model.electric_lt_to_ht[period]
            + model.steam_lt_to_ht[period]
            + model.steam_lt_to_mt[period]
            - model.heat_mt_to_lt[period]
            - model.loss_mt_to_lt[period]
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
    if loss_auxiliary is None:
        block.tracing_auxiliary_mw = Expression(
            periods,
            rule=lambda _model, _period: 0.0,
        )
        block.pump_auxiliary_mw = Expression(
            periods,
            rule=lambda _model, _period: 0.0,
        )
    else:
        block.tracing_auxiliary_mw = Expression(
            periods,
            rule=lambda model, period: (
                cp
                * (
                    physics.delta_ht_mt
                    * model.compensated_loss_ht_to_mt[period]
                    + physics.delta_mt_lt
                    * model.compensated_loss_mt_to_lt[period]
                )
                / loss_auxiliary.tracing_heater_efficiency
            ),
        )
        pump = loss_auxiliary.pump
        block.pump_auxiliary_mw = Expression(
            periods,
            rule=lambda model, period: pump.electric_power_mw(
                electric_lt_to_ht_tph=model.electric_lt_to_ht[period],
                steam_lt_to_ht_tph=model.steam_lt_to_ht[period],
                steam_lt_to_mt_tph=model.steam_lt_to_mt[period],
                power_ht_to_mt_tph=model.power_ht_to_mt[period],
                heat_mt_to_lt_tph=model.heat_mt_to_lt[period],
            ),
        )
    block.auxiliary_power_mw = Expression(
        periods,
        rule=lambda model, period: (
            model.tracing_auxiliary_mw[period]
            + model.pump_auxiliary_mw[period]
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
    ht_charge_mass_rate_capacity = (
        block.electric_charge_input_capacity_mw
        * physics.electric_heater_efficiency
        / (cp * full_delta)
        + block.steam_to_ht_input_capacity_mw
        * physics.steam_to_ht_efficiency
        / (cp * full_delta)
    )
    direct_mt_charge_mass_rate_capacity = (
        block.steam_to_mt_input_capacity_mw
        * physics.steam_to_mt_efficiency
        / (cp * physics.delta_mt_lt)
    )
    ht_to_mt_mass_rate_capacity = (
        block.electric_output_capacity_mw
        / (physics.power_block_efficiency * cp * physics.delta_ht_mt)
    )
    block.ht_service_charge_reachability = Constraint(
        expr=(
            block.ht_service_salt_mass_t
            <= spec.maximum_service_duration_hours * ht_charge_mass_rate_capacity
        )
    )
    block.mt_service_charge_reachability_upstream = Constraint(
        expr=(
            block.mt_service_salt_mass_t
            <= spec.maximum_service_duration_hours
            * (direct_mt_charge_mass_rate_capacity + ht_charge_mass_rate_capacity)
        )
    )
    block.mt_service_charge_reachability_downstream = Constraint(
        expr=(
            block.mt_service_salt_mass_t
            <= spec.maximum_service_duration_hours
            * (direct_mt_charge_mass_rate_capacity + ht_to_mt_mass_rate_capacity)
        )
    )
    if certify_rated_discharge:
        test_step_count_float = spec.minimum_service_duration_hours / dt_hours
        test_step_count = int(round(test_step_count_float))
        if test_step_count <= 0 or not math.isclose(
            test_step_count_float,
            float(test_step_count),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "TES minimum service duration must contain an integer number of time steps"
            )
        block.rated_test_steps = RangeSet(0, test_step_count - 1)
        block.rated_test_states = RangeSet(0, test_step_count)

        block.ht_rated_ht_mass_t = Var(
            block.rated_test_states,
            bounds=(0.0, bounds.ht_tank_capacity_upper_t),
        )
        block.ht_rated_mt_mass_t = Var(
            block.rated_test_states,
            bounds=(0.0, bounds.mt_tank_capacity_upper_t),
        )
        block.ht_rated_lt_mass_t = Var(
            block.rated_test_states,
            bounds=(0.0, bounds.lt_tank_capacity_upper_t),
        )
        block.ht_rated_power_flow_tph = Var(
            block.rated_test_steps,
            bounds=(0.0, flow_bounds["power_ht_to_mt"]),
        )
        block.ht_rated_initial_ht = Constraint(
            expr=block.ht_rated_ht_mass_t[0] == block.ht_service_salt_mass_t
        )
        block.ht_rated_initial_mt = Constraint(
            expr=block.ht_rated_mt_mass_t[0] == 0.0
        )
        block.ht_rated_initial_lt = Constraint(
            expr=(
                block.ht_rated_lt_mass_t[0]
                == block.salt_mass_t - block.ht_service_salt_mass_t
            )
        )
        block.ht_rated_total_mass = Constraint(
            block.rated_test_states,
            rule=lambda model, state: (
                model.ht_rated_ht_mass_t[state]
                + model.ht_rated_mt_mass_t[state]
                + model.ht_rated_lt_mass_t[state]
                == model.salt_mass_t
            ),
        )
        block.ht_rated_ht_capacity = Constraint(
            block.rated_test_states,
            rule=lambda model, state: (
                model.ht_rated_ht_mass_t[state] <= model.ht_tank_capacity_t
            ),
        )
        block.ht_rated_mt_capacity = Constraint(
            block.rated_test_states,
            rule=lambda model, state: (
                model.ht_rated_mt_mass_t[state] <= model.mt_tank_capacity_t
            ),
        )
        block.ht_rated_lt_capacity = Constraint(
            block.rated_test_states,
            rule=lambda model, state: (
                model.ht_rated_lt_mass_t[state] <= model.lt_tank_capacity_t
            ),
        )
        block.ht_rated_output = Constraint(
            block.rated_test_steps,
            rule=lambda model, step: (
                physics.power_block_efficiency
                * cp
                * physics.delta_ht_mt
                * model.ht_rated_power_flow_tph[step]
                == model.electric_output_capacity_mw
            ),
        )
        if loss_auxiliary is None:
            rated_ht_loss_coefficient = 0.0
            rated_ht_uncompensated_fraction = 1.0
            ht_test_mt_loss_coefficient = 0.0
            ht_test_mt_uncompensated_fraction = 1.0
        else:
            rated_ht_loss_coefficient = loss_auxiliary.ht_loss_flow_coefficient(
                dt_hours=dt_hours,
                state_temperature_c=physics.temperature_ht,
                ambient_temperature_c=(
                    loss_auxiliary.reference_ambient_temperature_c
                ),
            )
            rated_ht_uncompensated_fraction = (
                1.0 - loss_auxiliary.ht_loss_compensation_fraction
            )
            ht_test_mt_loss_coefficient = loss_auxiliary.mt_loss_flow_coefficient(
                dt_hours=dt_hours,
                state_temperature_c=physics.temperature_mt,
                ambient_temperature_c=(
                    loss_auxiliary.reference_ambient_temperature_c
                ),
            )
            ht_test_mt_uncompensated_fraction = (
                1.0 - loss_auxiliary.mt_loss_compensation_fraction
            )

        def ht_rated_ht_balance(model: object, step: int) -> object:
            rated_loss = (
                rated_ht_loss_coefficient
                * rated_ht_uncompensated_fraction
                * model.ht_rated_ht_mass_t[step]
            )
            return model.ht_rated_ht_mass_t[step + 1] == (
                model.ht_rated_ht_mass_t[step]
                - dt_hours
                * (model.ht_rated_power_flow_tph[step] + rated_loss)
            )

        def ht_rated_mt_balance(model: object, step: int) -> object:
            rated_ht_loss = (
                rated_ht_loss_coefficient
                * rated_ht_uncompensated_fraction
                * model.ht_rated_ht_mass_t[step]
            )
            rated_mt_loss = (
                ht_test_mt_loss_coefficient
                * ht_test_mt_uncompensated_fraction
                * model.ht_rated_mt_mass_t[step]
            )
            return model.ht_rated_mt_mass_t[step + 1] == (
                model.ht_rated_mt_mass_t[step]
                + dt_hours
                * (
                    model.ht_rated_power_flow_tph[step]
                    + rated_ht_loss
                    - rated_mt_loss
                )
            )

        block.ht_rated_ht_balance = Constraint(
            block.rated_test_steps,
            rule=ht_rated_ht_balance,
        )
        block.ht_rated_mt_balance = Constraint(
            block.rated_test_steps,
            rule=ht_rated_mt_balance,
        )
        block.ht_rated_lt_balance = Constraint(
            block.rated_test_steps,
            rule=lambda model, step: (
                model.ht_rated_lt_mass_t[step + 1]
                == model.ht_rated_lt_mass_t[step]
                + dt_hours
                * ht_test_mt_loss_coefficient
                * ht_test_mt_uncompensated_fraction
                * model.ht_rated_mt_mass_t[step]
            ),
        )

        block.mt_rated_ht_mass_t = Var(
            block.rated_test_states,
            bounds=(0.0, bounds.ht_tank_capacity_upper_t),
        )
        block.mt_rated_mt_mass_t = Var(
            block.rated_test_states,
            bounds=(0.0, bounds.mt_tank_capacity_upper_t),
        )
        block.mt_rated_lt_mass_t = Var(
            block.rated_test_states,
            bounds=(0.0, bounds.lt_tank_capacity_upper_t),
        )
        block.mt_rated_heat_flow_tph = Var(
            block.rated_test_steps,
            bounds=(0.0, flow_bounds["heat_mt_to_lt"]),
        )
        block.mt_rated_initial_ht = Constraint(
            expr=block.mt_rated_ht_mass_t[0] == 0.0
        )
        block.mt_rated_initial_mt = Constraint(
            expr=block.mt_rated_mt_mass_t[0] == block.mt_service_salt_mass_t
        )
        block.mt_rated_initial_lt = Constraint(
            expr=(
                block.mt_rated_lt_mass_t[0]
                == block.salt_mass_t - block.mt_service_salt_mass_t
            )
        )
        block.mt_rated_total_mass = Constraint(
            block.rated_test_states,
            rule=lambda model, state: (
                model.mt_rated_ht_mass_t[state]
                + model.mt_rated_mt_mass_t[state]
                + model.mt_rated_lt_mass_t[state]
                == model.salt_mass_t
            ),
        )
        block.mt_rated_ht_capacity = Constraint(
            block.rated_test_states,
            rule=lambda model, state: (
                model.mt_rated_ht_mass_t[state] <= model.ht_tank_capacity_t
            ),
        )
        block.mt_rated_mt_capacity = Constraint(
            block.rated_test_states,
            rule=lambda model, state: (
                model.mt_rated_mt_mass_t[state] <= model.mt_tank_capacity_t
            ),
        )
        block.mt_rated_lt_capacity = Constraint(
            block.rated_test_states,
            rule=lambda model, state: (
                model.mt_rated_lt_mass_t[state] <= model.lt_tank_capacity_t
            ),
        )
        block.mt_rated_output = Constraint(
            block.rated_test_steps,
            rule=lambda model, step: (
                physics.heat_exchanger_efficiency
                * cp
                * physics.delta_mt_lt
                * model.mt_rated_heat_flow_tph[step]
                == model.heat_output_capacity_mw
            ),
        )
        if loss_auxiliary is None:
            rated_mt_loss_coefficient = 0.0
            rated_mt_uncompensated_fraction = 1.0
        else:
            rated_mt_loss_coefficient = loss_auxiliary.mt_loss_flow_coefficient(
                dt_hours=dt_hours,
                state_temperature_c=physics.temperature_mt,
                ambient_temperature_c=(
                    loss_auxiliary.reference_ambient_temperature_c
                ),
            )
            rated_mt_uncompensated_fraction = (
                1.0 - loss_auxiliary.mt_loss_compensation_fraction
            )

        def mt_rated_mt_balance(model: object, step: int) -> object:
            rated_loss = (
                rated_mt_loss_coefficient
                * rated_mt_uncompensated_fraction
                * model.mt_rated_mt_mass_t[step]
            )
            return model.mt_rated_mt_mass_t[step + 1] == (
                model.mt_rated_mt_mass_t[step]
                - dt_hours * (model.mt_rated_heat_flow_tph[step] + rated_loss)
            )

        def mt_rated_lt_balance(model: object, step: int) -> object:
            rated_loss = (
                rated_mt_loss_coefficient
                * rated_mt_uncompensated_fraction
                * model.mt_rated_mt_mass_t[step]
            )
            return model.mt_rated_lt_mass_t[step + 1] == (
                model.mt_rated_lt_mass_t[step]
                + dt_hours * (model.mt_rated_heat_flow_tph[step] + rated_loss)
            )

        block.mt_rated_ht_balance = Constraint(
            block.rated_test_steps,
            rule=lambda model, step: (
                model.mt_rated_ht_mass_t[step + 1]
                == model.mt_rated_ht_mass_t[step]
            ),
        )
        block.mt_rated_mt_balance = Constraint(
            block.rated_test_steps,
            rule=mt_rated_mt_balance,
        )
        block.mt_rated_lt_balance = Constraint(
            block.rated_test_steps,
            rule=mt_rated_lt_balance,
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
