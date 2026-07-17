"""Pinch and deliverable-heat audit for the TES medium-to-low path."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from tes_bess_boundary.model import TESFixedSpec


class HeatNetworkTemperatureBasis(str, Enum):
    """Provenance level of supply/return temperatures."""

    SITE_PRIMARY = "site_primary"
    CORE_REFERENCE_SCENARIO = "core_reference_scenario"
    AUTHOR_SENSITIVITY = "author_sensitivity"


@dataclass(frozen=True)
class HeatNetworkPinchSpec:
    """Counter-current heat-network boundary with explicit approach assumptions."""

    supply_temperature_c: float
    return_temperature_c: float
    hot_end_minimum_approach_k: float
    cold_end_minimum_approach_k: float
    temperature_basis: HeatNetworkTemperatureBasis
    source_id: str

    def __post_init__(self) -> None:
        values = (
            self.supply_temperature_c,
            self.return_temperature_c,
            self.hot_end_minimum_approach_k,
            self.cold_end_minimum_approach_k,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in values
        ):
            raise ValueError("heat-network temperatures and approaches must be finite")
        if self.supply_temperature_c <= self.return_temperature_c:
            raise ValueError("heat-network supply temperature must exceed return")
        if min(
            self.hot_end_minimum_approach_k,
            self.cold_end_minimum_approach_k,
        ) < 0.0:
            raise ValueError("minimum heat-exchanger approaches must be non-negative")
        if not isinstance(self.temperature_basis, HeatNetworkTemperatureBasis):
            raise ValueError(
                "temperature_basis must use HeatNetworkTemperatureBasis"
            )
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must disclose the temperature provenance")
        if (
            self.temperature_basis
            is HeatNetworkTemperatureBasis.CORE_REFERENCE_SCENARIO
            and not self.source_id.strip().lower().startswith("10.")
        ):
            raise ValueError("core reference scenario requires a DOI source_id")


@dataclass(frozen=True)
class MoltenSaltMaterialEnvelope:
    """Liquid and upper-temperature material limits for one disclosed salt."""

    material_name: str
    melting_point_c: float
    minimum_liquid_margin_k: float
    maximum_operating_temperature_c: float
    source_doi: str

    def __post_init__(self) -> None:
        if not isinstance(self.material_name, str) or not self.material_name.strip():
            raise ValueError("material_name must be non-empty")
        values = (
            self.melting_point_c,
            self.minimum_liquid_margin_k,
            self.maximum_operating_temperature_c,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in values
        ):
            raise ValueError("material temperature limits must be finite")
        if self.minimum_liquid_margin_k < 0.0:
            raise ValueError("minimum_liquid_margin_k must be non-negative")
        if self.maximum_operating_temperature_c <= self.melting_point_c:
            raise ValueError("maximum operating temperature must exceed melting point")
        if not isinstance(self.source_doi, str) or not self.source_doi.lower().startswith(
            "10."
        ):
            raise ValueError("material envelope requires a DOI")


@dataclass(frozen=True)
class TESHeatDeliveryPinchAudit:
    """Auditable endpoint-pinch and capacity checks for MT-to-LT heat delivery."""

    tes: TESFixedSpec
    heat_network: HeatNetworkPinchSpec
    material: MoltenSaltMaterialEnvelope
    dispatch_interval_hours: float

    def __post_init__(self) -> None:
        if not isinstance(self.tes, TESFixedSpec):
            raise ValueError("tes must be a TESFixedSpec")
        if not isinstance(self.heat_network, HeatNetworkPinchSpec):
            raise ValueError("heat_network must be a HeatNetworkPinchSpec")
        if not isinstance(self.material, MoltenSaltMaterialEnvelope):
            raise ValueError("material must be a MoltenSaltMaterialEnvelope")
        if (
            isinstance(self.dispatch_interval_hours, bool)
            or not isinstance(self.dispatch_interval_hours, (int, float))
            or not math.isfinite(self.dispatch_interval_hours)
            or self.dispatch_interval_hours <= 0.0
        ):
            raise ValueError("dispatch_interval_hours must be finite and positive")

    @property
    def hot_end_approach_k(self) -> float:
        return (
            self.tes.physics.temperature_mt
            - self.heat_network.supply_temperature_c
        )

    @property
    def cold_end_approach_k(self) -> float:
        return (
            self.tes.physics.temperature_lt
            - self.heat_network.return_temperature_c
        )

    @property
    def liquid_margin_k(self) -> float:
        return self.tes.physics.temperature_lt - self.material.melting_point_c

    @property
    def pinch_mt_lower_bound_c(self) -> float:
        return (
            self.heat_network.supply_temperature_c
            + self.heat_network.hot_end_minimum_approach_k
        )

    @property
    def hot_end_pinch_binds_above_lt(self) -> bool:
        """Whether the network imposes an MT floor above the existing LT state."""

        return self.pinch_mt_lower_bound_c > self.tes.physics.temperature_lt

    @property
    def maximum_supply_temperature_c(self) -> float:
        return (
            self.tes.physics.temperature_mt
            - self.heat_network.hot_end_minimum_approach_k
        )

    @property
    def maximum_return_temperature_c(self) -> float:
        return (
            self.tes.physics.temperature_lt
            - self.heat_network.cold_end_minimum_approach_k
        )

    @property
    def useful_heat_per_tonne_mwh(self) -> float:
        physics = self.tes.physics
        return (
            physics.heat_exchanger_efficiency
            * physics.specific_heat_mwh_per_tonne_k
            * physics.delta_mt_lt
        )

    @property
    def inventory_limited_useful_heat_mw(self) -> float:
        return (
            self.useful_heat_per_tonne_mwh
            * self.tes.physics.salt_mass_t
            / self.dispatch_interval_hours
        )

    @property
    def effective_heat_output_cap_mw(self) -> float:
        return min(
            self.tes.port_caps.heat_output_mw,
            self.inventory_limited_useful_heat_mw,
        )

    @property
    def port_cap_is_inventory_redundant(self) -> bool:
        return (
            self.tes.port_caps.heat_output_mw
            > self.inventory_limited_useful_heat_mw
        )

    def required_salt_flow_tph(self, useful_heat_mw: float) -> float:
        if (
            isinstance(useful_heat_mw, bool)
            or not isinstance(useful_heat_mw, (int, float))
            or not math.isfinite(useful_heat_mw)
            or useful_heat_mw < 0.0
        ):
            raise ValueError("useful_heat_mw must be finite and non-negative")
        return useful_heat_mw / self.useful_heat_per_tonne_mwh

    def required_water_flow_tph(
        self,
        useful_heat_mw: float,
        *,
        water_specific_heat_mwh_per_tonne_k: float,
    ) -> float:
        if (
            isinstance(water_specific_heat_mwh_per_tonne_k, bool)
            or not isinstance(water_specific_heat_mwh_per_tonne_k, (int, float))
            or not math.isfinite(water_specific_heat_mwh_per_tonne_k)
            or water_specific_heat_mwh_per_tonne_k <= 0.0
        ):
            raise ValueError("water specific heat must be finite and positive")
        if (
            isinstance(useful_heat_mw, bool)
            or not isinstance(useful_heat_mw, (int, float))
            or not math.isfinite(useful_heat_mw)
            or useful_heat_mw < 0.0
        ):
            raise ValueError("useful_heat_mw must be finite and non-negative")
        water_delta_k = (
            self.heat_network.supply_temperature_c
            - self.heat_network.return_temperature_c
        )
        return useful_heat_mw / (
            water_specific_heat_mwh_per_tonne_k * water_delta_k
        )

    @property
    def violations(self) -> tuple[str, ...]:
        physics = self.tes.physics
        failures: list[str] = []
        if self.hot_end_approach_k < (
            self.heat_network.hot_end_minimum_approach_k
        ):
            failures.append("hot-end pinch is violated")
        if self.cold_end_approach_k < (
            self.heat_network.cold_end_minimum_approach_k
        ):
            failures.append("cold-end pinch is violated")
        if self.liquid_margin_k < self.material.minimum_liquid_margin_k:
            failures.append("LT salt liquid margin is violated")
        if physics.temperature_mt > self.material.maximum_operating_temperature_c:
            failures.append("MT exceeds the material operating limit")
        return tuple(failures)

    def certify_heat_delivery(self) -> None:
        if self.tes.port_caps.heat_output_mw <= 0.0:
            raise ValueError("heat-delivery certification requires an active heat port")
        if self.violations:
            raise ValueError("; ".join(self.violations))


def build_li2026_reference_heat_network(
    *,
    hot_end_minimum_approach_k: float,
    cold_end_minimum_approach_k: float,
) -> HeatNetworkPinchSpec:
    """Build the Energy 2026 350-MW CHP reference, never a Yangling site claim."""

    return HeatNetworkPinchSpec(
        supply_temperature_c=120.0,
        return_temperature_c=70.0,
        hot_end_minimum_approach_k=hot_end_minimum_approach_k,
        cold_end_minimum_approach_k=cold_end_minimum_approach_k,
        temperature_basis=HeatNetworkTemperatureBasis.CORE_REFERENCE_SCENARIO,
        source_id="10.1016/j.energy.2026.141711",
    )


def build_hitec_candidate_envelope(
    *,
    minimum_liquid_margin_k: float,
) -> MoltenSaltMaterialEnvelope:
    """Build the Applied Energy HITEC candidate with an explicit author margin."""

    return MoltenSaltMaterialEnvelope(
        material_name="HITEC 53% KNO3 / 40% NaNO2 / 7% NaNO3",
        melting_point_c=142.0,
        minimum_liquid_margin_k=minimum_liquid_margin_k,
        maximum_operating_temperature_c=540.0,
        source_doi="10.1016/j.apenergy.2025.126876",
    )
