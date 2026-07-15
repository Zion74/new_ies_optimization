"""Auditable project-life economics for storage planning.

All monetary inputs use constant real currency from one disclosed price base
year.  The module converts explicit project cash flows to net present value
before applying the project-horizon capital recovery factor.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum
from numbers import Real


def _is_finite_real(value: object) -> bool:
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


@dataclass(frozen=True)
class AnnualHorizonSpec:
    """Immutable scoring weights that must represent one complete year."""

    period_weights: tuple[float, ...]
    expected_annual_hours: float = 8784.0

    def __post_init__(self) -> None:
        if not isinstance(self.period_weights, tuple) or not self.period_weights:
            raise ValueError("period_weights must be a non-empty immutable tuple")
        if any(
            not _is_finite_real(weight) or weight <= 0.0
            for weight in self.period_weights
        ):
            raise ValueError("period_weights must be finite and strictly positive")
        if (
            not _is_finite_real(self.expected_annual_hours)
            or self.expected_annual_hours <= 0.0
        ):
            raise ValueError("expected_annual_hours must be finite and positive")
        if float(self.expected_annual_hours) != 8784.0:
            raise ValueError(
                "expected_annual_hours must be exactly 8784 for the 2024 E0-D contract"
            )

    def weighted_hours(self, *, dt_hours: float) -> float:
        """Return scored hours after applying the dispatch time-step duration."""

        if not _is_finite_real(dt_hours) or dt_hours <= 0.0:
            raise ValueError("dt_hours must be finite and positive")
        hours = float(dt_hours) * math.fsum(
            float(weight) for weight in self.period_weights
        )
        if not math.isfinite(hours):
            raise ValueError("weighted annual hours must remain finite")
        return hours

    def validate_time_grid(self, *, period_count: int, dt_hours: float) -> None:
        """Require exact weight coverage and closure to the declared annual hours."""

        if (
            isinstance(period_count, bool)
            or not isinstance(period_count, int)
            or period_count <= 0
        ):
            raise ValueError("period_count must be a positive integer")
        if period_count != len(self.period_weights):
            raise ValueError(
                "period_weights must contain one value per dispatch period"
            )
        weighted_hours = self.weighted_hours(dt_hours=dt_hours)
        tolerance = 1e-9 * max(float(self.expected_annual_hours), 1.0)
        if not math.isclose(
            weighted_hours,
            float(self.expected_annual_hours),
            rel_tol=0.0,
            abs_tol=tolerance,
        ):
            raise ValueError(
                "weighted time grid must close to "
                f"{float(self.expected_annual_hours):g} annual hours; "
                f"received {weighted_hours:g}"
            )


@dataclass(frozen=True)
class AnnualDispatchBlock:
    """One ordered dispatch block with its own cyclic physical state boundary."""

    block_id: str
    periods: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.block_id, str) or not self.block_id.strip():
            raise ValueError("block_id must be a non-empty string")
        if not isinstance(self.periods, tuple) or not self.periods:
            raise ValueError("block periods must be a non-empty immutable tuple")
        if any(
            isinstance(period, bool)
            or not isinstance(period, int)
            or period < 0
            for period in self.periods
        ):
            raise ValueError("block periods must be non-negative integers")
        expected = tuple(range(self.periods[0], self.periods[0] + len(self.periods)))
        if self.periods != expected:
            raise ValueError("block periods must be strictly consecutive")


@dataclass(frozen=True)
class BlockAnnualHorizonSpec(AnnualHorizonSpec):
    """Annual scoring weights plus independent cyclic dispatch blocks.

    Zero weights are permitted only as a leading warm-up prefix inside a block.
    The legacy :class:`AnnualHorizonSpec` retains its strictly-positive contract.
    """

    dispatch_blocks: tuple[AnnualDispatchBlock, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.period_weights, tuple) or not self.period_weights:
            raise ValueError("period_weights must be a non-empty immutable tuple")
        if any(
            not _is_finite_real(weight) or weight < 0.0
            for weight in self.period_weights
        ):
            raise ValueError("block period_weights must be finite and non-negative")
        if not any(float(weight) > 0.0 for weight in self.period_weights):
            raise ValueError("at least one block period weight must be positive")
        if (
            not _is_finite_real(self.expected_annual_hours)
            or self.expected_annual_hours <= 0.0
        ):
            raise ValueError("expected_annual_hours must be finite and positive")
        if float(self.expected_annual_hours) != 8784.0:
            raise ValueError(
                "expected_annual_hours must be exactly 8784 for the 2024 E0-D contract"
            )
        if not isinstance(self.dispatch_blocks, tuple) or not self.dispatch_blocks:
            raise ValueError("dispatch_blocks must be a non-empty immutable tuple")
        if any(
            not isinstance(block, AnnualDispatchBlock)
            for block in self.dispatch_blocks
        ):
            raise ValueError("dispatch_blocks must contain AnnualDispatchBlock values")
        block_ids = tuple(block.block_id for block in self.dispatch_blocks)
        if len(set(block_ids)) != len(block_ids):
            raise ValueError("dispatch block ids must be unique")
        flattened_periods = tuple(
            period for block in self.dispatch_blocks for period in block.periods
        )
        if flattened_periods != tuple(range(len(self.period_weights))):
            raise ValueError(
                "dispatch blocks must form an ordered, exact partition of all periods"
            )
        for block in self.dispatch_blocks:
            seen_scored_period = False
            for period in block.periods:
                weight = float(self.period_weights[period])
                if weight > 0.0:
                    seen_scored_period = True
                elif seen_scored_period:
                    raise ValueError(
                        "zero-weight warm-up periods must precede scored periods "
                        f"within block {block.block_id}"
                    )
            if not seen_scored_period:
                raise ValueError(
                    f"dispatch block {block.block_id} must contain a scored period"
                )

    @property
    def cyclic_period_blocks(self) -> tuple[tuple[int, ...], ...]:
        """Return the period partition consumed by block-cyclic components."""

        return tuple(block.periods for block in self.dispatch_blocks)


def validate_cyclic_period_blocks(
    periods: tuple[object, ...],
    cyclic_period_blocks: tuple[tuple[object, ...], ...],
) -> tuple[tuple[object, ...], ...]:
    """Validate an ordered exact partition used by block-cyclic components."""

    if not isinstance(cyclic_period_blocks, tuple) or not cyclic_period_blocks:
        raise ValueError("cyclic_period_blocks must be a non-empty immutable tuple")
    if any(not isinstance(block, tuple) or not block for block in cyclic_period_blocks):
        raise ValueError("every cyclic period block must be a non-empty tuple")
    flattened = tuple(period for block in cyclic_period_blocks for period in block)
    if flattened != periods:
        raise ValueError(
            "cyclic period blocks must form an ordered, exact partition of periods"
        )
    return cyclic_period_blocks


@dataclass(frozen=True)
class ProjectFinance:
    """Common real-discounting contract for one planning project."""

    project_years: int
    real_discount_rate: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.project_years, bool)
            or not isinstance(self.project_years, int)
            or self.project_years <= 0
        ):
            raise ValueError("project_years must be a positive integer")
        if (
            not _is_finite_real(self.real_discount_rate)
            or self.real_discount_rate < 0.0
        ):
            raise ValueError("real_discount_rate must be finite and non-negative")

    def discount_factor(self, year: float) -> float:
        """Return the year-zero present-value factor for a real cash flow."""

        if not _is_finite_real(year) or year < 0.0:
            raise ValueError("cash-flow year must be finite and non-negative")
        return (1.0 + self.real_discount_rate) ** (-year)

    @property
    def present_value_annuity_factor(self) -> float:
        """Present value of one real currency unit paid at each year end."""

        if self.real_discount_rate == 0.0:
            return float(self.project_years)
        rate = self.real_discount_rate
        log_growth = self.project_years * math.log1p(rate)
        return -math.expm1(-log_growth) / rate

    @property
    def capital_recovery_factor(self) -> float:
        """Project-horizon factor that converts NPV to equivalent annual cost."""

        return 1.0 / self.present_value_annuity_factor

    def equivalent_annual_cost(self, net_present_value: float) -> float:
        """Convert a finite project NPV to an equivalent real annual amount."""

        if not _is_finite_real(net_present_value):
            raise ValueError("net_present_value must be finite")
        return net_present_value * self.capital_recovery_factor


class CashFlowKind(str, Enum):
    """Kinds of project cash flow retained in an audit ledger."""

    INITIAL_CAPEX = "initial_capex"
    REPLACEMENT = "replacement"
    FIXED_OM = "fixed_om"
    RESIDUAL_CREDIT = "residual_credit"


class LifecycleAssetClass(str, Enum):
    """Accounting role used to make BESS-cell exclusion structural."""

    GENERIC_COMPONENT = "generic_component"
    BESS_NON_CELL = "bess_non_cell"
    BESS_CELL = "bess_cell"
    TES_COMPONENT = "tes_component"
    SALT_TO_STEAM_GENERATOR = "salt_to_steam_generator"
    EXISTING_TURBINE_REUSE = "existing_turbine_reuse"
    NEW_POWER_BLOCK = "new_power_block"


@dataclass(frozen=True)
class CashFlowEvent:
    """One real, per-capacity-unit cash flow and its discounted value."""

    kind: CashFlowKind
    year: float
    amount_per_unit: float
    discount_factor: float

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CashFlowKind):
            raise ValueError("kind must be selected with the CashFlowKind enum")
        if not _is_finite_real(self.year) or self.year < 0.0:
            raise ValueError("cash-flow year must be finite and non-negative")
        if self.kind is CashFlowKind.INITIAL_CAPEX:
            if self.year != 0.0:
                raise ValueError("initial CAPEX must occur at year zero")
        elif self.year <= 0.0:
            raise ValueError("non-initial cash flows must occur after year zero")
        if not _is_finite_real(self.amount_per_unit):
            raise ValueError("cash-flow amount must be finite")
        if self.kind is CashFlowKind.RESIDUAL_CREDIT:
            if self.amount_per_unit > 0.0:
                raise ValueError("residual credit must be zero or negative")
        elif self.amount_per_unit < 0.0:
            raise ValueError("cost cash flows must be non-negative")
        if (
            not _is_finite_real(self.discount_factor)
            or not 0.0 <= self.discount_factor <= 1.0
        ):
            raise ValueError("discount_factor must lie in [0, 1]")

    @property
    def present_value_per_unit(self) -> float:
        return self.amount_per_unit * self.discount_factor


@dataclass(frozen=True)
class LifecycleCostSpec:
    """Real unit-cost assumptions for one replaceable physical asset."""

    asset_id: str
    capacity_unit: str
    currency: str
    price_base_year: int
    initial_cost_per_unit: float
    service_life_years: float
    asset_class: LifecycleAssetClass = LifecycleAssetClass.GENERIC_COMPONENT
    replacement_cost_per_unit: float | None = None
    fixed_om_per_unit_year: float = 0.0
    residual_recovery_fraction: float = 1.0

    def __post_init__(self) -> None:
        for field_name in ("asset_id", "capacity_unit", "currency"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if (
            isinstance(self.price_base_year, bool)
            or not isinstance(self.price_base_year, int)
            or self.price_base_year <= 0
        ):
            raise ValueError("price_base_year must be a positive integer")
        if not isinstance(self.asset_class, LifecycleAssetClass):
            raise ValueError(
                "asset_class must be selected with the LifecycleAssetClass enum"
            )

        non_negative_values = {
            "initial_cost_per_unit": self.initial_cost_per_unit,
            "fixed_om_per_unit_year": self.fixed_om_per_unit_year,
        }
        if self.replacement_cost_per_unit is not None:
            non_negative_values["replacement_cost_per_unit"] = (
                self.replacement_cost_per_unit
            )
        for name, value in non_negative_values.items():
            if not _is_finite_real(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        if (
            not _is_finite_real(self.service_life_years)
            or self.service_life_years <= 0.0
        ):
            raise ValueError("service_life_years must be finite and positive")
        if (
            not _is_finite_real(self.residual_recovery_fraction)
            or not 0.0 <= self.residual_recovery_fraction <= 1.0
        ):
            raise ValueError("residual_recovery_fraction must lie in [0, 1]")
        if self.asset_class is LifecycleAssetClass.EXISTING_TURBINE_REUSE and (
            self.initial_cost_per_unit != 0.0
            or (
                self.replacement_cost_per_unit is not None
                and self.replacement_cost_per_unit != 0.0
            )
        ):
            raise ValueError("existing turbine reuse must not carry capital cost")

    @property
    def resolved_replacement_cost_per_unit(self) -> float:
        if self.replacement_cost_per_unit is None:
            return self.initial_cost_per_unit
        return self.replacement_cost_per_unit


@dataclass(frozen=True)
class PriceBasisConversion:
    """Explicit price-index and FX bridge between two disclosed cost bases."""

    source_currency: str
    source_price_base_year: int
    target_currency: str
    target_price_base_year: int
    source_price_index: float
    target_price_index: float
    target_currency_per_source_currency: float
    price_index_series_id: str
    exchange_rate_series_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "source_currency",
            "target_currency",
            "price_index_series_id",
            "exchange_rate_series_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        for field_name in ("source_currency", "target_currency"):
            value = getattr(self, field_name)
            if len(value) != 3 or not value.isalpha() or value != value.upper():
                raise ValueError(
                    f"{field_name} must be an uppercase ISO 4217 currency code"
                )
        for field_name in ("source_price_base_year", "target_price_base_year"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        for field_name in (
            "source_price_index",
            "target_price_index",
            "target_currency_per_source_currency",
        ):
            value = getattr(self, field_name)
            if not _is_finite_real(value) or value <= 0.0:
                raise ValueError(f"{field_name} must be finite and positive")
        if (
            self.source_currency == self.target_currency
            and self.target_currency_per_source_currency != 1.0
        ):
            raise ValueError(
                "same-currency conversion must use an exchange-rate factor of one"
            )

    @property
    def inflation_factor(self) -> float:
        return float(self.target_price_index) / float(self.source_price_index)

    @property
    def conversion_factor(self) -> float:
        factor = self.inflation_factor * float(self.target_currency_per_source_currency)
        if not math.isfinite(factor) or factor <= 0.0:
            raise ValueError("price-basis conversion factor must remain finite")
        return factor


@dataclass(frozen=True)
class BESSVariableOMSpec:
    """Variable BESS O&M charged once on AC-side discharge throughput."""

    currency: str
    price_base_year: int
    cost_per_ac_discharge_mwh: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.currency, str)
            or len(self.currency) != 3
            or not self.currency.isalpha()
            or self.currency != self.currency.upper()
        ):
            raise ValueError("currency must be an uppercase ISO 4217 code")
        if (
            isinstance(self.price_base_year, bool)
            or not isinstance(self.price_base_year, int)
            or self.price_base_year <= 0
        ):
            raise ValueError("price_base_year must be a positive integer")
        if (
            not _is_finite_real(self.cost_per_ac_discharge_mwh)
            or self.cost_per_ac_discharge_mwh < 0.0
        ):
            raise ValueError(
                "cost_per_ac_discharge_mwh must be finite and non-negative"
            )


@dataclass(frozen=True)
class BESSVariableOMConversion:
    """Auditable price-basis bridge for an AC-discharge variable O&M rate."""

    source_spec: BESSVariableOMSpec
    conversion: PriceBasisConversion
    converted_spec: BESSVariableOMSpec

    def __post_init__(self) -> None:
        if not isinstance(self.source_spec, BESSVariableOMSpec) or not isinstance(
            self.converted_spec,
            BESSVariableOMSpec,
        ):
            raise ValueError("variable O&M conversion specs must be canonical")
        if not isinstance(self.conversion, PriceBasisConversion):
            raise ValueError("variable O&M conversion must be canonical")
        if (
            self.source_spec.currency != self.conversion.source_currency
            or self.source_spec.price_base_year
            != self.conversion.source_price_base_year
        ):
            raise ValueError("variable O&M conversion source must be canonical")
        expected = BESSVariableOMSpec(
            currency=self.conversion.target_currency,
            price_base_year=self.conversion.target_price_base_year,
            cost_per_ac_discharge_mwh=(
                self.source_spec.cost_per_ac_discharge_mwh
                * self.conversion.conversion_factor
            ),
        )
        if self.converted_spec != expected:
            raise ValueError("variable O&M conversion must be canonical")

    @property
    def conversion_factor(self) -> float:
        return self.conversion.conversion_factor


def convert_bess_variable_om_spec(
    spec: BESSVariableOMSpec,
    conversion: PriceBasisConversion,
) -> BESSVariableOMConversion:
    """Convert a discharge-basis BESS variable O&M rate exactly once."""

    if not isinstance(spec, BESSVariableOMSpec):
        raise ValueError("spec must be a BESSVariableOMSpec")
    if not isinstance(conversion, PriceBasisConversion):
        raise ValueError("conversion must be a PriceBasisConversion")
    if (
        spec.currency != conversion.source_currency
        or spec.price_base_year != conversion.source_price_base_year
    ):
        raise ValueError(
            "spec must match the conversion source currency and price base year"
        )
    converted = BESSVariableOMSpec(
        currency=conversion.target_currency,
        price_base_year=conversion.target_price_base_year,
        cost_per_ac_discharge_mwh=(
            spec.cost_per_ac_discharge_mwh * conversion.conversion_factor
        ),
    )
    return BESSVariableOMConversion(
        source_spec=spec,
        conversion=conversion,
        converted_spec=converted,
    )


@dataclass(frozen=True)
class LifecycleCostConversion:
    """Auditable source, conversion contract, and converted lifecycle spec."""

    source_spec: LifecycleCostSpec
    conversion: PriceBasisConversion
    converted_spec: LifecycleCostSpec

    def __post_init__(self) -> None:
        if not isinstance(self.source_spec, LifecycleCostSpec) or not isinstance(
            self.converted_spec,
            LifecycleCostSpec,
        ):
            raise ValueError("lifecycle cost conversion specs must be canonical")
        if not isinstance(self.conversion, PriceBasisConversion):
            raise ValueError("lifecycle cost conversion must be canonical")
        if (
            self.source_spec.currency != self.conversion.source_currency
            or self.source_spec.price_base_year
            != self.conversion.source_price_base_year
        ):
            raise ValueError("lifecycle cost conversion source must be canonical")
        factor = self.conversion.conversion_factor
        replacement_cost = self.source_spec.replacement_cost_per_unit
        expected = replace(
            self.source_spec,
            currency=self.conversion.target_currency,
            price_base_year=self.conversion.target_price_base_year,
            initial_cost_per_unit=self.source_spec.initial_cost_per_unit * factor,
            replacement_cost_per_unit=(
                None if replacement_cost is None else replacement_cost * factor
            ),
            fixed_om_per_unit_year=(self.source_spec.fixed_om_per_unit_year * factor),
        )
        if self.converted_spec != expected:
            raise ValueError("lifecycle cost conversion must be canonical")

    @property
    def inflation_factor(self) -> float:
        return self.conversion.inflation_factor

    @property
    def conversion_factor(self) -> float:
        return self.conversion.conversion_factor


def convert_lifecycle_cost_spec(
    spec: LifecycleCostSpec,
    conversion: PriceBasisConversion,
) -> LifecycleCostConversion:
    """Convert all monetary fields once while retaining an explicit audit trail."""

    if not isinstance(spec, LifecycleCostSpec):
        raise ValueError("spec must be a LifecycleCostSpec")
    if not isinstance(conversion, PriceBasisConversion):
        raise ValueError("conversion must be a PriceBasisConversion")
    if (
        spec.currency != conversion.source_currency
        or spec.price_base_year != conversion.source_price_base_year
    ):
        raise ValueError(
            "spec must match the conversion source currency and price base year"
        )
    factor = conversion.conversion_factor
    replacement_cost = spec.replacement_cost_per_unit
    converted = replace(
        spec,
        currency=conversion.target_currency,
        price_base_year=conversion.target_price_base_year,
        initial_cost_per_unit=spec.initial_cost_per_unit * factor,
        replacement_cost_per_unit=(
            None if replacement_cost is None else replacement_cost * factor
        ),
        fixed_om_per_unit_year=spec.fixed_om_per_unit_year * factor,
    )
    return LifecycleCostConversion(
        source_spec=spec,
        conversion=conversion,
        converted_spec=converted,
    )


@dataclass(frozen=True)
class LifecycleCostLedger:
    """Project NPV and EAC audit for one unit of installed asset capacity."""

    spec: LifecycleCostSpec
    finance: ProjectFinance
    events: tuple[CashFlowEvent, ...]
    replacement_years: tuple[float, ...]
    remaining_life_fraction: float
    terminal_residual_value_per_unit: float
    initial_cost_present_value: float
    replacement_cost_present_value: float
    residual_credit_present_value: float
    fixed_om_present_value: float
    capital_net_present_value: float
    total_net_present_value: float
    annualized_capital_cost: float
    annualized_fixed_om_cost: float
    total_equivalent_annual_cost: float


def _replacement_years(
    project_years: int, service_life_years: float
) -> tuple[float, ...]:
    years: list[float] = []
    event_number = 1
    endpoint_tolerance = 1e-12 * max(float(project_years), service_life_years, 1.0)
    while True:
        replacement_year = event_number * service_life_years
        if replacement_year >= project_years - endpoint_tolerance:
            break
        years.append(replacement_year)
        event_number += 1
        if event_number > 1_000_000:
            raise ValueError("service_life_years creates too many replacement events")
    return tuple(years)


def annualize_lifecycle_cost(
    spec: LifecycleCostSpec,
    finance: ProjectFinance,
) -> LifecycleCostLedger:
    """Build the sole all-in lifecycle ledger for one installed asset unit."""

    replacement_years = _replacement_years(
        finance.project_years,
        spec.service_life_years,
    )
    events = [
        CashFlowEvent(
            kind=CashFlowKind.INITIAL_CAPEX,
            year=0.0,
            amount_per_unit=spec.initial_cost_per_unit,
            discount_factor=1.0,
        )
    ]
    replacement_cost = spec.resolved_replacement_cost_per_unit
    events.extend(
        CashFlowEvent(
            kind=CashFlowKind.REPLACEMENT,
            year=year,
            amount_per_unit=replacement_cost,
            discount_factor=finance.discount_factor(year),
        )
        for year in replacement_years
    )
    events.extend(
        CashFlowEvent(
            kind=CashFlowKind.FIXED_OM,
            year=float(year),
            amount_per_unit=spec.fixed_om_per_unit_year,
            discount_factor=finance.discount_factor(float(year)),
        )
        for year in range(1, finance.project_years + 1)
    )

    last_installation_year = replacement_years[-1] if replacement_years else 0.0
    last_installation_cost = (
        replacement_cost if replacement_years else spec.initial_cost_per_unit
    )
    age_at_project_end = finance.project_years - last_installation_year
    remaining_life_fraction = max(
        0.0,
        min(
            1.0,
            (spec.service_life_years - age_at_project_end) / spec.service_life_years,
        ),
    )
    terminal_residual = (
        spec.residual_recovery_fraction
        * remaining_life_fraction
        * last_installation_cost
    )
    events.append(
        CashFlowEvent(
            kind=CashFlowKind.RESIDUAL_CREDIT,
            year=float(finance.project_years),
            amount_per_unit=-terminal_residual,
            discount_factor=finance.discount_factor(float(finance.project_years)),
        )
    )
    kind_order = {
        CashFlowKind.INITIAL_CAPEX: 0,
        CashFlowKind.REPLACEMENT: 1,
        CashFlowKind.FIXED_OM: 2,
        CashFlowKind.RESIDUAL_CREDIT: 3,
    }
    ordered_events = tuple(
        sorted(events, key=lambda event: (event.year, kind_order[event.kind]))
    )

    initial_pv = sum(
        event.present_value_per_unit
        for event in ordered_events
        if event.kind is CashFlowKind.INITIAL_CAPEX
    )
    replacement_pv = sum(
        event.present_value_per_unit
        for event in ordered_events
        if event.kind is CashFlowKind.REPLACEMENT
    )
    residual_credit_pv = -sum(
        event.present_value_per_unit
        for event in ordered_events
        if event.kind is CashFlowKind.RESIDUAL_CREDIT
    )
    fixed_om_pv = sum(
        event.present_value_per_unit
        for event in ordered_events
        if event.kind is CashFlowKind.FIXED_OM
    )
    capital_npv = initial_pv + replacement_pv - residual_credit_pv
    total_npv = capital_npv + fixed_om_pv
    annualized_capital = finance.equivalent_annual_cost(capital_npv)
    annualized_fixed_om = finance.equivalent_annual_cost(fixed_om_pv)

    return LifecycleCostLedger(
        spec=spec,
        finance=finance,
        events=ordered_events,
        replacement_years=replacement_years,
        remaining_life_fraction=remaining_life_fraction,
        terminal_residual_value_per_unit=terminal_residual,
        initial_cost_present_value=initial_pv,
        replacement_cost_present_value=replacement_pv,
        residual_credit_present_value=residual_credit_pv,
        fixed_om_present_value=fixed_om_pv,
        capital_net_present_value=capital_npv,
        total_net_present_value=total_npv,
        annualized_capital_cost=annualized_capital,
        annualized_fixed_om_cost=annualized_fixed_om,
        total_equivalent_annual_cost=annualized_capital + annualized_fixed_om,
    )


@dataclass(frozen=True)
class BESSCellDegradationSpec:
    """Pre-solve assumptions for linear calendar/AC-throughput calibration."""

    cell_lifecycle: LifecycleCostSpec
    cycle_life_ac_efc: float
    reference_annual_ac_efc: float
    ac_deliverable_fraction: float

    def __post_init__(self) -> None:
        if not isinstance(self.cell_lifecycle, LifecycleCostSpec):
            raise ValueError("cell_lifecycle must be a LifecycleCostSpec")
        if self.cell_lifecycle.asset_class is not LifecycleAssetClass.BESS_CELL:
            raise ValueError("cell_lifecycle must use the BESS_CELL asset class")
        if self.cell_lifecycle.capacity_unit != "MWh_internal":
            raise ValueError("BESS cell capacity_unit must be 'MWh_internal'")
        if self.cell_lifecycle.fixed_om_per_unit_year != 0.0:
            raise ValueError(
                "BESS cell FOM must be a separate non-cell lifecycle ledger"
            )
        for name, value in (
            ("cycle_life_ac_efc", self.cycle_life_ac_efc),
            ("reference_annual_ac_efc", self.reference_annual_ac_efc),
            ("ac_deliverable_fraction", self.ac_deliverable_fraction),
        ):
            if not _is_finite_real(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if self.ac_deliverable_fraction > 1.0:
            raise ValueError("ac_deliverable_fraction must not exceed one")


def _bess_cell_calibration_values(
    degradation: BESSCellDegradationSpec,
    finance: ProjectFinance,
) -> tuple[
    LifecycleCostLedger,
    LifecycleCostLedger,
    float,
    float,
    float,
    float,
]:
    calendar_life = degradation.cell_lifecycle.service_life_years
    reference_damage_rate = (
        1.0 / calendar_life
        + degradation.reference_annual_ac_efc / degradation.cycle_life_ac_efc
    )
    reference_effective_life = 1.0 / reference_damage_rate
    zero_cycle_ledger = annualize_lifecycle_cost(
        degradation.cell_lifecycle,
        finance,
    )
    reference_cycle_ledger = annualize_lifecycle_cost(
        replace(
            degradation.cell_lifecycle,
            service_life_years=reference_effective_life,
        ),
        finance,
    )
    zero_anchor = zero_cycle_ledger.annualized_capital_cost
    reference_anchor = reference_cycle_ledger.annualized_capital_cost
    comparison_tolerance = 1e-10 * max(abs(zero_anchor), abs(reference_anchor), 1.0)
    if reference_anchor < zero_anchor - comparison_tolerance:
        raise ValueError(
            "reference-cycle lifecycle EAC must not be below zero-cycle EAC"
        )
    cycle_cost = (reference_anchor - zero_anchor) / (
        degradation.reference_annual_ac_efc * degradation.ac_deliverable_fraction
    )
    if cycle_cost < 0.0 and abs(cycle_cost) <= comparison_tolerance:
        cycle_cost = 0.0
    return (
        zero_cycle_ledger,
        reference_cycle_ledger,
        reference_effective_life,
        zero_anchor,
        reference_anchor,
        cycle_cost,
    )


@dataclass(frozen=True)
class BESSCellCostCalibration:
    """Two-anchor linear cell-cost coefficients on the AC discharge basis."""

    degradation: BESSCellDegradationSpec
    finance: ProjectFinance
    zero_cycle_ledger: LifecycleCostLedger
    reference_cycle_ledger: LifecycleCostLedger
    reference_effective_life_years: float
    zero_cycle_anchor_eac_per_nominal_mwh: float
    reference_cycle_anchor_eac_per_nominal_mwh: float
    calendar_cost_per_nominal_mwh_year: float
    cycle_cost_per_ac_discharge_mwh: float

    def __post_init__(self) -> None:
        if not isinstance(self.degradation, BESSCellDegradationSpec) or not isinstance(
            self.finance,
            ProjectFinance,
        ):
            raise ValueError("BESS cell cost calibration must be canonical")
        expected = _bess_cell_calibration_values(self.degradation, self.finance)
        expected_zero, expected_reference, expected_life, a0, a1, cycle = expected
        scalar_pairs = (
            (self.reference_effective_life_years, expected_life),
            (self.zero_cycle_anchor_eac_per_nominal_mwh, a0),
            (self.reference_cycle_anchor_eac_per_nominal_mwh, a1),
            (self.calendar_cost_per_nominal_mwh_year, a0),
            (self.cycle_cost_per_ac_discharge_mwh, cycle),
        )
        if (
            self.zero_cycle_ledger != expected_zero
            or self.reference_cycle_ledger != expected_reference
            or self.reference_effective_life_years <= 0.0
            or self.zero_cycle_anchor_eac_per_nominal_mwh < 0.0
            or self.reference_cycle_anchor_eac_per_nominal_mwh < 0.0
            or self.calendar_cost_per_nominal_mwh_year < 0.0
            or self.cycle_cost_per_ac_discharge_mwh < 0.0
            or any(
                not _is_finite_real(actual)
                or not math.isclose(
                    actual,
                    expected_value,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
                for actual, expected_value in scalar_pairs
            )
        ):
            raise ValueError("BESS cell cost calibration must be canonical")

    @property
    def cell_asset_id(self) -> str:
        return self.degradation.cell_lifecycle.asset_id

    @property
    def cell_lifecycle_spec(self) -> LifecycleCostSpec:
        return self.degradation.cell_lifecycle

    @property
    def project_finance(self) -> ProjectFinance:
        return self.finance

    @property
    def reference_annual_ac_efc(self) -> float:
        return self.degradation.reference_annual_ac_efc

    @property
    def ac_deliverable_fraction(self) -> float:
        return self.degradation.ac_deliverable_fraction

    def maximum_annual_ac_throughput_mwh(
        self,
        nominal_energy_mwh: float,
    ) -> float:
        if not _is_finite_real(nominal_energy_mwh) or nominal_energy_mwh < 0.0:
            raise ValueError("nominal_energy_mwh must be finite and non-negative")
        return (
            self.degradation.reference_annual_ac_efc
            * self.degradation.ac_deliverable_fraction
            * nominal_energy_mwh
        )

    def annual_cell_cost(
        self,
        *,
        nominal_energy_mwh: float,
        ac_discharge_throughput_mwh: float,
    ) -> float:
        if (
            not _is_finite_real(ac_discharge_throughput_mwh)
            or ac_discharge_throughput_mwh < 0.0
        ):
            raise ValueError(
                "ac_discharge_throughput_mwh must be finite and non-negative"
            )
        maximum_throughput = self.maximum_annual_ac_throughput_mwh(nominal_energy_mwh)
        tolerance = 1e-9 * max(maximum_throughput, 1.0)
        if ac_discharge_throughput_mwh > maximum_throughput + tolerance:
            raise ValueError("AC discharge throughput exceeds the calibrated EFC limit")
        return (
            self.calendar_cost_per_nominal_mwh_year * nominal_energy_mwh
            + self.cycle_cost_per_ac_discharge_mwh * ac_discharge_throughput_mwh
        )


def calibrate_bess_cell_cost(
    degradation: BESSCellDegradationSpec,
    finance: ProjectFinance,
) -> BESSCellCostCalibration:
    """Calibrate a linear cell cost at zero and reference annual AC cycling."""

    (
        zero_cycle_ledger,
        reference_cycle_ledger,
        reference_effective_life,
        zero_anchor,
        reference_anchor,
        cycle_cost,
    ) = _bess_cell_calibration_values(degradation, finance)

    return BESSCellCostCalibration(
        degradation=degradation,
        finance=finance,
        zero_cycle_ledger=zero_cycle_ledger,
        reference_cycle_ledger=reference_cycle_ledger,
        reference_effective_life_years=reference_effective_life,
        zero_cycle_anchor_eac_per_nominal_mwh=zero_anchor,
        reference_cycle_anchor_eac_per_nominal_mwh=reference_anchor,
        calendar_cost_per_nominal_mwh_year=zero_anchor,
        cycle_cost_per_ac_discharge_mwh=cycle_cost,
    )


@dataclass(frozen=True)
class FixedLifeBESSCellCost:
    """Fixed-life sensitivity in which cell throughput carries no cost."""

    lifecycle_ledger: LifecycleCostLedger
    calendar_cost_per_nominal_mwh_year: float
    cycle_cost_per_ac_discharge_mwh: float = 0.0
    reference_calibration: BESSCellCostCalibration | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.lifecycle_ledger, LifecycleCostLedger):
            raise ValueError("fixed-life BESS cell cost must be canonical")
        spec = self.lifecycle_ledger.spec
        expected_ledger = annualize_lifecycle_cost(
            spec,
            self.lifecycle_ledger.finance,
        )
        if (
            self.lifecycle_ledger != expected_ledger
            or spec.asset_class is not LifecycleAssetClass.BESS_CELL
            or spec.capacity_unit != "MWh_internal"
            or spec.fixed_om_per_unit_year != 0.0
            or not _is_finite_real(self.calendar_cost_per_nominal_mwh_year)
            or self.calendar_cost_per_nominal_mwh_year < 0.0
            or not math.isclose(
                self.calendar_cost_per_nominal_mwh_year,
                expected_ledger.annualized_capital_cost,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            or self.cycle_cost_per_ac_discharge_mwh != 0.0
        ):
            raise ValueError("fixed-life BESS cell cost must be canonical")
        if self.reference_calibration is not None and (
            not isinstance(self.reference_calibration, BESSCellCostCalibration)
            or self.reference_calibration.project_finance
            != self.lifecycle_ledger.finance
            or self.reference_calibration.cell_lifecycle_spec != spec
        ):
            raise ValueError(
                "fixed-life BESS reference calibration must match its cell ledger"
            )

    @property
    def cell_asset_id(self) -> str:
        return self.lifecycle_ledger.spec.asset_id

    @property
    def cell_lifecycle_spec(self) -> LifecycleCostSpec:
        return self.lifecycle_ledger.spec

    @property
    def project_finance(self) -> ProjectFinance:
        return self.lifecycle_ledger.finance

    @property
    def reference_annual_ac_efc(self) -> float | None:
        if self.reference_calibration is None:
            return None
        return self.reference_calibration.reference_annual_ac_efc

    @property
    def ac_deliverable_fraction(self) -> float | None:
        if self.reference_calibration is None:
            return None
        return self.reference_calibration.ac_deliverable_fraction

    def annual_cell_cost(
        self,
        *,
        nominal_energy_mwh: float,
        ac_discharge_throughput_mwh: float,
    ) -> float:
        for name, value in (
            ("nominal_energy_mwh", nominal_energy_mwh),
            ("ac_discharge_throughput_mwh", ac_discharge_throughput_mwh),
        ):
            if not _is_finite_real(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        return self.calendar_cost_per_nominal_mwh_year * nominal_energy_mwh


def fixed_life_bess_cell_cost(
    cell_lifecycle: LifecycleCostSpec,
    finance: ProjectFinance,
) -> FixedLifeBESSCellCost:
    """Build the disclosed no-throughput-cost sensitivity cell ledger."""

    if not isinstance(cell_lifecycle, LifecycleCostSpec):
        raise ValueError("cell_lifecycle must be a LifecycleCostSpec")
    if cell_lifecycle.asset_class is not LifecycleAssetClass.BESS_CELL:
        raise ValueError("cell_lifecycle must use the BESS_CELL asset class")
    if cell_lifecycle.capacity_unit != "MWh_internal":
        raise ValueError("BESS cell capacity_unit must be 'MWh_internal'")
    if cell_lifecycle.fixed_om_per_unit_year != 0.0:
        raise ValueError("BESS cell FOM must be a separate non-cell lifecycle ledger")
    ledger = annualize_lifecycle_cost(cell_lifecycle, finance)
    return FixedLifeBESSCellCost(
        lifecycle_ledger=ledger,
        calendar_cost_per_nominal_mwh_year=ledger.annualized_capital_cost,
    )


def fixed_life_bess_cell_cost_from_calibration(
    calibration: BESSCellCostCalibration,
) -> FixedLifeBESSCellCost:
    """Keep a calibration's AC-EFC feasible set while removing cycle charges."""

    if not isinstance(calibration, BESSCellCostCalibration):
        raise ValueError("calibration must be a BESSCellCostCalibration")
    fixed_life = fixed_life_bess_cell_cost(
        calibration.cell_lifecycle_spec,
        calibration.project_finance,
    )
    return replace(fixed_life, reference_calibration=calibration)


@dataclass(frozen=True)
class AssetAnnualCost:
    """Quantity-scaled annual cost for one portfolio asset."""

    asset_id: str
    asset_class: LifecycleAssetClass
    capacity_unit: str
    installed_quantity: float
    initial_cost_present_value: float
    replacement_cost_present_value: float
    residual_credit_present_value: float
    fixed_om_present_value: float
    capital_net_present_value: float
    total_net_present_value: float
    annualized_capital_cost: float
    annualized_fixed_om_cost: float
    total_annual_cost: float


@dataclass(frozen=True)
class PortfolioAnnualCost:
    """Auditable annual monetary total across heterogeneous capacity bases."""

    currency: str
    price_base_year: int
    assets: tuple[AssetAnnualCost, ...]
    initial_cost_present_value: float
    replacement_cost_present_value: float
    residual_credit_present_value: float
    fixed_om_present_value: float
    capital_net_present_value: float
    total_net_present_value: float
    annualized_capital_cost: float
    annualized_fixed_om_cost: float
    total_annual_cost: float

    @property
    def by_asset_id(self) -> dict[str, AssetAnnualCost]:
        return {asset.asset_id: asset for asset in self.assets}


@dataclass(frozen=True)
class LifecycleCostPortfolio:
    """Unique component ledgers evaluated on their own installed quantities."""

    finance: ProjectFinance
    ledgers: tuple[LifecycleCostLedger, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.ledgers, tuple):
            raise ValueError("portfolio ledgers must be an immutable tuple")
        if not self.ledgers:
            raise ValueError("a lifecycle portfolio requires at least one asset")
        if any(not isinstance(ledger, LifecycleCostLedger) for ledger in self.ledgers):
            raise ValueError("portfolio entries must be LifecycleCostLedger values")
        asset_ids = tuple(ledger.spec.asset_id for ledger in self.ledgers)
        if len(set(asset_ids)) != len(asset_ids):
            raise ValueError("portfolio asset_id values must be unique")
        currencies = {ledger.spec.currency for ledger in self.ledgers}
        base_years = {ledger.spec.price_base_year for ledger in self.ledgers}
        if len(currencies) != 1 or len(base_years) != 1:
            raise ValueError(
                "portfolio assets must use one currency and one price base year"
            )
        if any(ledger.finance != self.finance for ledger in self.ledgers):
            raise ValueError("portfolio ledgers must use the common project finance")
        if any(
            ledger != annualize_lifecycle_cost(ledger.spec, self.finance)
            for ledger in self.ledgers
        ):
            raise ValueError("portfolio ledgers must be canonical lifecycle results")
        if any(
            ledger.spec.asset_class is LifecycleAssetClass.BESS_CELL
            for ledger in self.ledgers
        ):
            raise ValueError(
                "generic portfolio would double count a calibrated BESS cell asset"
            )
        generation_roles = tuple(
            ledger.spec.asset_class
            for ledger in self.ledgers
            if ledger.spec.asset_class
            in {
                LifecycleAssetClass.SALT_TO_STEAM_GENERATOR,
                LifecycleAssetClass.EXISTING_TURBINE_REUSE,
                LifecycleAssetClass.NEW_POWER_BLOCK,
            }
        )
        if generation_roles and (
            generation_roles.count(LifecycleAssetClass.SALT_TO_STEAM_GENERATOR) != 1
            or (
                generation_roles.count(LifecycleAssetClass.EXISTING_TURBINE_REUSE)
                + generation_roles.count(LifecycleAssetClass.NEW_POWER_BLOCK)
                != 1
            )
        ):
            raise ValueError(
                "TES generation cost classification requires exactly one "
                "salt-to-steam generator and exactly one of existing-turbine "
                "reuse or new power block"
            )

    @property
    def asset_ids(self) -> tuple[str, ...]:
        return tuple(ledger.spec.asset_id for ledger in self.ledgers)

    @property
    def currency(self) -> str:
        return self.ledgers[0].spec.currency

    @property
    def price_base_year(self) -> int:
        return self.ledgers[0].spec.price_base_year

    @property
    def tes_generation_cost_treatment(self) -> LifecycleAssetClass | None:
        """Return the explicit turbine investment treatment, when classified."""

        roles = {
            ledger.spec.asset_class
            for ledger in self.ledgers
            if ledger.spec.asset_class
            in {
                LifecycleAssetClass.EXISTING_TURBINE_REUSE,
                LifecycleAssetClass.NEW_POWER_BLOCK,
            }
        }
        if not roles:
            return None
        return next(iter(roles))

    def evaluate(
        self,
        installed_quantities: Mapping[str, float],
    ) -> PortfolioAnnualCost:
        """Scale each per-unit ledger once and require complete asset coverage."""

        if not isinstance(installed_quantities, Mapping):
            raise ValueError("installed_quantities must be a mapping by asset_id")
        expected = set(self.asset_ids)
        supplied = set(installed_quantities)
        if supplied != expected:
            missing = sorted(repr(value) for value in expected - supplied)
            extra = sorted(repr(value) for value in supplied - expected)
            raise ValueError(
                f"installed quantities must cover each asset exactly; "
                f"missing={missing}, extra={extra}"
            )

        asset_costs: list[AssetAnnualCost] = []
        for ledger in self.ledgers:
            quantity = installed_quantities[ledger.spec.asset_id]
            if not _is_finite_real(quantity) or quantity < 0.0:
                raise ValueError("installed quantities must be finite and non-negative")
            scaled_values = {
                "initial_cost_present_value": (
                    quantity * ledger.initial_cost_present_value
                ),
                "replacement_cost_present_value": (
                    quantity * ledger.replacement_cost_present_value
                ),
                "residual_credit_present_value": (
                    quantity * ledger.residual_credit_present_value
                ),
                "fixed_om_present_value": quantity * ledger.fixed_om_present_value,
                "capital_net_present_value": (
                    quantity * ledger.capital_net_present_value
                ),
                "total_net_present_value": quantity * ledger.total_net_present_value,
                "annualized_capital_cost": (quantity * ledger.annualized_capital_cost),
                "annualized_fixed_om_cost": (
                    quantity * ledger.annualized_fixed_om_cost
                ),
            }
            if not all(math.isfinite(value) for value in scaled_values.values()):
                raise ValueError("scaled portfolio costs must remain finite")
            annualized_capital = scaled_values["annualized_capital_cost"]
            annualized_fixed_om = scaled_values["annualized_fixed_om_cost"]
            asset_costs.append(
                AssetAnnualCost(
                    asset_id=ledger.spec.asset_id,
                    asset_class=ledger.spec.asset_class,
                    capacity_unit=ledger.spec.capacity_unit,
                    installed_quantity=quantity,
                    initial_cost_present_value=scaled_values[
                        "initial_cost_present_value"
                    ],
                    replacement_cost_present_value=scaled_values[
                        "replacement_cost_present_value"
                    ],
                    residual_credit_present_value=scaled_values[
                        "residual_credit_present_value"
                    ],
                    fixed_om_present_value=scaled_values["fixed_om_present_value"],
                    capital_net_present_value=scaled_values[
                        "capital_net_present_value"
                    ],
                    total_net_present_value=scaled_values["total_net_present_value"],
                    annualized_capital_cost=annualized_capital,
                    annualized_fixed_om_cost=annualized_fixed_om,
                    total_annual_cost=annualized_capital + annualized_fixed_om,
                )
            )
        capital_total = sum(asset.annualized_capital_cost for asset in asset_costs)
        fixed_om_total = sum(asset.annualized_fixed_om_cost for asset in asset_costs)
        portfolio_present_values = {
            "initial_cost_present_value": sum(
                asset.initial_cost_present_value for asset in asset_costs
            ),
            "replacement_cost_present_value": sum(
                asset.replacement_cost_present_value for asset in asset_costs
            ),
            "residual_credit_present_value": sum(
                asset.residual_credit_present_value for asset in asset_costs
            ),
            "fixed_om_present_value": sum(
                asset.fixed_om_present_value for asset in asset_costs
            ),
            "capital_net_present_value": sum(
                asset.capital_net_present_value for asset in asset_costs
            ),
            "total_net_present_value": sum(
                asset.total_net_present_value for asset in asset_costs
            ),
        }
        if (
            not math.isfinite(capital_total)
            or not math.isfinite(fixed_om_total)
            or not all(
                math.isfinite(value) for value in portfolio_present_values.values()
            )
        ):
            raise ValueError("portfolio annual cost totals must remain finite")
        return PortfolioAnnualCost(
            currency=self.currency,
            price_base_year=self.price_base_year,
            assets=tuple(asset_costs),
            initial_cost_present_value=portfolio_present_values[
                "initial_cost_present_value"
            ],
            replacement_cost_present_value=portfolio_present_values[
                "replacement_cost_present_value"
            ],
            residual_credit_present_value=portfolio_present_values[
                "residual_credit_present_value"
            ],
            fixed_om_present_value=portfolio_present_values["fixed_om_present_value"],
            capital_net_present_value=portfolio_present_values[
                "capital_net_present_value"
            ],
            total_net_present_value=portfolio_present_values["total_net_present_value"],
            annualized_capital_cost=capital_total,
            annualized_fixed_om_cost=fixed_om_total,
            total_annual_cost=capital_total + fixed_om_total,
        )


@dataclass(frozen=True)
class InstalledAssetQuantity:
    """One immutable installed quantity bound to a lifecycle asset identifier."""

    asset_id: str
    quantity: float

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not self.asset_id.strip():
            raise ValueError("asset_id must be a non-empty string")
        if not _is_finite_real(self.quantity) or self.quantity < 0.0:
            raise ValueError("installed quantity must be finite and non-negative")


@dataclass(frozen=True)
class FixedCapacityNonCellCost:
    """Canonical fixed-capacity binding for a non-cell lifecycle portfolio."""

    portfolio: LifecycleCostPortfolio
    quantities: tuple[InstalledAssetQuantity, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.portfolio, LifecycleCostPortfolio):
            raise ValueError("portfolio must be a LifecycleCostPortfolio")
        if not isinstance(self.quantities, tuple) or any(
            not isinstance(quantity, InstalledAssetQuantity)
            for quantity in self.quantities
        ):
            raise ValueError(
                "quantities must be an immutable tuple of asset quantities"
            )
        quantity_by_id = {quantity.asset_id: quantity for quantity in self.quantities}
        if len(quantity_by_id) != len(self.quantities) or set(quantity_by_id) != set(
            self.portfolio.asset_ids
        ):
            raise ValueError(
                "fixed-capacity quantities must uniquely and exactly cover portfolio assets"
            )
        object.__setattr__(
            self,
            "quantities",
            tuple(quantity_by_id[asset_id] for asset_id in self.portfolio.asset_ids),
        )
        self.portfolio.evaluate(self.installed_quantities)

    @property
    def installed_quantities(self) -> dict[str, float]:
        return {quantity.asset_id: quantity.quantity for quantity in self.quantities}

    @property
    def annual_cost(self) -> PortfolioAnnualCost:
        return self.portfolio.evaluate(self.installed_quantities)

    @property
    def has_positive_tes_generation_cost_quantities(self) -> bool:
        """Return whether every classified TES generation role is installed."""
        if self.portfolio.tes_generation_cost_treatment is None:
            return False
        quantities = self.installed_quantities
        classified_ids = tuple(
            ledger.spec.asset_id
            for ledger in self.portfolio.ledgers
            if ledger.spec.asset_class
            in {
                LifecycleAssetClass.SALT_TO_STEAM_GENERATOR,
                LifecycleAssetClass.EXISTING_TURBINE_REUSE,
                LifecycleAssetClass.NEW_POWER_BLOCK,
            }
        )
        return bool(classified_ids) and all(
            quantities[asset_id] > 0.0 for asset_id in classified_ids
        )


@dataclass(frozen=True)
class AnnualEconomicsSpec:
    """Auditable annual cost inputs for one fixed-capacity dispatch case."""

    horizon: AnnualHorizonSpec
    non_cell_cost: FixedCapacityNonCellCost | None = None
    bess_cell_cost: BESSCellCostCalibration | FixedLifeBESSCellCost | None = None
    bess_variable_om: BESSVariableOMSpec | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.horizon, AnnualHorizonSpec):
            raise ValueError("horizon must be an AnnualHorizonSpec")
        if self.non_cell_cost is not None and not isinstance(
            self.non_cell_cost,
            FixedCapacityNonCellCost,
        ):
            raise ValueError("non_cell_cost must be a FixedCapacityNonCellCost")
        if self.bess_cell_cost is not None and not isinstance(
            self.bess_cell_cost,
            (BESSCellCostCalibration, FixedLifeBESSCellCost),
        ):
            raise ValueError("bess_cell_cost must be a canonical BESS cell cost")
        if self.bess_variable_om is not None and not isinstance(
            self.bess_variable_om,
            BESSVariableOMSpec,
        ):
            raise ValueError("bess_variable_om must be a BESSVariableOMSpec")

        if (
            isinstance(
                self.bess_cell_cost,
                FixedLifeBESSCellCost,
            )
            and self.bess_cell_cost.reference_calibration is None
        ):
            raise ValueError(
                "fixed-life annual economics must be derived from the main BESS calibration"
            )

        if self.non_cell_cost is not None and self.bess_cell_cost is not None:
            portfolio = self.non_cell_cost.portfolio
            cell_finance = self.bess_cell_cost.project_finance
            cell_spec = self.bess_cell_cost.cell_lifecycle_spec
            if portfolio.finance != cell_finance:
                raise ValueError(
                    "BESS cell and non-cell costs must use common project finance"
                )
            if (
                portfolio.currency != cell_spec.currency
                or portfolio.price_base_year != cell_spec.price_base_year
            ):
                raise ValueError(
                    "BESS cell and non-cell costs must use one currency and price base year"
                )
            if cell_spec.asset_id in portfolio.asset_ids:
                raise ValueError(
                    "non-cell portfolio would double count the calibrated BESS cell asset"
                )

        currencies: set[str] = set()
        price_base_years: set[int] = set()
        if self.non_cell_cost is not None:
            currencies.add(self.non_cell_cost.portfolio.currency)
            price_base_years.add(self.non_cell_cost.portfolio.price_base_year)
        if self.bess_cell_cost is not None:
            currencies.add(self.bess_cell_cost.cell_lifecycle_spec.currency)
            price_base_years.add(
                self.bess_cell_cost.cell_lifecycle_spec.price_base_year
            )
        if self.bess_variable_om is not None:
            currencies.add(self.bess_variable_om.currency)
            price_base_years.add(self.bess_variable_om.price_base_year)
        if currencies and currencies != {"CNY"}:
            raise ValueError("annual E0-D economics must use CNY cost inputs")
        if price_base_years and price_base_years != {2024}:
            raise ValueError(
                "annual E0-D economics must use constant 2024 CNY cost inputs"
            )

    @property
    def non_cell_fixed_annual_cost_cny(self) -> float:
        if self.non_cell_cost is None:
            return 0.0
        return self.non_cell_cost.annual_cost.total_annual_cost

    @property
    def bess_calendar_cost_per_nominal_mwh_year(self) -> float:
        if self.bess_cell_cost is None:
            return 0.0
        return self.bess_cell_cost.calendar_cost_per_nominal_mwh_year

    @property
    def bess_cycle_cost_per_ac_discharge_mwh(self) -> float:
        if self.bess_cell_cost is None:
            return 0.0
        return self.bess_cell_cost.cycle_cost_per_ac_discharge_mwh

    @property
    def bess_variable_om_per_ac_discharge_mwh(self) -> float:
        if self.bess_variable_om is None:
            return 0.0
        return self.bess_variable_om.cost_per_ac_discharge_mwh

    @property
    def bess_reference_annual_ac_efc(self) -> float | None:
        if self.bess_cell_cost is None:
            return None
        return self.bess_cell_cost.reference_annual_ac_efc

    @property
    def calibrated_ac_deliverable_fraction(self) -> float | None:
        if self.bess_cell_cost is None:
            return None
        return self.bess_cell_cost.ac_deliverable_fraction


def build_lifecycle_cost_portfolio(
    specs: tuple[LifecycleCostSpec, ...],
    finance: ProjectFinance,
    *,
    bess_cell_cost: BESSCellCostCalibration | FixedLifeBESSCellCost | None = None,
) -> LifecycleCostPortfolio:
    """Annualize unique non-cell assets while protecting calibrated BESS cells."""

    specs = tuple(specs)
    if not specs:
        raise ValueError("a lifecycle portfolio requires at least one asset")
    asset_ids = tuple(spec.asset_id for spec in specs)
    if len(set(asset_ids)) != len(asset_ids):
        raise ValueError("portfolio asset_id values must be unique")
    if any(spec.asset_class is LifecycleAssetClass.BESS_CELL for spec in specs):
        raise ValueError(
            "generic portfolio would double count the calibrated BESS cell asset"
        )
    if bess_cell_cost is not None:
        if not isinstance(
            bess_cell_cost,
            (BESSCellCostCalibration, FixedLifeBESSCellCost),
        ):
            raise ValueError("bess_cell_cost must be a calibrated BESS cell cost")
        cell_finance = bess_cell_cost.project_finance
        cell_spec = bess_cell_cost.cell_lifecycle_spec
        if cell_finance != finance:
            raise ValueError("BESS cell and portfolio must use common project finance")
        if cell_spec.asset_id in asset_ids:
            raise ValueError(
                "generic portfolio would double count the calibrated BESS cell asset"
            )
        if any(
            spec.currency != cell_spec.currency
            or spec.price_base_year != cell_spec.price_base_year
            for spec in specs
        ):
            raise ValueError(
                "BESS cell and portfolio must use one currency and price base year"
            )
    return LifecycleCostPortfolio(
        finance=finance,
        ledgers=tuple(annualize_lifecycle_cost(spec, finance) for spec in specs),
    )
