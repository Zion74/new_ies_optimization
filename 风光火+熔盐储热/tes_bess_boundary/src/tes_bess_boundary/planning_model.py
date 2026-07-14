"""Full CHP/PCC model adapter for endogenous BESS/TES capacity planning.

The adapter reuses the validated two-unit CHP, renewable, common-PCC, heat,
annual-service, and fuel-accounting blocks from :mod:`model`.  It replaces only
the fixed storage blocks and their constant ledgers with the linear planning
kernels.  Public TES costs remain sensitivity-only and can never certify the
Yangling project TAC.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from tes_bess_boundary.capacity_planning import (
    BESSPlanningEconomics,
    BESSPlanningSpec,
    TESPlanningSpec,
    add_endogenous_bess_dispatch,
    add_endogenous_tes_dispatch,
)
from tes_bess_boundary.components.chp import (
    CHPCommitmentSpec,
    CommitmentTransitionFormulation,
    FuelSegmentFormulation,
)
from tes_bess_boundary.economics import AnnualEconomicsSpec, AnnualHorizonSpec
from tes_bess_boundary.model import (
    AnnualCurtailmentServiceSpec,
    AnnualPCCExportServiceSpec,
    Architecture,
    E0CCase,
    E0CTimeSeries,
    ValidationObjectiveSpec,
    build_e0c_model,
)
from tes_bess_boundary.public_tes_costs import PublicTESCostPortfolio
from tes_bess_boundary.tes_loss_auxiliary import TESLossAuxiliarySpec


@dataclass(frozen=True)
class EndogenousCapacityCase:
    """One four-architecture annual planning case on the common E0 boundary."""

    architecture: Architecture
    timeseries: E0CTimeSeries
    chp_units: tuple[CHPCommitmentSpec, ...]
    chp_initial_online: tuple[int, ...]
    chp_terminal_online: tuple[int, ...]
    pcc_export_capacity_mw: float
    horizon: AnnualHorizonSpec
    bess: BESSPlanningSpec | None = None
    bess_economics: BESSPlanningEconomics | None = None
    tes: TESPlanningSpec | None = None
    tes_cost_portfolio: PublicTESCostPortfolio | None = None
    tes_loss_auxiliary: TESLossAuxiliarySpec | None = None
    objective: ValidationObjectiveSpec = field(default_factory=ValidationObjectiveSpec)
    curtailment_service: AnnualCurtailmentServiceSpec | None = None
    pcc_export_service: AnnualPCCExportServiceSpec | None = None
    chp_fuel_segment_formulation: FuelSegmentFormulation = (
        FuelSegmentFormulation.ONE_HOT
    )
    chp_transition_formulation: CommitmentTransitionFormulation = (
        CommitmentTransitionFormulation.BINARY
    )

    def __post_init__(self) -> None:
        if not isinstance(self.architecture, Architecture):
            raise ValueError("architecture must be selected with Architecture")
        if not isinstance(self.horizon, AnnualHorizonSpec):
            raise ValueError("horizon must be AnnualHorizonSpec")
        self.horizon.validate_time_grid(
            period_count=self.timeseries.period_count,
            dt_hours=self.timeseries.dt_hours,
        )
        if self.chp_terminal_online != self.chp_initial_online:
            raise ValueError("planning requires a closed CHP status boundary")
        includes_bess = self.architecture in (Architecture.BESS, Architecture.HYBRID)
        includes_tes = self.architecture in (Architecture.TES, Architecture.HYBRID)
        if includes_bess != (self.bess is not None):
            raise ValueError("architecture and endogenous BESS spec are inconsistent")
        if includes_bess != (self.bess_economics is not None):
            raise ValueError("architecture and BESS planning economics are inconsistent")
        if includes_tes != (self.tes is not None):
            raise ValueError("architecture and endogenous TES spec are inconsistent")
        if includes_tes != (self.tes_cost_portfolio is not None):
            raise ValueError("architecture and public TES cost portfolio are inconsistent")
        if not includes_tes and self.tes_loss_auxiliary is not None:
            raise ValueError("disabled TES architecture contains loss/auxiliary inputs")
        if self.bess is not None:
            if not self.bess.cyclic:
                raise ValueError("annual planning requires a cyclic BESS boundary")
            assert self.bess_economics is not None
            physical_fraction = self.bess.discharge_efficiency * (
                self.bess.soc_max - self.bess.soc_min
            )
            if not math.isclose(
                physical_fraction,
                self.bess_economics.ac_deliverable_fraction,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    "BESS planning economics must match the AC-deliverable physics"
                )
        if self.tes is not None:
            if not self.tes.cyclic:
                raise ValueError("annual planning requires a cyclic TES boundary")
            assert self.tes_cost_portfolio is not None
            if not self.tes_cost_portfolio.public_sensitivity_ready:
                raise ValueError("public TES assumptions must be explicitly acknowledged")

    @property
    def formal_project_tac_ready(self) -> bool:
        """The public TES path is never project-specific Yangling evidence."""

        return False


@dataclass(frozen=True)
class EndogenousCapacityResult:
    """Compact planning audit for one solved architecture."""

    architecture: Architecture
    termination_condition: str
    objective_lower_bound_cny: float
    objective_upper_bound_cny: float
    relative_mip_gap: float
    annual_total_cost_cny: float
    annual_operating_cost_cny: float
    annual_storage_capacity_cost_cny: float
    annual_bess_cycle_cost_cny: float
    annual_bess_variable_om_cost_cny: float
    weighted_fuel_tce: float
    weighted_curtailment_mwh: float
    weighted_pcc_export_mwh: float
    bess_energy_capacity_mwh: float | None
    bess_charge_power_capacity_mw: float | None
    bess_discharge_power_capacity_mw: float | None
    bess_common_pcs_power_capacity_mw: float | None
    bess_ac_discharge_throughput_mwh: float | None
    tes_salt_mass_t: float | None
    tes_electric_output_capacity_mw: float | None
    tes_heat_output_capacity_mw: float | None
    tes_auxiliary_mwh: float | None
    tes_public_cost_mode: str | None
    tes_public_cost_scenario: str | None
    formal_project_tac_ready: bool = False
    claim_scope: str = "controlled_public_cost_sensitivity_not_formal_project_tac"


def _nonnegative_solution_value(
    expression: object,
    *,
    name: str,
    tolerance: float = 1e-7,
) -> float:
    """Normalize solver negative zero while rejecting material violations."""

    from pyomo.environ import value

    solved_value = float(value(expression))
    if solved_value < -tolerance:
        raise RuntimeError(
            f"{name} violates its non-negative domain by {solved_value}"
        )
    return max(0.0, solved_value)


def _base_no_storage_case(case: EndogenousCapacityCase) -> E0CCase:
    return E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=case.timeseries,
        chp_units=case.chp_units,
        chp_initial_online=case.chp_initial_online,
        chp_terminal_online=case.chp_terminal_online,
        pcc_export_capacity_mw=case.pcc_export_capacity_mw,
        objective=case.objective,
        economics=AnnualEconomicsSpec(horizon=case.horizon),
        curtailment_service=case.curtailment_service,
        pcc_export_service=case.pcc_export_service,
        chp_fuel_segment_formulation=case.chp_fuel_segment_formulation,
        chp_transition_formulation=case.chp_transition_formulation,
    )


def build_endogenous_capacity_model(case: EndogenousCapacityCase) -> object:
    """Build one linear full-system capacity-and-dispatch MILP."""

    from pyomo.environ import Block, Constraint, Expression, Objective, minimize

    if not isinstance(case, EndogenousCapacityCase):
        raise ValueError("case must be EndogenousCapacityCase")
    model = build_e0c_model(_base_no_storage_case(case))
    model.name = f"e0_endogenous_{case.architecture.value}"

    if case.bess is not None:
        assert case.bess_economics is not None
        model.bess = Block()
        add_endogenous_bess_dispatch(
            model.bess,
            model.periods,
            case.bess,
            dt_hours=case.timeseries.dt_hours,
            planning_economics=case.bess_economics,
        )
    if case.tes is not None:
        assert case.tes_cost_portfolio is not None
        model.tes = Block()
        add_endogenous_tes_dispatch(
            model.tes,
            model.periods,
            case.tes,
            dt_hours=case.timeseries.dt_hours,
            cost_portfolio=case.tes_cost_portfolio,
            loss_auxiliary=case.tes_loss_auxiliary,
            ambient_temperature_c=case.timeseries.ambient_temperature_c,
            certify_rated_discharge=True,
        )

    model.pcc_balance.deactivate()
    model.heat_allocation.deactivate()
    model.heat_balance.deactivate()
    model.validation_cost.deactivate()

    model.planning_tes_auxiliary_mw = Expression(
        model.periods,
        rule=lambda block, period: (
            block.tes.auxiliary_power_mw[period]
            if hasattr(block, "tes")
            else 0.0
        ),
    )

    def pcc_balance_rule(block: object, period: int) -> object:
        bess_charge = (
            block.bess.charge_ac_mw[period] if hasattr(block, "bess") else 0.0
        )
        bess_discharge = (
            block.bess.discharge_ac_mw[period]
            if hasattr(block, "bess")
            else 0.0
        )
        tes_charge = (
            block.tes.electric_charge_input_mw[period]
            if hasattr(block, "tes")
            else 0.0
        )
        tes_output = (
            block.tes.electric_output_mw[period]
            if hasattr(block, "tes")
            else 0.0
        )
        return (
            block.pcc_export[period]
            + bess_charge
            + tes_charge
            + block.chp_auxiliary_total[period]
            + block.planning_tes_auxiliary_mw[period]
            == block.chp_gross_total[period]
            + block.wind_used[period]
            + block.pv_used[period]
            + bess_discharge
            + tes_output
        )

    model.planning_pcc_balance = Constraint(model.periods, rule=pcc_balance_rule)

    def heat_allocation_rule(block: object, period: int) -> object:
        tes_reference_charge = (
            block.tes.steam_to_ht_input_mw[period]
            + block.tes.steam_to_mt_input_mw[period]
            if hasattr(block, "tes")
            else 0.0
        )
        return (
            block.chp_heat_total[period]
            == block.direct_heat[period] + tes_reference_charge
        )

    def heat_balance_rule(block: object, period: int) -> object:
        tes_heat_output = (
            block.tes.heat_output_mw[period] if hasattr(block, "tes") else 0.0
        )
        return (
            block.direct_heat[period] + tes_heat_output
            == case.timeseries.heat_demand_mw[period]
        )

    model.planning_heat_allocation = Constraint(
        model.periods,
        rule=heat_allocation_rule,
    )
    model.planning_heat_balance = Constraint(
        model.periods,
        rule=heat_balance_rule,
    )
    model.planning_bess_capacity_cost_cny = Expression(
        expr=(
            model.bess.annual_capacity_cost_cny if hasattr(model, "bess") else 0.0
        )
    )
    model.planning_tes_capacity_cost_cny = Expression(
        expr=(
            model.tes.annual_capacity_cost_cny if hasattr(model, "tes") else 0.0
        )
    )
    model.planning_storage_capacity_cost_cny = Expression(
        expr=(
            model.planning_bess_capacity_cost_cny
            + model.planning_tes_capacity_cost_cny
        )
    )
    model.planning_bess_ac_discharge_throughput_mwh = Expression(
        expr=(
            case.timeseries.dt_hours
            * sum(
                model.annual_period_weight[period]
                * model.bess.discharge_ac_mw[period]
                for period in model.periods
            )
            if hasattr(model, "bess")
            else 0.0
        )
    )
    if case.bess_economics is not None:
        model.planning_bess_ac_throughput_limit_mwh = Expression(
            expr=(
                case.bess_economics.reference_annual_ac_efc
                * case.bess_economics.ac_deliverable_fraction
                * model.bess.energy_capacity_mwh
            )
        )
        model.planning_bess_ac_throughput_limit = Constraint(
            expr=(
                model.planning_bess_ac_discharge_throughput_mwh
                <= model.planning_bess_ac_throughput_limit_mwh
            )
        )
        cycle_coefficient = (
            case.bess_economics.cycle_cost_cny_per_ac_discharge_mwh
        )
        variable_om_coefficient = (
            case.bess_economics.variable_om_cny_per_ac_discharge_mwh
        )
    else:
        cycle_coefficient = 0.0
        variable_om_coefficient = 0.0
    model.planning_bess_cycle_cost_cny = Expression(
        expr=(
            cycle_coefficient
            * model.planning_bess_ac_discharge_throughput_mwh
        )
    )
    model.planning_bess_variable_om_cost_cny = Expression(
        expr=(
            variable_om_coefficient
            * model.planning_bess_ac_discharge_throughput_mwh
        )
    )
    model.planning_total_cost_cny = Expression(
        expr=(
            model.annual_operating_cost_cny
            + model.planning_storage_capacity_cost_cny
            + model.planning_bess_cycle_cost_cny
            + model.planning_bess_variable_om_cost_cny
        )
    )
    model.planning_cost = Objective(
        expr=model.planning_total_cost_cny,
        sense=minimize,
    )
    return model


def solve_endogenous_capacity(
    case: EndogenousCapacityCase,
    *,
    solver: object | None = None,
) -> EndogenousCapacityResult:
    """Solve one architecture with HiGHS and return a capacity/cost audit."""

    from pyomo.environ import value

    from tes_bess_boundary.solver import create_highs_solver

    model = build_endogenous_capacity_model(case)
    active_solver = solver or create_highs_solver(threads=1, random_seed=0)
    solved = active_solver.solve(model)
    termination = str(solved.solver.termination_condition).lower()
    if "optimal" not in termination:
        raise RuntimeError(f"endogenous capacity solve did not converge: {termination}")
    objective_lower_bound = float(solved.problem.lower_bound)
    objective_upper_bound = float(solved.problem.upper_bound)
    relative_mip_gap = abs(objective_upper_bound - objective_lower_bound) / max(
        abs(objective_upper_bound),
        1e-12,
    )

    has_bess = hasattr(model, "bess")
    has_tes = hasattr(model, "tes")
    tes_auxiliary_mwh = None
    if has_tes:
        tes_auxiliary_mwh = float(
            value(
                case.timeseries.dt_hours
                * sum(
                    model.annual_period_weight[period]
                    * model.tes.auxiliary_power_mw[period]
                    for period in model.periods
                )
            )
        )
    portfolio = case.tes_cost_portfolio
    return EndogenousCapacityResult(
        architecture=case.architecture,
        termination_condition=termination,
        objective_lower_bound_cny=objective_lower_bound,
        objective_upper_bound_cny=objective_upper_bound,
        relative_mip_gap=relative_mip_gap,
        annual_total_cost_cny=float(value(model.planning_total_cost_cny)),
        annual_operating_cost_cny=float(value(model.annual_operating_cost_cny)),
        annual_storage_capacity_cost_cny=_nonnegative_solution_value(
            model.planning_storage_capacity_cost_cny,
            name="annual storage capacity cost",
            tolerance=1e-3,
        ),
        annual_bess_cycle_cost_cny=_nonnegative_solution_value(
            model.planning_bess_cycle_cost_cny,
            name="annual BESS cycle cost",
            tolerance=1e-3,
        ),
        annual_bess_variable_om_cost_cny=_nonnegative_solution_value(
            model.planning_bess_variable_om_cost_cny,
            name="annual BESS variable O&M cost",
            tolerance=1e-3,
        ),
        weighted_fuel_tce=float(value(model.annual_fuel_tce)),
        weighted_curtailment_mwh=float(value(model.annual_curtailment_mwh)),
        weighted_pcc_export_mwh=float(value(model.annual_pcc_export_mwh)),
        bess_energy_capacity_mwh=(
            _nonnegative_solution_value(
                model.bess.energy_capacity_mwh,
                name="BESS energy capacity",
            )
            if has_bess
            else None
        ),
        bess_charge_power_capacity_mw=(
            _nonnegative_solution_value(
                model.bess.charge_power_capacity_mw,
                name="BESS charge power capacity",
            )
            if has_bess
            else None
        ),
        bess_discharge_power_capacity_mw=(
            _nonnegative_solution_value(
                model.bess.discharge_power_capacity_mw,
                name="BESS discharge power capacity",
            )
            if has_bess
            else None
        ),
        bess_common_pcs_power_capacity_mw=(
            _nonnegative_solution_value(
                model.bess.pcs_power_capacity_mw,
                name="BESS common PCS capacity",
            )
            if has_bess
            else None
        ),
        bess_ac_discharge_throughput_mwh=(
            float(value(model.planning_bess_ac_discharge_throughput_mwh))
            if has_bess
            else None
        ),
        tes_salt_mass_t=(
            _nonnegative_solution_value(
                model.tes.salt_mass_t,
                name="TES salt mass",
            )
            if has_tes
            else None
        ),
        tes_electric_output_capacity_mw=(
            _nonnegative_solution_value(
                model.tes.electric_output_capacity_mw,
                name="TES electric output capacity",
            )
            if has_tes
            else None
        ),
        tes_heat_output_capacity_mw=(
            _nonnegative_solution_value(
                model.tes.heat_output_capacity_mw,
                name="TES heat output capacity",
            )
            if has_tes
            else None
        ),
        tes_auxiliary_mwh=tes_auxiliary_mwh,
        tes_public_cost_mode=(portfolio.mode.value if portfolio is not None else None),
        tes_public_cost_scenario=(
            portfolio.scenario.value if portfolio is not None else None
        ),
    )
