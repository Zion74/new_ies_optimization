"""Formal-candidate BESS cost basis from the approved Rahman evidence package.

This module intentionally separates source qualification from model readiness.
The linked source package is formally eligible, while fields that still require
a modeling convention remain explicitly deferred rather than silently guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from tes_bess_boundary.cost_evidence import (
    CostEvidenceAudit,
    FormalCostEvidenceCertificate,
    build_e0d10_reference_cost_audit,
)
from tes_bess_boundary.economics import (
    LifecycleAssetClass,
    LifecycleCostConversion,
    LifecycleCostSpec,
    PriceBasisConversion,
    convert_lifecycle_cost_spec,
)


RAHMAN_EVIDENCE_ID = "rahman2021_bess_component_package"
RAHMAN_COMPONENT_DENOMINATOR = (
    "component_specific_kWh_kW_kW_year_MWh_m2"
)


class BESSCostMappingStatus(str, Enum):
    """Whether one reported cost line can enter the current model boundary."""

    DIRECT = "direct"
    DERIVED_DIRECT = "derived_direct"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class BESSCostBoundaryLine:
    """One source value and its explicit mapping decision."""

    item_id: str
    source_value: float
    source_unit: str
    model_basis: str
    status: BESSCostMappingStatus
    note: str

    def __post_init__(self) -> None:
        for field_name in ("item_id", "source_unit", "model_basis", "note"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if (
            isinstance(self.source_value, bool)
            or not isinstance(self.source_value, (int, float))
            or not math.isfinite(float(self.source_value))
            or self.source_value < 0.0
        ):
            raise ValueError("source_value must be finite and non-negative")
        if not isinstance(self.status, BESSCostMappingStatus):
            raise ValueError("status must be selected with BESSCostMappingStatus")


@dataclass(frozen=True)
class Rahman2019BESSCostBasis:
    """Audited source constants and the model boundary they are allowed to fill."""

    evidence_certificate: FormalCostEvidenceCertificate
    direct_lines: tuple[BESSCostBoundaryLine, ...]
    deferred_lines: tuple[BESSCostBoundaryLine, ...]
    source_currency: str = "USD"
    source_price_base_year: int = 2019
    source_project_life_years: int = 20
    source_nominal_discount_rate: float = 0.10
    source_average_inflation_rate: float = 0.0172
    reference_round_trip_efficiency: float = 0.90
    reference_depth_of_discharge: float = 0.80
    reference_cycle_life: float = 4389.60215351849
    contingency_fraction: float = 0.10

    def __post_init__(self) -> None:
        if not isinstance(
            self.evidence_certificate,
            FormalCostEvidenceCertificate,
        ):
            raise ValueError("evidence_certificate must be canonical")
        evidence = self.evidence_certificate.evidence
        if (
            evidence.evidence_id != RAHMAN_EVIDENCE_ID
            or self.evidence_certificate.certified_capacity_denominator
            != RAHMAN_COMPONENT_DENOMINATOR
            or evidence.linked_author_expansion is None
            or evidence.linked_author_expansion.source_locator
            != "10.7939/r3-jgnr-b764"
        ):
            raise ValueError("Rahman evidence package must retain its exact crosswalk")
        if not isinstance(self.direct_lines, tuple) or not self.direct_lines:
            raise ValueError("direct_lines must be a non-empty immutable tuple")
        if not isinstance(self.deferred_lines, tuple) or not self.deferred_lines:
            raise ValueError("deferred_lines must be a non-empty immutable tuple")
        all_lines = self.direct_lines + self.deferred_lines
        if any(not isinstance(line, BESSCostBoundaryLine) for line in all_lines):
            raise ValueError("cost boundary lines must be canonical")
        if len({line.item_id for line in all_lines}) != len(all_lines):
            raise ValueError("cost boundary item_id values must be unique")
        if any(
            line.status is BESSCostMappingStatus.DEFERRED
            for line in self.direct_lines
        ) or any(
            line.status is not BESSCostMappingStatus.DEFERRED
            for line in self.deferred_lines
        ):
            raise ValueError("direct and deferred boundary lines must not be mixed")

    @property
    def source_real_discount_rate(self) -> float:
        return (
            (1.0 + self.source_nominal_discount_rate)
            / (1.0 + self.source_average_inflation_rate)
            - 1.0
        )

    @property
    def formal_source_qualified(self) -> bool:
        return True

    @property
    def formal_portfolio_ready(self) -> bool:
        """The source is qualified, but unresolved model joins still block TAC."""

        return not self.deferred_lines

    @property
    def direct_by_id(self) -> dict[str, BESSCostBoundaryLine]:
        return {line.item_id: line for line in self.direct_lines}

    @property
    def deferred_ids(self) -> tuple[str, ...]:
        return tuple(line.item_id for line in self.deferred_lines)

    def source_non_cell_specs(self) -> tuple[LifecycleCostSpec, ...]:
        """Build the directly mappable non-cell 2019 USD lifecycle inputs.

        The cell CAPEX is deliberately excluded because the source's cycle-only
        replacement logic must first be reconciled with the model's independent
        calendar/throughput degradation contract.
        """

        direct = self.direct_by_id
        common = {
            "currency": self.source_currency,
            "price_base_year": self.source_price_base_year,
            "service_life_years": float(self.source_project_life_years),
            "asset_class": LifecycleAssetClass.BESS_NON_CELL,
            "residual_recovery_fraction": 0.0,
        }
        return (
            LifecycleCostSpec(
                asset_id="bess_pcs",
                capacity_unit="MW_ac",
                initial_cost_per_unit=(
                    1000.0 * direct["pcs_capex_s1_s3"].source_value
                ),
                fixed_om_per_unit_year=(
                    1000.0 * direct["pcs_fixed_om"].source_value
                ),
                **common,
            ),
            LifecycleCostSpec(
                asset_id="bess_bop",
                capacity_unit="MW_ac",
                initial_cost_per_unit=(
                    1000.0 * direct["bop_capex"].source_value
                ),
                **common,
            ),
            LifecycleCostSpec(
                asset_id="bess_enclosure_foundation",
                capacity_unit="MWh_internal",
                initial_cost_per_unit=(
                    1000.0 * direct["enclosure_foundation"].source_value
                ),
                **common,
            ),
            LifecycleCostSpec(
                asset_id="bess_battery_fixed_om",
                capacity_unit="MW_ac",
                initial_cost_per_unit=0.0,
                fixed_om_per_unit_year=(
                    1000.0 * direct["battery_fixed_om"].source_value
                ),
                **common,
            ),
            LifecycleCostSpec(
                asset_id="bess_power_contingency",
                capacity_unit="MW_ac",
                initial_cost_per_unit=(
                    1000.0
                    * self.contingency_fraction
                    * (
                        direct["pcs_capex_s1_s3"].source_value
                        + direct["bop_capex"].source_value
                    )
                ),
                replacement_cost_per_unit=0.0,
                **common,
            ),
            LifecycleCostSpec(
                asset_id="bess_energy_contingency",
                capacity_unit="MWh_internal",
                initial_cost_per_unit=(
                    1000.0
                    * self.contingency_fraction
                    * (
                        direct["battery_capex"].source_value
                        + direct["enclosure_foundation"].source_value
                    )
                ),
                replacement_cost_per_unit=0.0,
                **common,
            ),
        )

    def convert_non_cell_specs(
        self,
        conversion: PriceBasisConversion,
    ) -> tuple[LifecycleCostConversion, ...]:
        """Convert every directly mapped non-cell field through one price bridge."""

        return tuple(
            convert_lifecycle_cost_spec(spec, conversion)
            for spec in self.source_non_cell_specs()
        )


def _reference_cycle_life(depth_of_discharge: float) -> float:
    return (
        2731.7
        * depth_of_discharge**-0.679
        * math.exp(1.614 * (1.0 - depth_of_discharge))
    )


def build_rahman2019_bess_cost_basis(
    evidence_audit: CostEvidenceAudit | None = None,
) -> Rahman2019BESSCostBasis:
    """Build the approved linked evidence package without filling deferred joins."""

    audit = (
        build_e0d10_reference_cost_audit()
        if evidence_audit is None
        else evidence_audit
    )
    if not isinstance(audit, CostEvidenceAudit):
        raise ValueError("evidence_audit must be a CostEvidenceAudit")
    certificate = audit.get(RAHMAN_EVIDENCE_ID).certify_formal_baseline(
        expected_capacity_denominator=RAHMAN_COMPONENT_DENOMINATOR
    )
    footprint_m2_per_kwh = 0.017
    enclosure_foundation_usd_per_m2 = 282.96
    reference_dod = 0.80
    return Rahman2019BESSCostBasis(
        evidence_certificate=certificate,
        reference_cycle_life=_reference_cycle_life(reference_dod),
        direct_lines=(
            BESSCostBoundaryLine(
                item_id="battery_capex",
                source_value=216.27,
                source_unit="USD_2019/kWh_installed_internal",
                model_basis="MWh_internal",
                status=BESSCostMappingStatus.DIRECT,
                note=(
                    "Table 3.5 battery cost; installed capacity is upstream of "
                    "the source's efficiency and DOD sizing equation."
                ),
            ),
            BESSCostBoundaryLine(
                item_id="battery_fixed_om",
                source_value=10.35,
                source_unit="USD_2019/kW-year",
                model_basis="MW_ac-year",
                status=BESSCostMappingStatus.DIRECT,
                note="Kept separate from cell CAPEX and PCS fixed O&M.",
            ),
            BESSCostBoundaryLine(
                item_id="bop_capex",
                source_value=106.75,
                source_unit="USD_2019/kW",
                model_basis="MW_ac",
                status=BESSCostMappingStatus.DIRECT,
                note=(
                    "BOP includes supporting HVAC, grid connection, monitoring, "
                    "control and installation items outside PCS/storage section."
                ),
            ),
            BESSCostBoundaryLine(
                item_id="pcs_capex_s1_s3",
                source_value=206.81,
                source_unit="USD_2019/kW",
                model_basis="MW_ac",
                status=BESSCostMappingStatus.DIRECT,
                note=(
                    "Table 3.6 value for S1-S3; the 5 MW modular scaling "
                    "convention is retained as a sensitivity requirement."
                ),
            ),
            BESSCostBoundaryLine(
                item_id="pcs_fixed_om",
                source_value=2.63,
                source_unit="USD_2019/kW-year",
                model_basis="MW_ac-year",
                status=BESSCostMappingStatus.DIRECT,
                note="Table 3.6 PCS fixed O&M, separate from battery fixed O&M.",
            ),
            BESSCostBoundaryLine(
                item_id="enclosure_foundation",
                source_value=(
                    footprint_m2_per_kwh * enclosure_foundation_usd_per_m2
                ),
                source_unit="USD_2019/kWh_installed_internal",
                model_basis="MWh_internal",
                status=BESSCostMappingStatus.DERIVED_DIRECT,
                note=(
                    "Li-ion footprint 0.017 m2/kWh from Table 3.2 multiplied by "
                    "282.96 USD/m2 from the Chapter 3 cost boundary."
                ),
            ),
        ),
        deferred_lines=(
            BESSCostBoundaryLine(
                item_id="cell_replacement_and_calendar_life_join",
                source_value=1.0,
                source_unit="replacement_fraction_of_battery_capex",
                model_basis="calendar_plus_AC_throughput_degradation",
                status=BESSCostMappingStatus.DEFERRED,
                note=(
                    "Rahman uses DOD-dependent cycle replacement only; importing "
                    "it directly into the existing calendar-plus-throughput kernel "
                    "would double count degradation."
                ),
            ),
            BESSCostBoundaryLine(
                item_id="variable_om_throughput_side",
                source_value=2.74,
                source_unit="USD_2019/MWh_reported",
                model_basis="AC_discharge_MWh_or_charge_MWh",
                status=BESSCostMappingStatus.DEFERRED,
                note=(
                    "Table 3.5 does not identify the exact charging/discharging "
                    "throughput side required by the model."
                ),
            ),
            BESSCostBoundaryLine(
                item_id="pcs_modular_scale_curve",
                source_value=5.0,
                source_unit="MW_per_PCS_module",
                model_basis="endogenous_MW_ac",
                status=BESSCostMappingStatus.DEFERRED,
                note=(
                    "The source applies a 5 MW module and 95% multiplicity learning; "
                    "a constant unit cost needs a disclosed approximation or PWL map."
                ),
            ),
        ),
    )
