"""CHP table-vertex feasible region and gross/net basis utilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from tes_bess_boundary.economics import validate_cyclic_period_blocks


@dataclass(frozen=True)
class CHPVertex:
    power_gross_mw: float
    heat_mw: float

    def __post_init__(self) -> None:
        if not isfinite(self.power_gross_mw) or not isfinite(self.heat_mw):
            raise ValueError("CHP vertex power and heat must be finite")
        if self.power_gross_mw < 0 or self.heat_mw < 0:
            raise ValueError("CHP vertex power and heat must be non-negative")


class HeatBasis(str, Enum):
    USEFUL = "useful_heat"
    EXTRACTION = "extraction_heat"
    UNRESOLVED = "unresolved"


class UnresolvedHeatBasisError(ValueError):
    """Raised when an unresolved heat basis would enter a formal model."""


class LowLoadFuelRule(str, Enum):
    """Explicit treatments for the 98--105 MW fuel-evidence gap."""

    LINEAR_TOTAL_FLOW_EXTRAPOLATION = "linear_total_flow_extrapolation"
    CLAMP_30_PERCENT_RATE = "clamp_30_percent_rate"
    RAISE_MIN_POWER_TO_105 = "raise_min_power_to_105"


class FuelSegmentFormulation(str, Enum):
    """Exact encodings for selecting one adjacent CHP fuel segment."""

    ONE_HOT = "one_hot"
    LOGARITHMIC = "logarithmic"


class CommitmentTransitionFormulation(str, Enum):
    """Equivalent encodings of startup and shutdown transition indicators."""

    BINARY = "binary"
    CONTINUOUS_ENVELOPE = "continuous_envelope"


@dataclass(frozen=True)
class CHPFuelPoint:
    """A raw supply-coal-rate observation at generator-gross power."""

    power_gross_mw: float
    supply_coal_rate_g_per_kwh: float

    def __post_init__(self) -> None:
        if not isfinite(self.power_gross_mw):
            raise ValueError("fuel-point gross power must be finite")
        if not isfinite(self.supply_coal_rate_g_per_kwh):
            raise ValueError("supply coal rate must be finite")
        if self.power_gross_mw <= 0:
            raise ValueError("fuel-point gross power must be positive")
        if self.supply_coal_rate_g_per_kwh < 0:
            raise ValueError("supply coal rate must be non-negative")

    def total_fuel_tce_per_hour(self, auxiliary_rate: float) -> float:
        """Convert the source net-electricity denominator to total flow."""

        return coal_consumption_tph(
            gross_power_mw=self.power_gross_mw,
            auxiliary_rate=auxiliary_rate,
            supply_coal_rate_g_per_kwh=self.supply_coal_rate_g_per_kwh,
        )


@dataclass(frozen=True)
class CHPFeasibleRegion:
    vertices: tuple[CHPVertex, ...]

    def __post_init__(self) -> None:
        if len(self.vertices) < 3:
            raise ValueError("At least three online CHP vertices are required")
        if len(set(self.vertices)) != len(self.vertices):
            raise ValueError("CHP vertices must be unique")

    @property
    def minimum_heat_mw(self) -> float:
        return min(vertex.heat_mw for vertex in self.vertices)

    @property
    def maximum_heat_mw(self) -> float:
        return max(vertex.heat_mw for vertex in self.vertices)

    def minimum_power_for_heat(self, heat_mw: float, *, tolerance: float = 1e-9) -> float:
        """Return the LP lower envelope of gross power at fixed heat."""

        if (
            heat_mw < self.minimum_heat_mw - tolerance
            or heat_mw > self.maximum_heat_mw + tolerance
        ):
            raise ValueError(
                f"heat {heat_mw} MW is outside "
                f"[{self.minimum_heat_mw}, {self.maximum_heat_mw}]"
            )

        candidates: list[float] = []
        for vertex in self.vertices:
            if abs(vertex.heat_mw - heat_mw) <= tolerance:
                candidates.append(vertex.power_gross_mw)

        for index, first in enumerate(self.vertices):
            for second in self.vertices[index + 1 :]:
                delta_heat = second.heat_mw - first.heat_mw
                if abs(delta_heat) <= tolerance:
                    continue
                weight_second = (heat_mw - first.heat_mw) / delta_heat
                if -tolerance <= weight_second <= 1.0 + tolerance:
                    weight_second = min(1.0, max(0.0, weight_second))
                    candidates.append(
                        (1.0 - weight_second) * first.power_gross_mw
                        + weight_second * second.power_gross_mw
                    )

        if not candidates:
            raise ValueError(f"No convex combination can provide heat {heat_mw} MW")
        return min(candidates)


@dataclass(frozen=True)
class CHPUnitSpec:
    name: str
    feasible_region: CHPFeasibleRegion
    heat_basis: HeatBasis
    auxiliary_rate: float

    def __post_init__(self) -> None:
        if not isinstance(self.heat_basis, HeatBasis):
            raise ValueError("heat_basis must be a HeatBasis value")
        if not isfinite(self.auxiliary_rate):
            raise ValueError("auxiliary_rate must be finite")
        if not 0.0 <= self.auxiliary_rate < 1.0:
            raise ValueError("auxiliary_rate must lie in [0, 1)")

    def require_resolved_heat_basis(self) -> None:
        if self.heat_basis is HeatBasis.UNRESOLVED:
            raise UnresolvedHeatBasisError(
                f"{self.name} heat basis must be confirmed as useful or extraction heat"
            )


@dataclass(frozen=True)
class CHPCommitmentSpec:
    """Evidence-bounded commitment and fuel contract for one CHP unit."""

    unit: CHPUnitSpec
    fuel_points: tuple[CHPFuelPoint, ...]
    low_load_fuel_rule: LowLoadFuelRule
    normal_ramp_mw_per_min: float | None = None
    unresolved_minimum_start_stop_hours: float | None = None
    unresolved_cycle_event_cost_cny: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.low_load_fuel_rule, LowLoadFuelRule):
            raise ValueError("low_load_fuel_rule must be selected explicitly")
        if len(self.fuel_points) < 2:
            raise ValueError("at least two raw fuel points are required")
        powers = tuple(point.power_gross_mw for point in self.fuel_points)
        if powers != tuple(sorted(powers)) or len(set(powers)) != len(powers):
            raise ValueError("fuel-point powers must be strictly increasing")
        if (
            self.normal_ramp_mw_per_min is not None
            and not isfinite(self.normal_ramp_mw_per_min)
        ):
            raise ValueError("normal online ramp must be finite")
        if self.normal_ramp_mw_per_min is not None and self.normal_ramp_mw_per_min < 0:
            raise ValueError("normal online ramp must be non-negative")
        if (
            self.unresolved_minimum_start_stop_hours is not None
            and not isfinite(self.unresolved_minimum_start_stop_hours)
        ):
            raise ValueError("source minimum start-stop field must be finite")
        if (
            self.unresolved_minimum_start_stop_hours is not None
            and self.unresolved_minimum_start_stop_hours <= 0
        ):
            raise ValueError("source minimum start-stop field must be positive")
        if (
            self.unresolved_cycle_event_cost_cny is not None
            and not isfinite(self.unresolved_cycle_event_cost_cny)
        ):
            raise ValueError("source cycle-event cost must be finite")
        if (
            self.unresolved_cycle_event_cost_cny is not None
            and self.unresolved_cycle_event_cost_cny < 0
        ):
            raise ValueError("source cycle-event cost must be non-negative")

    @property
    def name(self) -> str:
        return self.unit.name

    @property
    def feasible_region(self) -> CHPFeasibleRegion:
        return self.unit.feasible_region

    @property
    def heat_basis(self) -> HeatBasis:
        return self.unit.heat_basis

    @property
    def auxiliary_rate(self) -> float:
        return self.unit.auxiliary_rate

    def fuel_flow_knots(self) -> tuple[tuple[float, float], ...]:
        """Return modeling knots while keeping the raw source points separate."""

        raw_knots = tuple(
            (
                point.power_gross_mw,
                point.total_fuel_tce_per_hour(self.auxiliary_rate),
            )
            for point in self.fuel_points
        )
        minimum_feasible_power = min(
            vertex.power_gross_mw for vertex in self.feasible_region.vertices
        )
        if (
            self.low_load_fuel_rule is LowLoadFuelRule.RAISE_MIN_POWER_TO_105
            or raw_knots[0][0] <= minimum_feasible_power
        ):
            modeling_knots = raw_knots
        elif self.low_load_fuel_rule is LowLoadFuelRule.CLAMP_30_PERCENT_RATE:
            low_flow = coal_consumption_tph(
                gross_power_mw=minimum_feasible_power,
                auxiliary_rate=self.auxiliary_rate,
                supply_coal_rate_g_per_kwh=(
                    self.fuel_points[0].supply_coal_rate_g_per_kwh
                ),
            )
            modeling_knots = ((minimum_feasible_power, low_flow), *raw_knots)
        else:
            first_power, first_flow = raw_knots[0]
            second_power, second_flow = raw_knots[1]
            slope = (second_flow - first_flow) / (second_power - first_power)
            low_flow = first_flow + slope * (minimum_feasible_power - first_power)
            modeling_knots = ((minimum_feasible_power, low_flow), *raw_knots)

        modeling_powers = tuple(power for power, _ in modeling_knots)
        if any(not isfinite(power) for power in modeling_powers):
            raise ValueError("fuel-flow knot powers must be finite")
        if any(
            current <= previous
            for previous, current in zip(modeling_powers, modeling_powers[1:])
        ):
            raise ValueError("fuel-flow knot powers must be strictly increasing")
        if any(not isfinite(fuel_flow) for _, fuel_flow in modeling_knots):
            raise ValueError("fuel-flow knots must be finite")
        if any(fuel_flow < 0.0 for _, fuel_flow in modeling_knots):
            raise ValueError("fuel-flow knots must be non-negative")
        maximum_feasible_power = max(
            vertex.power_gross_mw for vertex in self.feasible_region.vertices
        )
        if modeling_knots[-1][0] < maximum_feasible_power:
            raise ValueError(
                "fuel-flow knots must cover the CHP feasible-region maximum power"
            )
        return modeling_knots

    @property
    def minimum_online_power_mw(self) -> float:
        return self.fuel_flow_knots()[0][0]


def coal_consumption_tph(
    *,
    gross_power_mw: float,
    auxiliary_rate: float,
    supply_coal_rate_g_per_kwh: float,
) -> float:
    """Convert supply-coal rate to tce/h while retaining a gross-power model."""

    if not isfinite(gross_power_mw):
        raise ValueError("gross_power_mw must be finite")
    if not isfinite(auxiliary_rate):
        raise ValueError("auxiliary_rate must be finite")
    if not isfinite(supply_coal_rate_g_per_kwh):
        raise ValueError("supply coal rate must be finite")
    if gross_power_mw < 0:
        raise ValueError("gross_power_mw must be non-negative")
    if not 0.0 <= auxiliary_rate < 1.0:
        raise ValueError("auxiliary_rate must lie in [0, 1)")
    if supply_coal_rate_g_per_kwh < 0:
        raise ValueError("supply coal rate must be non-negative")
    net_power_mw = gross_power_mw * (1.0 - auxiliary_rate)
    return net_power_mw * supply_coal_rate_g_per_kwh / 1000.0


def yangling_chp_specs(
    *,
    low_load_fuel_rule: LowLoadFuelRule | None = None,
) -> tuple[CHPCommitmentSpec, CHPCommitmentSpec]:
    """Return the two Yangling units without hiding the low-load assumption."""

    if low_load_fuel_rule is None:
        raise ValueError("low_load_fuel_rule must be selected explicitly")
    common_region = CHPFeasibleRegion(
        (
            CHPVertex(98.0, 0.0),
            CHPVertex(350.0, 0.0),
            CHPVertex(286.0, 438.0),
            CHPVertex(98.0, 83.0),
        )
    )
    powers = tuple(float(power) for power in range(105, 351, 35))
    rates_by_unit = (
        (
            394.556195140916,
            371.155307452574,
            329.25173575833,
            324.017882072051,
            319.958047664171,
            317.072232534689,
            315.360436683605,
            314.82266011092,
        ),
        (
            378.556195140916,
            360.155307452574,
            337.452770525067,
            327.448584358394,
            320.142748952555,
            315.535264307551,
            313.626130423382,
            314.415347300047,
        ),
    )
    auxiliary_rates = (0.0460139347345251, 0.0465236409080113)
    specs = tuple(
        CHPCommitmentSpec(
            unit=CHPUnitSpec(
                name=f"yangling_unit_{index}",
                feasible_region=common_region,
                heat_basis=HeatBasis.USEFUL,
                auxiliary_rate=auxiliary_rate,
            ),
            fuel_points=tuple(
                CHPFuelPoint(power, rate) for power, rate in zip(powers, rates)
            ),
            low_load_fuel_rule=low_load_fuel_rule,
            normal_ramp_mw_per_min=5.25,
            unresolved_minimum_start_stop_hours=3.5,
            unresolved_cycle_event_cost_cny=300_000.0,
        )
        for index, (rates, auxiliary_rate) in enumerate(
            zip(rates_by_unit, auxiliary_rates), start=1
        )
    )
    return specs[0], specs[1]


def add_chp_dispatch(block: object, periods: object, spec: CHPUnitSpec) -> object:
    """Attach the online table-vertex CHP feasible region to a Pyomo block."""

    from pyomo.environ import (
        Binary,
        Constraint,
        Expression,
        NonNegativeReals,
        RangeSet,
        Var,
    )

    spec.require_resolved_heat_basis()
    vertices = spec.feasible_region.vertices
    block.vertex_index = RangeSet(0, len(vertices) - 1)
    block.online = Var(periods, domain=Binary)
    block.vertex_weight = Var(periods, block.vertex_index, domain=NonNegativeReals)
    block.power_gross = Var(periods, domain=NonNegativeReals)
    block.heat = Var(periods, domain=NonNegativeReals)

    def weight_sum_rule(model: object, period: object) -> object:
        return (
            sum(model.vertex_weight[period, index] for index in model.vertex_index)
            == model.online[period]
        )

    def power_rule(model: object, period: object) -> object:
        return model.power_gross[period] == sum(
            vertices[index].power_gross_mw * model.vertex_weight[period, index]
            for index in model.vertex_index
        )

    def heat_rule(model: object, period: object) -> object:
        return model.heat[period] == sum(
            vertices[index].heat_mw * model.vertex_weight[period, index]
            for index in model.vertex_index
        )

    block.weight_sum = Constraint(periods, rule=weight_sum_rule)
    block.power_definition = Constraint(periods, rule=power_rule)
    block.heat_definition = Constraint(periods, rule=heat_rule)
    block.auxiliary_power = Expression(
        periods,
        rule=lambda model, period: spec.auxiliary_rate * model.power_gross[period],
    )
    return block


def add_chp_unit_commitment(
    block: object,
    periods: object,
    spec: CHPCommitmentSpec,
    *,
    time_step_hours: float = 1.0,
    initial_online: int = 0,
    cycle_event_cost_proxy_cny: float | None = None,
    fuel_segment_formulation: FuelSegmentFormulation = FuelSegmentFormulation.ONE_HOT,
    transition_formulation: CommitmentTransitionFormulation = (
        CommitmentTransitionFormulation.BINARY
    ),
    cyclic_period_blocks: tuple[tuple[object, ...], ...] | None = None,
) -> object:
    """Attach exact fuel segments and evidence-bounded commitment variables.

    Normal ramp evidence applies only between two modeled online endpoints.  A
    supplied cycle-event proxy is charged once per modeled startup; it is not a
    claim that the unresolved source cost is a separately identified startup
    cost.  With the default ``None``, transitions carry no monetary charge.
    """

    from pyomo.environ import (
        Binary,
        Constraint,
        Expression,
        NonNegativeReals,
        RangeSet,
        Set,
        Var,
    )

    if not isfinite(time_step_hours):
        raise ValueError("time_step_hours must be finite")
    if time_step_hours <= 0:
        raise ValueError("time_step_hours must be positive")
    if initial_online not in (0, 1):
        raise ValueError("initial_online must be zero or one")
    if not isinstance(fuel_segment_formulation, FuelSegmentFormulation):
        raise ValueError(
            "fuel_segment_formulation must be selected with FuelSegmentFormulation"
        )
    if not isinstance(transition_formulation, CommitmentTransitionFormulation):
        raise ValueError(
            "transition_formulation must use CommitmentTransitionFormulation"
        )
    if (
        cycle_event_cost_proxy_cny is not None
        and not isfinite(cycle_event_cost_proxy_cny)
    ):
        raise ValueError("cycle-event cost proxy must be finite")
    if cycle_event_cost_proxy_cny is not None and cycle_event_cost_proxy_cny < 0:
        raise ValueError("cycle-event cost proxy must be non-negative")

    is_ordered = getattr(periods, "isordered", None)
    if callable(is_ordered) and not is_ordered():
        raise ValueError("dispatch periods must be ordered")

    period_order = tuple(periods)
    if not period_order:
        raise ValueError("at least one dispatch period is required")
    validated_period_blocks = (
        None
        if cyclic_period_blocks is None
        else validate_cyclic_period_blocks(period_order, cyclic_period_blocks)
    )
    fuel_knots = spec.fuel_flow_knots()
    add_chp_dispatch(block, periods, spec.unit)
    segment_count = len(fuel_knots) - 1
    block.fuel_segment_index = RangeSet(0, segment_count - 1)
    if fuel_segment_formulation is FuelSegmentFormulation.ONE_HOT:
        block.fuel_segment_active = Var(
            periods,
            block.fuel_segment_index,
            domain=Binary,
        )
    else:
        block.fuel_segment_active = Var(
            periods,
            block.fuel_segment_index,
            domain=NonNegativeReals,
            bounds=(0.0, 1.0),
        )
    block.fuel_segment_fraction = Var(
        periods,
        block.fuel_segment_index,
        domain=NonNegativeReals,
        bounds=(0.0, 1.0),
    )
    block.fuel_tce_per_hour = Var(periods, domain=NonNegativeReals)

    block.fuel_segment_sum = Constraint(
        periods,
        rule=lambda model, period: sum(
            model.fuel_segment_active[period, segment]
            for segment in model.fuel_segment_index
        )
        == model.online[period],
    )
    if fuel_segment_formulation is FuelSegmentFormulation.LOGARITHMIC:
        code_bit_count = max(1, (segment_count - 1).bit_length())
        block.fuel_code_bit_index = RangeSet(0, code_bit_count - 1)
        block.fuel_code_bit = Var(
            periods,
            block.fuel_code_bit_index,
            domain=Binary,
        )

        def fuel_code_rule(model: object, period: object, bit: int) -> object:
            return sum(
                model.fuel_segment_active[period, segment]
                for segment in model.fuel_segment_index
                if (int(segment) >> int(bit)) & 1
            ) == model.fuel_code_bit[period, bit]

        block.fuel_code = Constraint(
            periods,
            block.fuel_code_bit_index,
            rule=fuel_code_rule,
        )
    block.fuel_fraction_activation = Constraint(
        periods,
        block.fuel_segment_index,
        rule=lambda model, period, segment: (
            model.fuel_segment_fraction[period, segment]
            <= model.fuel_segment_active[period, segment]
        ),
    )

    def fuel_power_rule(model: object, period: object) -> object:
        return model.power_gross[period] == sum(
            fuel_knots[segment][0]
            * model.fuel_segment_active[period, segment]
            + (fuel_knots[segment + 1][0] - fuel_knots[segment][0])
            * model.fuel_segment_fraction[period, segment]
            for segment in model.fuel_segment_index
        )

    def fuel_flow_rule(model: object, period: object) -> object:
        return model.fuel_tce_per_hour[period] == sum(
            fuel_knots[segment][1]
            * model.fuel_segment_active[period, segment]
            + (fuel_knots[segment + 1][1] - fuel_knots[segment][1])
            * model.fuel_segment_fraction[period, segment]
            for segment in model.fuel_segment_index
        )

    block.fuel_power_definition = Constraint(periods, rule=fuel_power_rule)
    block.fuel_flow_definition = Constraint(periods, rule=fuel_flow_rule)

    if transition_formulation is CommitmentTransitionFormulation.BINARY:
        block.startup = Var(periods, domain=Binary)
        block.shutdown = Var(periods, domain=Binary)
    else:
        block.startup = Var(periods, domain=NonNegativeReals, bounds=(0.0, 1.0))
        block.shutdown = Var(periods, domain=NonNegativeReals, bounds=(0.0, 1.0))
    first_period = period_order[0]
    if validated_period_blocks is None:
        previous_period = {
            period: period_order[index - 1]
            for index, period in enumerate(period_order)
            if index > 0
        }
    else:
        previous_period = {
            period: period_block[index - 1]
            for period_block in validated_period_blocks
            for index, period in enumerate(period_block)
        }

    def previous_online(model: object, period: object) -> object:
        if validated_period_blocks is None and period == first_period:
            return initial_online
        return model.online[previous_period[period]]

    def transition_rule(model: object, period: object) -> object:
        return (
            model.online[period] - previous_online(model, period)
            == model.startup[period] - model.shutdown[period]
        )

    block.commitment_transition = Constraint(periods, rule=transition_rule)
    if transition_formulation is CommitmentTransitionFormulation.BINARY:
        block.transition_exclusive = Constraint(
            periods,
            rule=lambda model, period: (
                model.startup[period] + model.shutdown[period] <= 1
            ),
        )
    else:
        block.startup_online_limit = Constraint(
            periods,
            rule=lambda model, period: model.startup[period] <= model.online[period],
        )
        block.startup_previous_offline_limit = Constraint(
            periods,
            rule=lambda model, period: (
                model.startup[period] <= 1 - previous_online(model, period)
            ),
        )
        block.shutdown_previous_online_limit = Constraint(
            periods,
            rule=lambda model, period: (
                model.shutdown[period] <= previous_online(model, period)
            ),
        )
        block.shutdown_offline_limit = Constraint(
            periods,
            rule=lambda model, period: (
                model.shutdown[period] <= 1 - model.online[period]
            ),
        )

    if spec.normal_ramp_mw_per_min is not None:
        ramp_period_order = (
            period_order[1:]
            if validated_period_blocks is None
            else period_order
        )
        block.ramp_periods = Set(initialize=ramp_period_order, ordered=True)
        ramp_allowance_mw = (
            spec.normal_ramp_mw_per_min * 60.0 * time_step_hours
        )
        ramp_big_m = max(
            vertex.power_gross_mw for vertex in spec.feasible_region.vertices
        )

        def ramp_up_rule(model: object, period: object) -> object:
            previous = previous_period[period]
            return (
                model.power_gross[period] - model.power_gross[previous]
                <= ramp_allowance_mw
                + ramp_big_m * (2 - model.online[period] - model.online[previous])
            )

        def ramp_down_rule(model: object, period: object) -> object:
            previous = previous_period[period]
            return (
                model.power_gross[previous] - model.power_gross[period]
                <= ramp_allowance_mw
                + ramp_big_m * (2 - model.online[period] - model.online[previous])
            )

        block.normal_ramp_up = Constraint(block.ramp_periods, rule=ramp_up_rule)
        block.normal_ramp_down = Constraint(block.ramp_periods, rule=ramp_down_rule)
    transition_proxy_rate = (
        0.0
        if cycle_event_cost_proxy_cny is None
        else cycle_event_cost_proxy_cny
    )
    block.transition_proxy_cost = Expression(
        expr=transition_proxy_rate
        * sum(block.startup[period] for period in period_order)
    )
    return block
