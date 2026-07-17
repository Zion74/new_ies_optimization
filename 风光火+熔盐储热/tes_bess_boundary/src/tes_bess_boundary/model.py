"""Unified fixed-capacity E0-C dispatch boundary for storage architectures."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from enum import Enum
from time import perf_counter

from tes_bess_boundary.components.bess import BESSPhysics
from tes_bess_boundary.components.bess import add_bess_dispatch
from tes_bess_boundary.components.chp import (
    CHPCommitmentSpec,
    CommitmentTransitionFormulation,
    FuelSegmentFormulation,
    HeatBasis,
    add_chp_unit_commitment,
)
from tes_bess_boundary.components.molten_salt import (
    MoltenSaltFlowBounds,
    MoltenSaltPhysics,
    SaltInventory,
)
from tes_bess_boundary.components.molten_salt import add_molten_salt_dispatch
from tes_bess_boundary.economics import (
    AnnualEconomicsSpec,
    BlockAnnualHorizonSpec,
    LifecycleAssetClass,
)
from tes_bess_boundary.tes_loss_auxiliary import (
    TESLossAuxiliarySpec,
    TESSaltPathThroughput,
)


class Architecture(str, Enum):
    """Storage blocks selected at Python model-construction time."""

    NO_STORAGE = "no_storage"
    BESS = "bess"
    TES = "tes"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class E0CTimeSeries:
    """Aligned deterministic hourly inputs on the common E0-C boundary."""

    heat_demand_mw: tuple[float, ...]
    wind_available_mw: tuple[float, ...]
    pv_available_mw: tuple[float, ...]
    dt_hours: float = 1.0
    ambient_temperature_c: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        lengths = {
            len(self.heat_demand_mw),
            len(self.wind_available_mw),
            len(self.pv_available_mw),
        }
        if len(lengths) != 1 or not self.heat_demand_mw:
            raise ValueError("time-series vectors must have the same non-zero length")
        values = (
            *self.heat_demand_mw,
            *self.wind_available_mw,
            *self.pv_available_mw,
        )
        if not all(math.isfinite(value) for value in (*values, self.dt_hours)):
            raise ValueError("time-series values and dt_hours must be finite")
        if any(value < 0.0 for value in values):
            raise ValueError("time-series values must be non-negative")
        if self.dt_hours <= 0.0:
            raise ValueError("dt_hours must be positive")
        if self.ambient_temperature_c is not None:
            if len(self.ambient_temperature_c) != len(self.heat_demand_mw):
                raise ValueError(
                    "ambient-temperature vector must align with time series"
                )
            if not all(math.isfinite(value) for value in self.ambient_temperature_c):
                raise ValueError("ambient temperatures must be finite")

    @property
    def period_count(self) -> int:
        return len(self.heat_demand_mw)


@dataclass(frozen=True)
class BESSFixedSpec:
    """Installed BESS physics and boundary state for one dispatch horizon."""

    physics: BESSPhysics
    initial_energy_mwh: float
    cyclic: bool = True

    def __post_init__(self) -> None:
        if not math.isfinite(self.initial_energy_mwh):
            raise ValueError("initial BESS energy must be finite")
        minimum = self.physics.soc_min * self.physics.energy_capacity_mwh
        maximum = self.physics.soc_max * self.physics.energy_capacity_mwh
        if not minimum <= self.initial_energy_mwh <= maximum:
            raise ValueError("initial BESS energy violates fixed SOC bounds")


@dataclass(frozen=True)
class TESPortCaps:
    """Fixed MW caps for the five externally visible TES energy ports."""

    electric_charge_input_mw: float
    steam_to_ht_reference_input_mw: float
    steam_to_mt_reference_input_mw: float
    electric_output_mw: float
    heat_output_mw: float

    def __post_init__(self) -> None:
        values = tuple(getattr(self, field.name) for field in fields(self))
        if not all(math.isfinite(value) for value in values):
            raise ValueError("TES port caps must be finite")
        if any(value < 0.0 for value in values):
            raise ValueError("TES port caps must be non-negative")


@dataclass(frozen=True)
class TESFixedSpec:
    """Installed three-temperature TES physics and boundary state."""

    physics: MoltenSaltPhysics
    initial_inventory: SaltInventory
    port_caps: TESPortCaps
    cyclic: bool = True
    loss_auxiliary: TESLossAuxiliarySpec | None = None

    def __post_init__(self) -> None:
        try:
            self.physics._validate_inventory(self.initial_inventory)
        except ValueError as error:
            raise ValueError(f"initial TES inventory is invalid: {error}") from error


@dataclass(frozen=True)
class ValidationObjectiveSpec:
    """Disclosed E0-C dispatch-only objective coefficients."""

    coal_price_cny_per_tce: float = 0.0
    curtailment_penalty_cny_per_mwh: float = 1.0
    cycle_event_cost_proxy_cny: float | None = None

    def __post_init__(self) -> None:
        values = (
            self.coal_price_cny_per_tce,
            self.curtailment_penalty_cny_per_mwh,
        )
        if not all(math.isfinite(value) for value in values) or any(
            value < 0.0 for value in values
        ):
            raise ValueError(
                "validation objective coefficients must be finite and non-negative"
            )
        if self.cycle_event_cost_proxy_cny is not None and (
            not math.isfinite(self.cycle_event_cost_proxy_cny)
            or self.cycle_event_cost_proxy_cny < 0.0
        ):
            raise ValueError(
                "validation objective coefficients must be finite and non-negative"
            )


@dataclass(frozen=True)
class AnnualCurtailmentServiceSpec:
    """Explicit annual renewable-curtailment service enforced without a penalty."""

    service_id: str
    maximum_curtailment_mwh: float

    def __post_init__(self) -> None:
        if not isinstance(self.service_id, str) or not self.service_id.strip():
            raise ValueError("annual curtailment service_id must be non-empty")
        if (
            isinstance(self.maximum_curtailment_mwh, bool)
            or not isinstance(self.maximum_curtailment_mwh, (int, float))
            or not math.isfinite(float(self.maximum_curtailment_mwh))
            or self.maximum_curtailment_mwh < 0.0
        ):
            raise ValueError(
                "annual maximum curtailment must be finite and non-negative"
            )


@dataclass(frozen=True)
class AnnualPCCExportServiceSpec:
    """Common annual PCC delivery fixed across architecture comparisons."""

    service_id: str
    target_export_mwh: float

    def __post_init__(self) -> None:
        if not isinstance(self.service_id, str) or not self.service_id.strip():
            raise ValueError("annual PCC export service_id must be non-empty")
        if (
            isinstance(self.target_export_mwh, bool)
            or not isinstance(self.target_export_mwh, (int, float))
            or not math.isfinite(float(self.target_export_mwh))
            or self.target_export_mwh < 0.0
        ):
            raise ValueError("annual target export must be finite and non-negative")


@dataclass(frozen=True)
class E0CCase:
    """Complete fixed-capacity deterministic case for exactly one architecture."""

    architecture: Architecture
    timeseries: E0CTimeSeries
    chp_units: tuple[CHPCommitmentSpec, ...]
    chp_initial_online: tuple[int, ...]
    pcc_export_capacity_mw: float
    chp_terminal_online: tuple[int, ...] | None = None
    bess: BESSFixedSpec | None = None
    tes: TESFixedSpec | None = None
    objective: ValidationObjectiveSpec = field(default_factory=ValidationObjectiveSpec)
    economics: AnnualEconomicsSpec | None = None
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
            raise ValueError("architecture must be selected with the Architecture enum")
        if not self.chp_units:
            raise ValueError("at least one fixed CHP unit is required")
        if any(not isinstance(unit, CHPCommitmentSpec) for unit in self.chp_units):
            raise ValueError("chp_units must contain CHPCommitmentSpec values")
        if not isinstance(self.chp_fuel_segment_formulation, FuelSegmentFormulation):
            raise ValueError(
                "chp_fuel_segment_formulation must use FuelSegmentFormulation"
            )
        if not isinstance(
            self.chp_transition_formulation,
            CommitmentTransitionFormulation,
        ):
            raise ValueError(
                "chp_transition_formulation must use CommitmentTransitionFormulation"
            )
        if any(unit.heat_basis is not HeatBasis.USEFUL for unit in self.chp_units):
            raise ValueError(
                "E0-C requires every CHP unit to use the useful heat basis"
            )
        boundary_states = (self.chp_initial_online,)
        if self.chp_terminal_online is not None:
            boundary_states += (self.chp_terminal_online,)
        if any(
            not isinstance(states, tuple)
            or len(states) != len(self.chp_units)
            or any(type(state) is not int or state not in (0, 1) for state in states)
            for states in boundary_states
        ):
            raise ValueError(
                "CHP boundary states must contain one integer zero/one per unit"
            )
        if not math.isfinite(self.pcc_export_capacity_mw) or (
            self.pcc_export_capacity_mw < 0.0
        ):
            raise ValueError("PCC export capacity must be finite and non-negative")
        if self.objective.cycle_event_cost_proxy_cny is not None and (
            self.chp_terminal_online is None
            or self.chp_terminal_online != self.chp_initial_online
        ):
            raise ValueError(
                "cycle-event cost proxy requires an explicit closed CHP status boundary"
            )
        if self.economics is not None:
            if not isinstance(self.economics, AnnualEconomicsSpec):
                raise ValueError("economics must be an AnnualEconomicsSpec or None")
            self.economics.horizon.validate_time_grid(
                period_count=self.timeseries.period_count,
                dt_hours=self.timeseries.dt_hours,
            )
            if self.objective.cycle_event_cost_proxy_cny is not None:
                raise ValueError(
                    "annual economics does not yet support the cycle-event cost proxy"
                )
        if self.curtailment_service is not None:
            if not isinstance(
                self.curtailment_service,
                AnnualCurtailmentServiceSpec,
            ):
                raise ValueError(
                    "curtailment_service must be an AnnualCurtailmentServiceSpec"
                )
            if self.economics is None:
                raise ValueError(
                    "annual curtailment service requires annual economics"
                )
        if self.pcc_export_service is not None:
            if not isinstance(
                self.pcc_export_service,
                AnnualPCCExportServiceSpec,
            ):
                raise ValueError(
                    "pcc_export_service must be an AnnualPCCExportServiceSpec"
                )
            if self.economics is None:
                raise ValueError(
                    "annual PCC export service requires annual economics"
                )

        includes_bess = self.architecture in (Architecture.BESS, Architecture.HYBRID)
        includes_tes = self.architecture in (Architecture.TES, Architecture.HYBRID)
        uses_block_horizon = self.economics is not None and isinstance(
            self.economics.horizon,
            BlockAnnualHorizonSpec,
        )
        if uses_block_horizon and (includes_bess or includes_tes):
            raise ValueError(
                "block annual storage dispatch requires the endogenous planning model"
            )
        if includes_bess and self.bess is None:
            raise ValueError(f"{self.architecture.value} requires a BESS fixed spec")
        if not includes_bess and self.bess is not None:
            raise ValueError(f"{self.architecture.value} contains a disabled BESS spec")
        if includes_tes and self.tes is None:
            raise ValueError(f"{self.architecture.value} requires a TES fixed spec")
        if not includes_tes and self.tes is not None:
            raise ValueError(f"{self.architecture.value} contains a disabled TES spec")
        if self.economics is not None:
            if not uses_block_horizon and (
                self.chp_terminal_online is None
                or self.chp_terminal_online != self.chp_initial_online
            ):
                raise ValueError(
                    "annual economics requires an explicit closed CHP status boundary"
                )
            if includes_bess and self.bess is not None and not self.bess.cyclic:
                raise ValueError("annual economics requires a cyclic BESS boundary")
            if includes_tes and self.tes is not None and not self.tes.cyclic:
                raise ValueError("annual economics requires a cyclic TES boundary")
            cell_cost = self.economics.bess_cell_cost
            variable_om = self.economics.bess_variable_om
            if includes_bess and cell_cost is None:
                raise ValueError(
                    "annual BESS economics requires one canonical BESS cell cost"
                )
            if not includes_bess and cell_cost is not None:
                raise ValueError(
                    f"{self.architecture.value} annual economics contains a disabled BESS cell cost"
                )
            if not includes_bess and variable_om is not None:
                raise ValueError(
                    f"{self.architecture.value} annual economics contains disabled BESS variable O&M"
                )
            calibrated_fraction = self.economics.calibrated_ac_deliverable_fraction
            if includes_bess and calibrated_fraction is not None:
                assert self.bess is not None
                physics = self.bess.physics
                physical_fraction = physics.discharge_efficiency * (
                    physics.soc_max - physics.soc_min
                )
                if not math.isclose(
                    calibrated_fraction,
                    physical_fraction,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                ):
                    raise ValueError(
                        "BESS cell AC deliverable fraction must match fixed BESS physics"
                    )
            if self.economics.non_cell_cost is not None:
                allowed_asset_classes = {
                    Architecture.NO_STORAGE: frozenset(),
                    Architecture.BESS: frozenset({LifecycleAssetClass.BESS_NON_CELL}),
                    Architecture.TES: frozenset({LifecycleAssetClass.TES_COMPONENT}),
                    Architecture.HYBRID: frozenset(
                        {
                            LifecycleAssetClass.BESS_NON_CELL,
                            LifecycleAssetClass.TES_COMPONENT,
                        }
                    ),
                }[self.architecture]
                if includes_tes:
                    allowed_asset_classes = allowed_asset_classes | {
                        LifecycleAssetClass.SALT_TO_STEAM_GENERATOR,
                        LifecycleAssetClass.EXISTING_TURBINE_REUSE,
                        LifecycleAssetClass.NEW_POWER_BLOCK,
                    }
                supplied_asset_classes = {
                    ledger.spec.asset_class
                    for ledger in self.economics.non_cell_cost.portfolio.ledgers
                }
                if not supplied_asset_classes <= allowed_asset_classes:
                    raise ValueError(
                        "annual non-cell portfolio asset classes must match the selected architecture"
                    )
            if (
                includes_tes
                and self.tes is not None
                and (self.tes.port_caps.electric_output_mw > 0.0)
            ):
                portfolio = (
                    None
                    if self.economics.non_cell_cost is None
                    else self.economics.non_cell_cost.portfolio
                )
                if portfolio is None or portfolio.tes_generation_cost_treatment is None:
                    raise ValueError(
                        "TES electric output requires explicit generation cost classification"
                    )
                assert self.economics.non_cell_cost is not None
                if not self.economics.non_cell_cost.has_positive_tes_generation_cost_quantities:
                    raise ValueError(
                        "TES generation cost classification requires strictly positive "
                        "installed quantities"
                    )


@dataclass(frozen=True)
class AnnualEconomicsAudit:
    """Public annual cost and energy breakdown without changing legacy metrics."""

    weighted_hours: float
    weighted_fuel_tce: float
    weighted_curtailment_mwh: float
    weighted_renewable_available_mwh: float
    weighted_pcc_export_mwh: float
    pcc_export_service_id: str | None
    pcc_export_target_mwh: float | None
    curtailment_service_id: str | None
    curtailment_ceiling_mwh: float | None
    bess_ac_discharge_throughput_mwh: float | None
    bess_ac_discharge_limit_mwh: float | None
    operating_cost_cny: float
    non_cell_fixed_cost_cny: float
    bess_calendar_cost_cny: float
    bess_cycle_cost_cny: float
    bess_variable_om_cost_cny: float
    total_cost_cny: float


class TESAuditWeightBasis(str, Enum):
    """Time-integration basis used by the public TES operational audit."""

    DISPATCH_HORIZON = "dispatch_horizon"
    ANNUAL_PERIOD_WEIGHTED = "annual_period_weighted"


@dataclass(frozen=True)
class TESOperationalAudit:
    """Five-path throughput, loss, and auxiliary totals on one explicit basis."""

    weight_basis: TESAuditWeightBasis
    weighted_hours: float
    path_throughput: TESSaltPathThroughput
    raw_standing_loss_mwh_th: float
    compensated_standing_loss_mwh_th: float
    net_standing_loss_mwh_th: float
    pump_auxiliary_mwh_e: float
    tracing_auxiliary_mwh_e: float
    total_auxiliary_mwh_e: float

    def __post_init__(self) -> None:
        if not isinstance(self.weight_basis, TESAuditWeightBasis):
            raise TypeError("weight_basis must be a TESAuditWeightBasis")
        if not isinstance(self.path_throughput, TESSaltPathThroughput):
            raise TypeError("path_throughput must be a TESSaltPathThroughput")
        values = (
            self.weighted_hours,
            self.raw_standing_loss_mwh_th,
            self.compensated_standing_loss_mwh_th,
            self.net_standing_loss_mwh_th,
            self.pump_auxiliary_mwh_e,
            self.tracing_auxiliary_mwh_e,
            self.total_auxiliary_mwh_e,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("TES operational audit values must be finite")
        if self.weighted_hours <= 0.0 or any(value < 0.0 for value in values[1:]):
            raise ValueError("TES operational audit values must be non-negative")
        if not math.isclose(
            self.net_standing_loss_mwh_th,
            self.raw_standing_loss_mwh_th
            - self.compensated_standing_loss_mwh_th,
            rel_tol=0.0,
            abs_tol=1e-8,
        ):
            raise ValueError("net TES standing loss must equal raw minus compensated")
        if not math.isclose(
            self.total_auxiliary_mwh_e,
            self.pump_auxiliary_mwh_e + self.tracing_auxiliary_mwh_e,
            rel_tol=0.0,
            abs_tol=1e-8,
        ):
            raise ValueError("total TES auxiliary must equal pump plus tracing")

    @property
    def compensation_fraction(self) -> float:
        if self.raw_standing_loss_mwh_th == 0.0:
            return 0.0
        return self.compensated_standing_loss_mwh_th / self.raw_standing_loss_mwh_th

    @property
    def pump_fraction_of_auxiliary(self) -> float:
        if self.total_auxiliary_mwh_e == 0.0:
            return 0.0
        return self.pump_auxiliary_mwh_e / self.total_auxiliary_mwh_e


@dataclass(frozen=True)
class E0CResult:
    """Compact solver and boundary audit for one E0-C validation solve."""

    architecture: Architecture
    solver_name: str
    termination: str
    runtime_seconds: float
    mip_gap: float | None
    objective_value: float
    fuel_tce: float
    curtailment_mwh: float
    wind_curtailed_mwh: float
    pv_curtailed_mwh: float
    pcc_export_mwh: float
    max_pcc_balance_residual_mw: float
    max_heat_balance_residual_mw: float
    bess_cyclic_residual_mwh: float | None
    tes_cyclic_residual_t: float | None
    tes_pump_auxiliary_mwh: float | None
    tes_tracing_auxiliary_mwh: float | None
    tes_auxiliary_mwh: float | None
    annual_economics: AnnualEconomicsAudit | None = None
    tes_operation: TESOperationalAudit | None = None
    lexicographic_curtailment_tie_break: bool = False
    primary_cost_tolerance_cny: float | None = None
    primary_cost_mip_gap: float | None = None
    primary_objective_lower_bound: float | None = None
    primary_objective_upper_bound: float | None = None
    secondary_curtailment_mip_gap: float | None = None
    lexicographic_fixed_primary_integer_count: int | None = None
    pcc_service_feasibility_warm_start: bool = False
    pcc_service_feasibility_runtime_seconds: float | None = None
    pcc_service_feasibility_deviation_mw: float | None = None
    pcc_export_trace_mw: tuple[float, ...] = ()

    @property
    def objective_basis(self) -> str:
        if self.annual_economics is None:
            return "dispatch_validation_cost"
        return "annual_validation_cost_cny_per_year"


def build_e0c_model(case: E0CCase) -> object:
    """Build the linear fixed-capacity E0-C dispatch MILP for one architecture."""

    from pyomo.environ import (
        Block,
        ConcreteModel,
        Constraint,
        Expression,
        NonNegativeReals,
        Objective,
        Param,
        RangeSet,
        Var,
        minimize,
    )

    model = ConcreteModel(name=f"e0c_{case.architecture.value}")
    model.periods = RangeSet(0, case.timeseries.period_count - 1)
    cyclic_period_blocks = (
        case.economics.horizon.cyclic_period_blocks
        if case.economics is not None
        and isinstance(case.economics.horizon, BlockAnnualHorizonSpec)
        else None
    )
    model.unit_index = RangeSet(0, len(case.chp_units) - 1)
    model.chp = Block(model.unit_index)
    for unit_index, spec in enumerate(case.chp_units):
        add_chp_unit_commitment(
            model.chp[unit_index],
            model.periods,
            spec,
            time_step_hours=case.timeseries.dt_hours,
            initial_online=case.chp_initial_online[unit_index],
            cycle_event_cost_proxy_cny=(case.objective.cycle_event_cost_proxy_cny),
            fuel_segment_formulation=case.chp_fuel_segment_formulation,
            transition_formulation=case.chp_transition_formulation,
            cyclic_period_blocks=cyclic_period_blocks,
        )
        if cyclic_period_blocks is None and case.chp_terminal_online is not None:
            model.chp[unit_index].terminal_online = Constraint(
                expr=model.chp[unit_index].online[case.timeseries.period_count - 1]
                == case.chp_terminal_online[unit_index]
            )

    model.wind_used = Var(model.periods, domain=NonNegativeReals)
    model.wind_curtailed = Var(model.periods, domain=NonNegativeReals)
    model.pv_used = Var(model.periods, domain=NonNegativeReals)
    model.pv_curtailed = Var(model.periods, domain=NonNegativeReals)
    model.pcc_export = Var(
        model.periods,
        bounds=(0.0, case.pcc_export_capacity_mw),
    )
    model.direct_heat = Var(model.periods, domain=NonNegativeReals)

    model.wind_split = Constraint(
        model.periods,
        rule=lambda block, period: (
            block.wind_used[period] + block.wind_curtailed[period]
            == case.timeseries.wind_available_mw[period]
        ),
    )
    model.pv_split = Constraint(
        model.periods,
        rule=lambda block, period: (
            block.pv_used[period] + block.pv_curtailed[period]
            == case.timeseries.pv_available_mw[period]
        ),
    )

    if case.bess is not None:
        model.bess = Block()
        add_bess_dispatch(
            model.bess,
            model.periods,
            case.bess.physics,
            initial_energy_mwh=case.bess.initial_energy_mwh,
            dt_hours=case.timeseries.dt_hours,
            cyclic=case.bess.cyclic,
        )

    if case.tes is not None:
        model.tes = Block()
        physics = case.tes.physics
        caps = case.tes.port_caps
        path_flow_bounds = MoltenSaltFlowBounds(
            electric_lt_to_ht_tph=(
                caps.electric_charge_input_mw
                * physics.electric_heater_efficiency
                / (
                    physics.specific_heat_mwh_per_tonne_k
                    * (physics.temperature_ht - physics.temperature_lt)
                )
            ),
            steam_lt_to_ht_tph=(
                caps.steam_to_ht_reference_input_mw
                * physics.steam_to_ht_efficiency
                / (
                    physics.specific_heat_mwh_per_tonne_k
                    * (physics.temperature_ht - physics.temperature_lt)
                )
            ),
            steam_lt_to_mt_tph=(
                caps.steam_to_mt_reference_input_mw
                * physics.steam_to_mt_efficiency
                / (
                    physics.specific_heat_mwh_per_tonne_k * physics.delta_mt_lt
                )
            ),
            power_ht_to_mt_tph=(
                caps.electric_output_mw
                / (
                    physics.power_block_efficiency
                    * physics.specific_heat_mwh_per_tonne_k
                    * physics.delta_ht_mt
                )
            ),
            heat_mt_to_lt_tph=(
                caps.heat_output_mw
                / (
                    physics.heat_exchanger_efficiency
                    * physics.specific_heat_mwh_per_tonne_k
                    * physics.delta_mt_lt
                )
            ),
        )
        add_molten_salt_dispatch(
            model.tes,
            model.periods,
            case.tes.physics,
            initial_inventory=case.tes.initial_inventory,
            dt_hours=case.timeseries.dt_hours,
            cyclic=case.tes.cyclic,
            loss_auxiliary=case.tes.loss_auxiliary,
            ambient_temperature_c=case.timeseries.ambient_temperature_c,
            path_flow_bounds=path_flow_bounds,
        )
        model.tes_electric_charge_cap = Constraint(
            model.periods,
            rule=lambda _block, period: (
                model.tes.electric_charge_input[period] <= caps.electric_charge_input_mw
            ),
        )
        model.tes_steam_to_ht_cap = Constraint(
            model.periods,
            rule=lambda _block, period: (
                model.tes.steam_to_ht_input[period]
                <= caps.steam_to_ht_reference_input_mw
            ),
        )
        model.tes_steam_to_mt_cap = Constraint(
            model.periods,
            rule=lambda _block, period: (
                model.tes.steam_to_mt_input[period]
                <= caps.steam_to_mt_reference_input_mw
            ),
        )
        model.tes_electric_output_cap = Constraint(
            model.periods,
            rule=lambda _block, period: (
                model.tes.electric_output[period] <= caps.electric_output_mw
            ),
        )
        model.tes_heat_output_cap = Constraint(
            model.periods,
            rule=lambda _block, period: (
                model.tes.heat_output[period] <= caps.heat_output_mw
            ),
        )

    model.chp_gross_total = Expression(
        model.periods,
        rule=lambda block, period: sum(
            block.chp[unit].power_gross[period] for unit in block.unit_index
        ),
    )
    model.chp_auxiliary_total = Expression(
        model.periods,
        rule=lambda block, period: sum(
            block.chp[unit].auxiliary_power[period] for unit in block.unit_index
        ),
    )
    model.tes_auxiliary_total = Expression(
        model.periods,
        rule=lambda block, period: (
            block.tes.auxiliary_power[period] if hasattr(block, "tes") else 0.0
        ),
    )
    model.chp_heat_total = Expression(
        model.periods,
        rule=lambda block, period: sum(
            block.chp[unit].heat[period] for unit in block.unit_index
        ),
    )

    def pcc_balance_rule(block: object, period: int) -> object:
        bess_charge = block.bess.charge_ac[period] if hasattr(block, "bess") else 0.0
        bess_discharge = (
            block.bess.discharge_ac[period] if hasattr(block, "bess") else 0.0
        )
        tes_charge = (
            block.tes.electric_charge_input[period] if hasattr(block, "tes") else 0.0
        )
        tes_output = block.tes.electric_output[period] if hasattr(block, "tes") else 0.0
        return (
            block.pcc_export[period]
            + bess_charge
            + tes_charge
            + block.chp_auxiliary_total[period]
            + block.tes_auxiliary_total[period]
            == block.chp_gross_total[period]
            + block.wind_used[period]
            + block.pv_used[period]
            + bess_discharge
            + tes_output
        )

    model.pcc_balance = Constraint(model.periods, rule=pcc_balance_rule)

    def heat_allocation_rule(block: object, period: int) -> object:
        tes_reference_charge = (
            block.tes.steam_to_ht_input[period] + block.tes.steam_to_mt_input[period]
            if hasattr(block, "tes")
            else 0.0
        )
        return (
            block.chp_heat_total[period]
            == block.direct_heat[period] + tes_reference_charge
        )

    def heat_balance_rule(block: object, period: int) -> object:
        tes_heat_output = (
            block.tes.heat_output[period] if hasattr(block, "tes") else 0.0
        )
        return (
            block.direct_heat[period] + tes_heat_output
            == case.timeseries.heat_demand_mw[period]
        )

    model.heat_allocation = Constraint(model.periods, rule=heat_allocation_rule)
    model.heat_balance = Constraint(model.periods, rule=heat_balance_rule)
    model.total_fuel_tce = Expression(
        expr=case.timeseries.dt_hours
        * sum(
            model.chp[unit].fuel_tce_per_hour[period]
            for unit in model.unit_index
            for period in model.periods
        )
    )
    model.total_curtailment_mwh = Expression(
        expr=case.timeseries.dt_hours
        * sum(
            model.wind_curtailed[period] + model.pv_curtailed[period]
            for period in model.periods
        )
    )
    model.total_transition_proxy_cost = Expression(
        expr=sum(model.chp[unit].transition_proxy_cost for unit in model.unit_index)
    )
    if case.economics is None:
        model.validation_cost = Objective(
            expr=case.objective.coal_price_cny_per_tce * model.total_fuel_tce
            + case.objective.curtailment_penalty_cny_per_mwh
            * model.total_curtailment_mwh
            + model.total_transition_proxy_cost,
            sense=minimize,
        )
    else:
        period_weights = case.economics.horizon.period_weights
        model.annual_period_weight = Param(
            model.periods,
            initialize=lambda _block, period: float(period_weights[period]),
            within=NonNegativeReals,
            mutable=False,
        )
        model.annual_weighted_hours = Expression(
            expr=case.timeseries.dt_hours
            * sum(model.annual_period_weight[period] for period in model.periods)
        )
        model.annual_fuel_tce = Expression(
            expr=case.timeseries.dt_hours
            * sum(
                model.annual_period_weight[period]
                * model.chp[unit].fuel_tce_per_hour[period]
                for unit in model.unit_index
                for period in model.periods
            )
        )
        model.annual_curtailment_mwh = Expression(
            expr=case.timeseries.dt_hours
            * sum(
                model.annual_period_weight[period]
                * (model.wind_curtailed[period] + model.pv_curtailed[period])
                for period in model.periods
            )
        )
        model.annual_renewable_available_mwh = Expression(
            expr=case.timeseries.dt_hours
            * sum(
                model.annual_period_weight[period]
                * (
                    case.timeseries.wind_available_mw[period]
                    + case.timeseries.pv_available_mw[period]
                )
                for period in model.periods
            )
        )
        model.annual_pcc_export_mwh = Expression(
            expr=case.timeseries.dt_hours
            * sum(
                model.annual_period_weight[period] * model.pcc_export[period]
                for period in model.periods
            )
        )
        if case.pcc_export_service is not None:
            # Enforce the annual-energy identity on an average-power basis.
            # The unscaled annual equation is O(1e6) MWh for the E0 windows,
            # whereas the dispatch rows are O(1e2--1e3) MW.  Dividing both
            # sides by the constant weighted hours preserves the exact
            # service contract and materially improves HiGHS feasibility
            # scaling on the 336 h mixed-integer model.
            model.annual_pcc_export_service = Constraint(
                expr=(
                    model.annual_pcc_export_mwh / model.annual_weighted_hours
                    == case.pcc_export_service.target_export_mwh
                    / model.annual_weighted_hours
                )
            )
        if case.curtailment_service is not None:
            model.annual_curtailment_service = Constraint(
                expr=model.annual_curtailment_mwh
                <= case.curtailment_service.maximum_curtailment_mwh
            )
        model.annual_operating_cost_cny = Expression(
            expr=case.objective.coal_price_cny_per_tce * model.annual_fuel_tce
            + case.objective.curtailment_penalty_cny_per_mwh
            * model.annual_curtailment_mwh
        )
        model.annual_non_cell_fixed_eac_cny = Expression(
            expr=case.economics.non_cell_fixed_annual_cost_cny
        )
        nominal_bess_energy_mwh = (
            case.bess.physics.energy_capacity_mwh if case.bess is not None else 0.0
        )
        model.annual_bess_calendar_cost_cny = Expression(
            expr=case.economics.bess_calendar_cost_per_nominal_mwh_year
            * nominal_bess_energy_mwh
        )
        model.annual_storage_fixed_eac_cny = Expression(
            expr=model.annual_non_cell_fixed_eac_cny
            + model.annual_bess_calendar_cost_cny
        )
        if case.bess is not None:
            model.annual_bess_ac_discharge_throughput_mwh = Expression(
                expr=case.timeseries.dt_hours
                * sum(
                    model.annual_period_weight[period] * model.bess.discharge_ac[period]
                    for period in model.periods
                )
            )
            physical_ac_fraction = case.bess.physics.discharge_efficiency * (
                case.bess.physics.soc_max - case.bess.physics.soc_min
            )
            reference_annual_ac_efc = case.economics.bess_reference_annual_ac_efc
            assert reference_annual_ac_efc is not None
            annual_throughput_limit_mwh = (
                reference_annual_ac_efc * physical_ac_fraction * nominal_bess_energy_mwh
            )
            model.annual_bess_ac_throughput_limit_mwh = Expression(
                expr=annual_throughput_limit_mwh
            )
            model.bess_annual_ac_throughput_limit = Constraint(
                expr=model.annual_bess_ac_discharge_throughput_mwh
                <= model.annual_bess_ac_throughput_limit_mwh
            )
        else:
            model.annual_bess_ac_discharge_throughput_mwh = Expression(expr=0.0)
        model.annual_bess_cycle_cost_cny = Expression(
            expr=case.economics.bess_cycle_cost_per_ac_discharge_mwh
            * model.annual_bess_ac_discharge_throughput_mwh
        )
        model.annual_bess_variable_om_cost_cny = Expression(
            expr=case.economics.bess_variable_om_per_ac_discharge_mwh
            * model.annual_bess_ac_discharge_throughput_mwh
        )
        model.annual_total_cost_cny = Expression(
            expr=model.annual_operating_cost_cny
            + model.annual_storage_fixed_eac_cny
            + model.annual_bess_cycle_cost_cny
            + model.annual_bess_variable_om_cost_cny
        )
        model.validation_cost = Objective(
            expr=model.annual_total_cost_cny,
            sense=minimize,
        )
    return model


def solve_e0c(
    case: E0CCase,
    *,
    solver: object | None = None,
    lexicographic_minimize_curtailment: bool = False,
    pcc_service_feasibility_warm_start: bool = False,
) -> E0CResult:
    """Solve one E0-C case with HiGHS and return boundary-level audit metrics.

    When requested for an annual case, a second solve fixes the primary
    cost-optimal incumbent's integer decisions and minimizes curtailment while
    constraining annual cost to that incumbent.  This removes continuous
    renewable-dispatch degeneracy without assigning an artificial monetary
    curtailment penalty or reopening the full mixed-integer search.

    A difficult annual PCC equality can optionally use a disclosed feasibility
    phase.  That phase minimizes average-power delivery deviation, then passes
    the zero-deviation incumbent to the unchanged primary-cost problem as a
    HiGHS warm start.  It changes the search path, not the service equality or
    primary objective.
    """

    from pyomo.environ import (
        Constraint,
        NonNegativeReals,
        Objective,
        Var,
        minimize,
        value,
    )
    from pyomo.contrib.appsi.base import LegacySolverInterface
    from pyomo.contrib.appsi.solvers import Highs

    from tes_bess_boundary.solver import create_highs_solver

    if not isinstance(lexicographic_minimize_curtailment, bool):
        raise ValueError("lexicographic_minimize_curtailment must be boolean")
    if not isinstance(pcc_service_feasibility_warm_start, bool):
        raise ValueError("pcc_service_feasibility_warm_start must be boolean")
    if lexicographic_minimize_curtailment and case.economics is None:
        raise ValueError("lexicographic curtailment tie-break requires annual economics")
    if pcc_service_feasibility_warm_start and case.pcc_export_service is None:
        raise ValueError(
            "PCC service feasibility warm start requires an annual PCC service"
        )
    if solver is None:
        solver = create_highs_solver()
    elif not isinstance(solver, Highs):
        raise ValueError("E0-C supports only the appsi_highs solver")

    model = build_e0c_model(case)
    is_legacy_interface = isinstance(solver, LegacySolverInterface)
    if pcc_service_feasibility_warm_start and not is_legacy_interface:
        raise ValueError(
            "PCC service feasibility warm start requires the legacy appsi_highs interface"
        )

    def termination_name(solve_results: object) -> str:
        raw = (
            solve_results.solver.termination_condition
            if is_legacy_interface
            else solve_results.termination_condition
        )
        return getattr(raw, "name", str(raw)).lower()

    measured_runtime_seconds = 0.0
    service_feasibility_runtime_seconds = None
    service_feasibility_deviation_mw = None
    if pcc_service_feasibility_warm_start:
        service = case.pcc_export_service
        assert service is not None
        model.validation_cost.deactivate()
        model.annual_pcc_export_service.deactivate()
        model.pcc_service_abs_deviation_mw = Var(domain=NonNegativeReals)
        average_export_mw = (
            model.annual_pcc_export_mwh / model.annual_weighted_hours
        )
        target_average_export_mw = (
            service.target_export_mwh / model.annual_weighted_hours
        )
        model.pcc_service_deviation_upper = Constraint(
            expr=(
                average_export_mw - target_average_export_mw
                <= model.pcc_service_abs_deviation_mw
            )
        )
        model.pcc_service_deviation_lower = Constraint(
            expr=(
                target_average_export_mw - average_export_mw
                <= model.pcc_service_abs_deviation_mw
            )
        )
        model.pcc_service_feasibility_objective = Objective(
            expr=model.pcc_service_abs_deviation_mw,
            sense=minimize,
        )
        feasibility_started = perf_counter()
        feasibility_results = solver.solve(model, tee=False)
        service_feasibility_runtime_seconds = (
            perf_counter() - feasibility_started
        )
        measured_runtime_seconds += service_feasibility_runtime_seconds
        feasibility_termination = termination_name(feasibility_results)
        if feasibility_termination != "optimal":
            raise RuntimeError(
                "E0-C PCC service feasibility phase did not solve optimally: "
                f"{feasibility_termination}"
            )
        service_feasibility_deviation_mw = float(
            value(model.pcc_service_abs_deviation_mw)
        )
        if service_feasibility_deviation_mw > 1e-9:
            raise RuntimeError(
                "E0-C annual PCC target is outside the solved service domain: "
                f"minimum average-power deviation is "
                f"{service_feasibility_deviation_mw:.12g} MW"
            )
        model.pcc_service_feasibility_objective.deactivate()
        model.pcc_service_deviation_upper.deactivate()
        model.pcc_service_deviation_lower.deactivate()
        model.annual_pcc_export_service.activate()
        model.validation_cost.activate()

    solve_started = perf_counter()
    results = (
        solver.solve(
            model,
            tee=False,
            warmstart=pcc_service_feasibility_warm_start,
        )
        if is_legacy_interface
        else solver.solve(model)
    )
    measured_runtime_seconds += perf_counter() - solve_started
    termination = termination_name(results)
    if termination != "optimal":
        raise RuntimeError(f"E0-C model did not solve optimally: {termination}")

    def finite_float(candidate: object) -> float | None:
        try:
            number = float(candidate)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def solve_bounds(solve_results: object) -> tuple[float | None, float | None]:
        if is_legacy_interface:
            feasible = finite_float(solve_results.problem.upper_bound)
            bound = finite_float(solve_results.problem.lower_bound)
        else:
            feasible = finite_float(solve_results.best_feasible_objective)
            bound = finite_float(solve_results.best_objective_bound)
        return bound, feasible

    def solve_gap(solve_results: object) -> float | None:
        bound, feasible = solve_bounds(solve_results)
        if feasible is None or bound is None:
            return None
        return abs(feasible - bound) / max(abs(feasible), 1e-12)

    primary_objective_lower_bound, primary_objective_upper_bound = solve_bounds(
        results
    )
    primary_cost_mip_gap = solve_gap(results)
    primary_cost_tolerance_cny = None
    fixed_primary_integer_count = None
    if lexicographic_minimize_curtailment:
        primary_cost = float(value(model.annual_total_cost_cny))
        # A one-ULP cap is numerically unsafe after the warm-started 336 h
        # annual-cost MILP is converted to a fixed-integer LP.  Only that
        # disclosed path receives a one-part-per-billion (sub-CNY at E0 scale)
        # allowance; exact small cases retain the historical ULP-level cap.
        warm_started_relative_tolerance = (
            1e-9 * abs(primary_cost)
            if pcc_service_feasibility_warm_start
            else 0.0
        )
        primary_cost_tolerance_cny = max(
            1e-6,
            10.0 * math.ulp(primary_cost),
            warm_started_relative_tolerance,
        )
        model.lexicographic_primary_cost_cap = Constraint(
            expr=model.annual_total_cost_cny
            <= primary_cost + primary_cost_tolerance_cny
        )
        model.validation_cost.deactivate()
        model.lexicographic_curtailment_objective = Objective(
            expr=model.annual_curtailment_mwh,
            sense=minimize,
        )
        fixed_primary_integer_count = 0
        for variable in model.component_data_objects(Var, active=True):
            if variable.is_binary() or variable.is_integer():
                incumbent_value = value(variable, exception=False)
                if incumbent_value is None:
                    raise RuntimeError(
                        "primary cost solve left an integer variable without a value"
                    )
                variable.fix(round(float(incumbent_value)))
                fixed_primary_integer_count += 1
        second_solve_started = perf_counter()
        results = (
            solver.solve(model, tee=False, warmstart=True)
            if is_legacy_interface
            else solver.solve(model)
        )
        measured_runtime_seconds += perf_counter() - second_solve_started
        raw_termination = (
            results.solver.termination_condition
            if is_legacy_interface
            else results.termination_condition
        )
        termination = getattr(raw_termination, "name", str(raw_termination)).lower()
        if termination != "optimal":
            raise RuntimeError(
                "E0-C lexicographic curtailment solve did not solve optimally: "
                f"{termination}"
            )

    if is_legacy_interface:
        runtime_seconds = measured_runtime_seconds
    else:
        reported_runtime = finite_float(results.wallclock_time)
        runtime_seconds = measured_runtime_seconds
        if not lexicographic_minimize_curtailment:
            runtime_seconds = (
                reported_runtime
                if reported_runtime is not None and reported_runtime >= 0.0
                else measured_runtime_seconds
            )
    secondary_curtailment_mip_gap = (
        solve_gap(results) if lexicographic_minimize_curtailment else None
    )
    mip_gap = secondary_curtailment_mip_gap
    if not lexicographic_minimize_curtailment:
        mip_gap = primary_cost_mip_gap
    elif primary_cost_mip_gap is not None:
        mip_gap = max(mip_gap or 0.0, primary_cost_mip_gap)

    dt_hours = case.timeseries.dt_hours
    wind_curtailed_mwh = dt_hours * sum(
        value(model.wind_curtailed[period]) for period in model.periods
    )
    pv_curtailed_mwh = dt_hours * sum(
        value(model.pv_curtailed[period]) for period in model.periods
    )

    def equality_residual(constraint: object) -> float:
        target = constraint.lower
        if target is None:
            target = constraint.upper
        if target is None:
            raise RuntimeError(f"{constraint.name} is not a bounded equality")
        return abs(value(constraint.body) - value(target))

    final_state = case.timeseries.period_count
    bess_cyclic_residual = None
    if case.bess is not None and case.bess.cyclic:
        bess_cyclic_residual = abs(
            value(model.bess.energy[final_state]) - value(model.bess.energy[0])
        )
    tes_cyclic_residual = None
    if case.tes is not None and case.tes.cyclic:
        tes_cyclic_residual = max(
            abs(
                value(getattr(model.tes, state)[final_state])
                - value(getattr(model.tes, state)[0])
            )
            for state in ("ht_mass", "mt_mass", "lt_mass")
        )

    annual_economics = None
    if case.economics is not None:
        annual_economics = AnnualEconomicsAudit(
            weighted_hours=float(value(model.annual_weighted_hours)),
            weighted_fuel_tce=float(value(model.annual_fuel_tce)),
            weighted_curtailment_mwh=float(value(model.annual_curtailment_mwh)),
            weighted_renewable_available_mwh=float(
                value(model.annual_renewable_available_mwh)
            ),
            weighted_pcc_export_mwh=float(value(model.annual_pcc_export_mwh)),
            pcc_export_service_id=(
                case.pcc_export_service.service_id
                if case.pcc_export_service is not None
                else None
            ),
            pcc_export_target_mwh=(
                float(case.pcc_export_service.target_export_mwh)
                if case.pcc_export_service is not None
                else None
            ),
            curtailment_service_id=(
                case.curtailment_service.service_id
                if case.curtailment_service is not None
                else None
            ),
            curtailment_ceiling_mwh=(
                float(case.curtailment_service.maximum_curtailment_mwh)
                if case.curtailment_service is not None
                else None
            ),
            bess_ac_discharge_throughput_mwh=(
                float(value(model.annual_bess_ac_discharge_throughput_mwh))
                if case.bess is not None
                else None
            ),
            bess_ac_discharge_limit_mwh=(
                float(value(model.annual_bess_ac_throughput_limit_mwh))
                if case.bess is not None
                else None
            ),
            operating_cost_cny=float(value(model.annual_operating_cost_cny)),
            non_cell_fixed_cost_cny=float(value(model.annual_non_cell_fixed_eac_cny)),
            bess_calendar_cost_cny=float(value(model.annual_bess_calendar_cost_cny)),
            bess_cycle_cost_cny=float(value(model.annual_bess_cycle_cost_cny)),
            bess_variable_om_cost_cny=float(
                value(model.annual_bess_variable_om_cost_cny)
            ),
            total_cost_cny=float(value(model.annual_total_cost_cny)),
        )

    tes_operation = None
    if case.tes is not None:
        if case.economics is None:
            audit_weight_basis = TESAuditWeightBasis.DISPATCH_HORIZON
            audit_weights = (1.0,) * case.timeseries.period_count
        else:
            audit_weight_basis = TESAuditWeightBasis.ANNUAL_PERIOD_WEIGHTED
            audit_weights = case.economics.horizon.period_weights

        def integrated_tonnes(flow_name: str) -> float:
            integrated = dt_hours * sum(
                audit_weights[period]
                * value(getattr(model.tes, flow_name)[period])
                for period in model.periods
            )
            return max(0.0, float(integrated))

        path_throughput = TESSaltPathThroughput(
            electric_lt_to_ht_t=integrated_tonnes("electric_lt_to_ht"),
            steam_lt_to_ht_t=integrated_tonnes("steam_lt_to_ht"),
            steam_lt_to_mt_t=integrated_tonnes("steam_lt_to_mt"),
            power_ht_to_mt_t=integrated_tonnes("power_ht_to_mt"),
            heat_mt_to_lt_t=integrated_tonnes("heat_mt_to_lt"),
        )

        def integrated_expression(expression_name: str) -> float:
            integrated = dt_hours * sum(
                audit_weights[period]
                * value(getattr(model.tes, expression_name)[period])
                for period in model.periods
            )
            return max(0.0, float(integrated))

        raw_ht_to_mt_t = integrated_expression("raw_loss_ht_to_mt")
        raw_mt_to_lt_t = integrated_expression("raw_loss_mt_to_lt")
        compensated_ht_to_mt_t = integrated_expression("compensated_loss_ht_to_mt")
        compensated_mt_to_lt_t = integrated_expression("compensated_loss_mt_to_lt")
        physics = case.tes.physics
        raw_standing_loss_mwh_th = physics.specific_heat_mwh_per_tonne_k * (
            physics.delta_ht_mt * raw_ht_to_mt_t
            + physics.delta_mt_lt * raw_mt_to_lt_t
        )
        compensated_standing_loss_mwh_th = (
            physics.specific_heat_mwh_per_tonne_k
            * (
                physics.delta_ht_mt * compensated_ht_to_mt_t
                + physics.delta_mt_lt * compensated_mt_to_lt_t
            )
        )
        net_standing_loss_mwh_th = max(
            0.0,
            raw_standing_loss_mwh_th - compensated_standing_loss_mwh_th,
        )
        pump_auxiliary_mwh_e = integrated_expression("pump_auxiliary")
        tracing_auxiliary_mwh_e = integrated_expression("tracing_auxiliary")
        tes_operation = TESOperationalAudit(
            weight_basis=audit_weight_basis,
            weighted_hours=float(dt_hours * sum(audit_weights)),
            path_throughput=path_throughput,
            raw_standing_loss_mwh_th=float(raw_standing_loss_mwh_th),
            compensated_standing_loss_mwh_th=float(
                compensated_standing_loss_mwh_th
            ),
            net_standing_loss_mwh_th=float(net_standing_loss_mwh_th),
            pump_auxiliary_mwh_e=pump_auxiliary_mwh_e,
            tracing_auxiliary_mwh_e=tracing_auxiliary_mwh_e,
            total_auxiliary_mwh_e=pump_auxiliary_mwh_e + tracing_auxiliary_mwh_e,
        )

    return E0CResult(
        architecture=case.architecture,
        solver_name="appsi_highs",
        termination=termination,
        runtime_seconds=float(runtime_seconds),
        mip_gap=float(mip_gap) if mip_gap is not None else None,
        objective_value=float(
            value(model.annual_total_cost_cny)
            if case.economics is not None
            else value(model.validation_cost)
        ),
        fuel_tce=float(value(model.total_fuel_tce)),
        curtailment_mwh=float(value(model.total_curtailment_mwh)),
        wind_curtailed_mwh=float(wind_curtailed_mwh),
        pv_curtailed_mwh=float(pv_curtailed_mwh),
        pcc_export_mwh=float(
            dt_hours * sum(value(model.pcc_export[period]) for period in model.periods)
        ),
        max_pcc_balance_residual_mw=float(
            max(
                equality_residual(model.pcc_balance[period]) for period in model.periods
            )
        ),
        max_heat_balance_residual_mw=float(
            max(
                max(
                    equality_residual(model.heat_allocation[period]),
                    equality_residual(model.heat_balance[period]),
                )
                for period in model.periods
            )
        ),
        bess_cyclic_residual_mwh=(
            float(bess_cyclic_residual) if bess_cyclic_residual is not None else None
        ),
        tes_cyclic_residual_t=(
            float(tes_cyclic_residual) if tes_cyclic_residual is not None else None
        ),
        tes_pump_auxiliary_mwh=(
            float(
                dt_hours
                * sum(
                    value(model.tes.pump_auxiliary[period]) for period in model.periods
                )
            )
            if case.tes is not None
            else None
        ),
        tes_tracing_auxiliary_mwh=(
            float(
                dt_hours
                * sum(
                    value(model.tes.tracing_auxiliary[period])
                    for period in model.periods
                )
            )
            if case.tes is not None
            else None
        ),
        tes_auxiliary_mwh=(
            float(
                dt_hours
                * sum(
                    value(model.tes.auxiliary_power[period]) for period in model.periods
                )
            )
            if case.tes is not None
            else None
        ),
        annual_economics=annual_economics,
        tes_operation=tes_operation,
        lexicographic_curtailment_tie_break=(
            lexicographic_minimize_curtailment
        ),
        primary_cost_tolerance_cny=primary_cost_tolerance_cny,
        primary_cost_mip_gap=primary_cost_mip_gap,
        primary_objective_lower_bound=primary_objective_lower_bound,
        primary_objective_upper_bound=primary_objective_upper_bound,
        secondary_curtailment_mip_gap=secondary_curtailment_mip_gap,
        lexicographic_fixed_primary_integer_count=fixed_primary_integer_count,
        pcc_service_feasibility_warm_start=(
            pcc_service_feasibility_warm_start
        ),
        pcc_service_feasibility_runtime_seconds=(
            service_feasibility_runtime_seconds
        ),
        pcc_service_feasibility_deviation_mw=(
            service_feasibility_deviation_mw
        ),
        pcc_export_trace_mw=tuple(
            float(value(model.pcc_export[period])) for period in model.periods
        ),
    )
