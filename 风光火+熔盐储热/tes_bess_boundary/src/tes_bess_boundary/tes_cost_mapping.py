"""Auditable capacity bases for mapping TES literature costs to E0-D physics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from tes_bess_boundary.economics import (
    FixedCapacityNonCellCost,
    InstalledAssetQuantity,
    LifecycleAssetClass,
    LifecycleCostPortfolio,
)
from tes_bess_boundary.model import TESFixedSpec


class TESCapacityBasis(Enum):
    """Unique physical denominator used by one TES literature cost item."""

    SALT_INVENTORY_KG = ("salt_inventory", "kg")
    FULL_SENSIBLE_HEAT_KWH_TH = ("full_sensible_heat", "kWh_th")
    HT_TANK_CAPACITY_T = ("ht_tank_capacity", "tonne_tank_capacity")
    MT_TANK_CAPACITY_T = ("mt_tank_capacity", "tonne_tank_capacity")
    LT_TANK_CAPACITY_T = ("lt_tank_capacity", "tonne_tank_capacity")
    ELECTRIC_HEATER_INPUT_KW_EL = ("electric_heater_input", "kW_el")
    HIGH_GRADE_STEAM_HX_INPUT_KW_TH = (
        "high_grade_steam_hx_input",
        "kW_th",
    )
    MEDIUM_GRADE_STEAM_HX_INPUT_KW_TH = (
        "medium_grade_steam_hx_input",
        "kW_th",
    )
    SALT_TO_STEAM_GENERATOR_INPUT_KW_TH = (
        "salt_to_steam_generator_input",
        "kW_th",
    )
    HEAT_DELIVERY_HX_INPUT_KW_TH = ("heat_delivery_hx_input", "kW_th")
    ELECTRIC_OUTPUT_KW_EL = ("electric_output", "kW_el")
    USEFUL_HEAT_OUTPUT_KW_TH = ("useful_heat_output", "kW_th")
    SYSTEM_COUNT = ("system_count", "system")

    @property
    def key(self) -> str:
        return self.value[0]

    @property
    def capacity_unit(self) -> str:
        return self.value[1]


class TESComponent(str, Enum):
    """Physical component roles admitted to a bottom-up TES cost ledger."""

    SALT = "salt"
    STORAGE_TANK_SYSTEM = "storage_tank_system"
    HT_TANK = "ht_tank"
    MT_TANK = "mt_tank"
    LT_TANK = "lt_tank"
    CIRCULATION = "circulation"
    TRANSFORMER = "transformer"
    ELECTRIC_HEATER = "electric_heater"
    HIGH_GRADE_STEAM_HX = "high_grade_steam_hx"
    MEDIUM_GRADE_STEAM_HX = "medium_grade_steam_hx"
    SALT_TO_STEAM_GENERATOR = "salt_to_steam_generator"
    HEAT_DELIVERY_HX = "heat_delivery_hx"
    EXISTING_TURBINE_REUSE = "existing_turbine_reuse"
    NEW_POWER_BLOCK = "new_power_block"
    FIXED_OM = "fixed_om"


_ALLOWED_BASES = {
    TESComponent.SALT: {TESCapacityBasis.SALT_INVENTORY_KG},
    TESComponent.STORAGE_TANK_SYSTEM: {
        TESCapacityBasis.FULL_SENSIBLE_HEAT_KWH_TH
    },
    TESComponent.HT_TANK: {TESCapacityBasis.HT_TANK_CAPACITY_T},
    TESComponent.MT_TANK: {TESCapacityBasis.MT_TANK_CAPACITY_T},
    TESComponent.LT_TANK: {TESCapacityBasis.LT_TANK_CAPACITY_T},
    TESComponent.CIRCULATION: {TESCapacityBasis.FULL_SENSIBLE_HEAT_KWH_TH},
    TESComponent.TRANSFORMER: {
        TESCapacityBasis.ELECTRIC_HEATER_INPUT_KW_EL
    },
    TESComponent.ELECTRIC_HEATER: {
        TESCapacityBasis.ELECTRIC_HEATER_INPUT_KW_EL
    },
    TESComponent.HIGH_GRADE_STEAM_HX: {
        TESCapacityBasis.HIGH_GRADE_STEAM_HX_INPUT_KW_TH
    },
    TESComponent.MEDIUM_GRADE_STEAM_HX: {
        TESCapacityBasis.MEDIUM_GRADE_STEAM_HX_INPUT_KW_TH
    },
    TESComponent.SALT_TO_STEAM_GENERATOR: {
        TESCapacityBasis.SALT_TO_STEAM_GENERATOR_INPUT_KW_TH
    },
    TESComponent.HEAT_DELIVERY_HX: {
        TESCapacityBasis.HEAT_DELIVERY_HX_INPUT_KW_TH
    },
    TESComponent.EXISTING_TURBINE_REUSE: {TESCapacityBasis.SYSTEM_COUNT},
    TESComponent.NEW_POWER_BLOCK: {TESCapacityBasis.ELECTRIC_OUTPUT_KW_EL},
    TESComponent.FIXED_OM: {TESCapacityBasis.SYSTEM_COUNT},
}


_ASSET_CLASSES = {
    TESComponent.SALT_TO_STEAM_GENERATOR: (
        LifecycleAssetClass.SALT_TO_STEAM_GENERATOR
    ),
    TESComponent.EXISTING_TURBINE_REUSE: (
        LifecycleAssetClass.EXISTING_TURBINE_REUSE
    ),
    TESComponent.NEW_POWER_BLOCK: LifecycleAssetClass.NEW_POWER_BLOCK,
}


_TEMPERATURE_STAGES = {
    TESComponent.SALT: ("temperature_lt", "temperature_ht"),
    TESComponent.STORAGE_TANK_SYSTEM: ("temperature_lt", "temperature_ht"),
    TESComponent.HT_TANK: ("temperature_ht", "temperature_ht"),
    TESComponent.MT_TANK: ("temperature_mt", "temperature_mt"),
    TESComponent.LT_TANK: ("temperature_lt", "temperature_lt"),
    TESComponent.CIRCULATION: ("temperature_lt", "temperature_ht"),
    TESComponent.TRANSFORMER: ("temperature_lt", "temperature_ht"),
    TESComponent.ELECTRIC_HEATER: ("temperature_lt", "temperature_ht"),
    TESComponent.HIGH_GRADE_STEAM_HX: ("temperature_lt", "temperature_ht"),
    TESComponent.MEDIUM_GRADE_STEAM_HX: ("temperature_lt", "temperature_mt"),
    TESComponent.SALT_TO_STEAM_GENERATOR: (
        "temperature_mt",
        "temperature_ht",
    ),
    TESComponent.HEAT_DELIVERY_HX: ("temperature_lt", "temperature_mt"),
    TESComponent.EXISTING_TURBINE_REUSE: None,
    TESComponent.NEW_POWER_BLOCK: ("temperature_mt", "temperature_ht"),
    TESComponent.FIXED_OM: None,
}


@dataclass(frozen=True)
class TESComponentCostBinding:
    """Declare which model quantity scales one bottom-up TES cost component."""

    asset_id: str
    component: TESComponent
    basis: TESCapacityBasis
    reference_temperature_range_c: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not self.asset_id.strip():
            raise ValueError("asset_id must be a non-empty string")
        if not isinstance(self.component, TESComponent):
            raise ValueError("component must be selected with TESComponent")
        if not isinstance(self.basis, TESCapacityBasis):
            raise ValueError("basis must be selected with TESCapacityBasis")
        if self.basis not in _ALLOWED_BASES[self.component]:
            raise ValueError("capacity basis is not valid for TES component")
        required_stage = _TEMPERATURE_STAGES[self.component]
        if required_stage is None:
            if self.reference_temperature_range_c is not None:
                raise ValueError(
                    "non-temperature TES component must not claim a temperature range"
                )
            return
        interval = self.reference_temperature_range_c
        if (
            not isinstance(interval, tuple)
            or len(interval) != 2
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in interval
            )
            or interval[0] > interval[1]
        ):
            raise ValueError(
                "temperature-dependent TES component requires a finite reference "
                "temperature range"
            )


@dataclass(frozen=True)
class TESCapacityQuantity:
    """One canonical quantity on a disclosed physical and unit basis."""

    basis: TESCapacityBasis
    quantity: float

    def __post_init__(self) -> None:
        if not isinstance(self.basis, TESCapacityBasis):
            raise ValueError("basis must be selected with TESCapacityBasis")
        if not math.isfinite(self.quantity) or self.quantity < 0.0:
            raise ValueError("TES capacity quantity must be finite and non-negative")


@dataclass(frozen=True)
class TESCapacityLedger:
    """Complete, immutable TES quantities derived from one fixed physical spec."""

    tes: TESFixedSpec
    quantities: tuple[TESCapacityQuantity, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.tes, TESFixedSpec):
            raise ValueError("tes must be a TESFixedSpec")
        if not isinstance(self.quantities, tuple) or any(
            not isinstance(item, TESCapacityQuantity) for item in self.quantities
        ):
            raise ValueError("quantities must be an immutable TES capacity tuple")
        supplied = {item.basis: item.quantity for item in self.quantities}
        if len(supplied) != len(self.quantities) or set(supplied) != set(
            TESCapacityBasis
        ):
            raise ValueError("TES capacity ledger must cover each basis exactly once")
        expected = _canonical_quantities(self.tes)
        if any(supplied[basis] != expected[basis] for basis in TESCapacityBasis):
            raise ValueError("TES capacity ledger quantities must be canonical")

    def quantity(self, basis: TESCapacityBasis) -> float:
        """Return one quantity without collapsing unlike thermal/electric bases."""

        if not isinstance(basis, TESCapacityBasis):
            raise ValueError("basis must be selected with TESCapacityBasis")
        return next(item.quantity for item in self.quantities if item.basis is basis)

    def required_temperature_interval_c(
        self,
        component: TESComponent,
    ) -> tuple[float, float] | None:
        """Return only the salt-temperature stage experienced by a component."""

        if not isinstance(component, TESComponent):
            raise ValueError("component must be selected with TESComponent")
        stage = _TEMPERATURE_STAGES[component]
        if stage is None:
            return None
        return (
            getattr(self.tes.physics, stage[0]),
            getattr(self.tes.physics, stage[1]),
        )

    def temperature_compatible(self, binding: TESComponentCostBinding) -> bool:
        """Check that literature temperatures cover the component's full stage."""

        if not isinstance(binding, TESComponentCostBinding):
            raise ValueError("binding must be a TESComponentCostBinding")
        required = self.required_temperature_interval_c(binding.component)
        if required is None:
            return True
        reference = binding.reference_temperature_range_c
        if reference is None:
            return False
        return reference[0] <= required[0] and reference[1] >= required[1]


def _canonical_quantities(tes: TESFixedSpec) -> dict[TESCapacityBasis, float]:
    physics = tes.physics
    caps = tes.port_caps
    return {
        TESCapacityBasis.SALT_INVENTORY_KG: physics.salt_mass_t * 1_000.0,
        TESCapacityBasis.FULL_SENSIBLE_HEAT_KWH_TH: (
            physics.salt_mass_t
            * physics.specific_heat_mwh_per_tonne_k
            * (physics.temperature_ht - physics.temperature_lt)
            * 1_000.0
        ),
        TESCapacityBasis.HT_TANK_CAPACITY_T: physics.ht_tank_capacity_t,
        TESCapacityBasis.MT_TANK_CAPACITY_T: physics.mt_tank_capacity_t,
        TESCapacityBasis.LT_TANK_CAPACITY_T: physics.lt_tank_capacity_t,
        TESCapacityBasis.ELECTRIC_HEATER_INPUT_KW_EL: (
            caps.electric_charge_input_mw * 1_000.0
        ),
        TESCapacityBasis.HIGH_GRADE_STEAM_HX_INPUT_KW_TH: (
            caps.steam_to_ht_reference_input_mw * 1_000.0
        ),
        TESCapacityBasis.MEDIUM_GRADE_STEAM_HX_INPUT_KW_TH: (
            caps.steam_to_mt_reference_input_mw * 1_000.0
        ),
        TESCapacityBasis.SALT_TO_STEAM_GENERATOR_INPUT_KW_TH: (
            caps.electric_output_mw / physics.power_block_efficiency * 1_000.0
        ),
        TESCapacityBasis.HEAT_DELIVERY_HX_INPUT_KW_TH: (
            caps.heat_output_mw / physics.heat_exchanger_efficiency * 1_000.0
        ),
        TESCapacityBasis.ELECTRIC_OUTPUT_KW_EL: caps.electric_output_mw * 1_000.0,
        TESCapacityBasis.USEFUL_HEAT_OUTPUT_KW_TH: caps.heat_output_mw * 1_000.0,
        TESCapacityBasis.SYSTEM_COUNT: 1.0,
    }


def derive_tes_capacity_ledger(tes: TESFixedSpec) -> TESCapacityLedger:
    """Derive every allowed TES literature-cost denominator exactly once."""

    if not isinstance(tes, TESFixedSpec):
        raise ValueError("tes must be a TESFixedSpec")
    physics = tes.physics
    if any(
        capacity < physics.salt_mass_t
        for capacity in (
            physics.ht_tank_capacity_t,
            physics.mt_tank_capacity_t,
            physics.lt_tank_capacity_t,
        )
    ):
        raise ValueError(
            "each HT/MT/LT state tank must hold the full salt inventory before "
            "a full sensible-heat cost basis can be certified"
        )
    quantities = _canonical_quantities(tes)
    return TESCapacityLedger(
        tes=tes,
        quantities=tuple(
            TESCapacityQuantity(basis, quantities[basis])
            for basis in TESCapacityBasis
        ),
    )


def bind_tes_cost_portfolio(
    tes: TESFixedSpec,
    portfolio: LifecycleCostPortfolio,
    bindings: tuple[TESComponentCostBinding, ...],
) -> FixedCapacityNonCellCost:
    """Bind a bottom-up TES portfolio to canonical model quantities and units."""

    if not isinstance(tes, TESFixedSpec):
        raise ValueError("tes must be a TESFixedSpec")
    if not isinstance(portfolio, LifecycleCostPortfolio):
        raise ValueError("portfolio must be a LifecycleCostPortfolio")
    if not isinstance(bindings, tuple) or any(
        not isinstance(binding, TESComponentCostBinding) for binding in bindings
    ):
        raise ValueError("bindings must be an immutable TES component tuple")
    by_asset_id = {binding.asset_id: binding for binding in bindings}
    if len(by_asset_id) != len(bindings) or set(by_asset_id) != set(
        portfolio.asset_ids
    ):
        raise ValueError(
            "TES bindings must uniquely and exactly cover portfolio assets"
        )

    ledger = derive_tes_capacity_ledger(tes)
    quantities: list[InstalledAssetQuantity] = []
    for lifecycle_ledger in portfolio.ledgers:
        spec = lifecycle_ledger.spec
        binding = by_asset_id[spec.asset_id]
        if spec.capacity_unit != binding.basis.capacity_unit:
            raise ValueError(
                "lifecycle capacity unit does not match the TES capacity basis"
            )
        if not ledger.temperature_compatible(binding):
            raise ValueError(
                "literature temperature range does not cover the TES component stage"
            )
        expected_class = _ASSET_CLASSES.get(
            binding.component,
            LifecycleAssetClass.TES_COMPONENT,
        )
        if spec.asset_class is not expected_class:
            raise ValueError("lifecycle asset class does not match TES component role")
        quantities.append(
            InstalledAssetQuantity(
                asset_id=spec.asset_id,
                quantity=ledger.quantity(binding.basis),
            )
        )
    return FixedCapacityNonCellCost(portfolio, tuple(quantities))
