"""Formal-candidate BESS cost basis from the approved Rahman evidence package.

This module intentionally separates source qualification from model readiness.
The linked source package is formally eligible, while fields that still require
a modeling convention remain explicitly deferred rather than silently guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from tes_bess_boundary.capacity_planning import (
    BESSAnnualCapacityCost,
    BESSPlanningEconomics,
)
from tes_bess_boundary.cost_evidence import (
    CostEvidenceAudit,
    FormalCostEvidenceCertificate,
    build_e0d10_reference_cost_audit,
)
from tes_bess_boundary.economics import (
    AnnualEconomicsSpec,
    AnnualHorizonSpec,
    BESSCellDegradationSpec,
    BESSVariableOMConversion,
    BESSVariableOMSpec,
    FixedCapacityNonCellCost,
    InstalledAssetQuantity,
    LifecycleAssetClass,
    LifecycleCostConversion,
    LifecycleCostSpec,
    PriceBasisConversion,
    ProjectFinance,
    build_lifecycle_cost_portfolio,
    calibrate_bess_cell_cost,
    convert_bess_variable_om_spec,
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


class BESSCellLifecycleJoin(str, Enum):
    """Allowed ownership of cell replacement in the formal baseline."""

    EXTERNAL_CALENDAR_AC_THROUGHPUT = "external_calendar_ac_throughput"


class BESSVariableOMBasis(str, Enum):
    """Physical throughput side used by the formal variable O&M line."""

    AC_DISCHARGE = "ac_discharge"


class PCSScalePolicy(str, Enum):
    """Disclosed PCS treatment where the source lacks a unique module curve."""

    CONSTANT_UNIT_COST_WITHIN_SOURCE_RANGE = (
        "constant_unit_cost_within_source_range"
    )


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

    @property
    def deferred_by_id(self) -> dict[str, BESSCostBoundaryLine]:
        return {line.item_id: line for line in self.deferred_lines}

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


@dataclass(frozen=True)
class RahmanBESSResolvedJoinContract:
    """Model-ready fixed-capacity joins without inventing a PCS learning curve.

    Rahman owns the 2019 USD price lines. Schmidt et al. own the direct
    non-price cell life parameters. The existing degradation kernel owns all
    replacement timing, so Rahman's cycle-only replacement is never charged a
    second time. Variable O&M and degradation cost are separate coefficients
    on the same AC-discharge throughput expression.
    """

    source_basis: Rahman2019BESSCostBasis
    cell_lifecycle_join: BESSCellLifecycleJoin = (
        BESSCellLifecycleJoin.EXTERNAL_CALENDAR_AC_THROUGHPUT
    )
    variable_om_basis: BESSVariableOMBasis = BESSVariableOMBasis.AC_DISCHARGE
    pcs_scale_policy: PCSScalePolicy = (
        PCSScalePolicy.CONSTANT_UNIT_COST_WITHIN_SOURCE_RANGE
    )
    cell_parameter_source_locator: str = "10.1016/j.joule.2018.12.008"
    variable_om_definition_locator: str = "10.1016/j.rser.2014.10.011"
    pcs_scale_definition_locator: str = "EPRI-DOE Handbook 1001834"
    cell_calendar_life_years: float = 13.0
    cell_cycle_life_efc: float = 3250.0
    pcs_source_min_mw: float = 5.0
    pcs_source_max_mw: float = 100.0

    def __post_init__(self) -> None:
        if not isinstance(self.source_basis, Rahman2019BESSCostBasis):
            raise ValueError("source_basis must be a Rahman2019BESSCostBasis")
        if (
            self.cell_lifecycle_join
            is not BESSCellLifecycleJoin.EXTERNAL_CALENDAR_AC_THROUGHPUT
            or self.variable_om_basis is not BESSVariableOMBasis.AC_DISCHARGE
            or self.pcs_scale_policy
            is not PCSScalePolicy.CONSTANT_UNIT_COST_WITHIN_SOURCE_RANGE
        ):
            raise ValueError("formal BESS joins must use the pre-registered policies")
        for field_name in (
            "cell_parameter_source_locator",
            "variable_om_definition_locator",
            "pcs_scale_definition_locator",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        for field_name in (
            "cell_calendar_life_years",
            "cell_cycle_life_efc",
            "pcs_source_min_mw",
            "pcs_source_max_mw",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{field_name} must be finite")
        if (
            self.cell_calendar_life_years <= 0.0
            or self.cell_cycle_life_efc <= 0.0
            or self.pcs_source_min_mw <= 0.0
            or self.pcs_source_max_mw < self.pcs_source_min_mw
        ):
            raise ValueError("formal BESS life and PCS range values must be positive")

    @property
    def resolved_join_ids(self) -> tuple[str, ...]:
        return self.source_basis.deferred_ids

    @property
    def formal_fixed_capacity_ready(self) -> bool:
        return self.resolved_join_ids == (
            "cell_replacement_and_calendar_life_join",
            "variable_om_throughput_side",
            "pcs_modular_scale_curve",
        )

    @property
    def exact_pcs_multiplicity_curve_supported(self) -> bool:
        """The cited sources do not identify one reproducible 95% formula."""

        return False

    def validate_pcs_power_mw(self, pcs_power_mw: float) -> None:
        if (
            isinstance(pcs_power_mw, bool)
            or not isinstance(pcs_power_mw, (int, float))
            or not math.isfinite(float(pcs_power_mw))
            or not self.pcs_source_min_mw
            <= float(pcs_power_mw)
            <= self.pcs_source_max_mw
        ):
            raise ValueError(
                "formal PCS power must remain within the 5-100 MW source range"
            )

    def source_cell_degradation_spec(
        self,
        *,
        reference_annual_ac_efc: float,
        ac_deliverable_fraction: float,
    ) -> BESSCellDegradationSpec:
        """Join Rahman cell price to Schmidt life in the sole replacement kernel."""

        battery_capex = self.source_basis.direct_by_id["battery_capex"].source_value
        return BESSCellDegradationSpec(
            cell_lifecycle=LifecycleCostSpec(
                asset_id="bess_cell",
                capacity_unit="MWh_internal",
                currency=self.source_basis.source_currency,
                price_base_year=self.source_basis.source_price_base_year,
                initial_cost_per_unit=1000.0 * battery_capex,
                service_life_years=self.cell_calendar_life_years,
                asset_class=LifecycleAssetClass.BESS_CELL,
                residual_recovery_fraction=0.0,
            ),
            cycle_life_ac_efc=self.cell_cycle_life_efc,
            reference_annual_ac_efc=reference_annual_ac_efc,
            ac_deliverable_fraction=ac_deliverable_fraction,
        )

    def convert_cell_degradation_spec(
        self,
        *,
        reference_annual_ac_efc: float,
        ac_deliverable_fraction: float,
        conversion: PriceBasisConversion,
    ) -> BESSCellDegradationSpec:
        source = self.source_cell_degradation_spec(
            reference_annual_ac_efc=reference_annual_ac_efc,
            ac_deliverable_fraction=ac_deliverable_fraction,
        )
        converted = convert_lifecycle_cost_spec(source.cell_lifecycle, conversion)
        return BESSCellDegradationSpec(
            cell_lifecycle=converted.converted_spec,
            cycle_life_ac_efc=source.cycle_life_ac_efc,
            reference_annual_ac_efc=source.reference_annual_ac_efc,
            ac_deliverable_fraction=source.ac_deliverable_fraction,
        )

    def source_variable_om_spec(self) -> BESSVariableOMSpec:
        line = self.source_basis.deferred_by_id["variable_om_throughput_side"]
        return BESSVariableOMSpec(
            currency=self.source_basis.source_currency,
            price_base_year=self.source_basis.source_price_base_year,
            cost_per_ac_discharge_mwh=line.source_value,
        )

    def convert_variable_om_spec(
        self,
        conversion: PriceBasisConversion,
    ) -> BESSVariableOMConversion:
        return convert_bess_variable_om_spec(
            self.source_variable_om_spec(),
            conversion,
        )

    def convert_non_cell_specs(
        self,
        *,
        pcs_power_mw: float,
        conversion: PriceBasisConversion,
    ) -> tuple[LifecycleCostConversion, ...]:
        self.validate_pcs_power_mw(pcs_power_mw)
        return self.source_basis.convert_non_cell_specs(conversion)

    def build_annual_economics(
        self,
        *,
        horizon: AnnualHorizonSpec,
        finance: ProjectFinance,
        conversion: PriceBasisConversion,
        pcs_power_mw: float,
        nominal_energy_mwh: float,
        reference_annual_ac_efc: float,
        ac_deliverable_fraction: float,
    ) -> AnnualEconomicsSpec:
        """Build a complete fixed-capacity BESS ledger on one price bridge."""

        self.validate_pcs_power_mw(pcs_power_mw)
        if (
            isinstance(nominal_energy_mwh, bool)
            or not isinstance(nominal_energy_mwh, (int, float))
            or not math.isfinite(float(nominal_energy_mwh))
            or nominal_energy_mwh <= 0.0
        ):
            raise ValueError("nominal_energy_mwh must be finite and positive")
        degradation = self.convert_cell_degradation_spec(
            reference_annual_ac_efc=reference_annual_ac_efc,
            ac_deliverable_fraction=ac_deliverable_fraction,
            conversion=conversion,
        )
        cell_cost = calibrate_bess_cell_cost(degradation, finance)
        non_cell_specs = tuple(
            item.converted_spec
            for item in self.convert_non_cell_specs(
                pcs_power_mw=pcs_power_mw,
                conversion=conversion,
            )
        )
        portfolio = build_lifecycle_cost_portfolio(
            non_cell_specs,
            finance,
            bess_cell_cost=cell_cost,
        )
        power_assets = {
            "bess_pcs",
            "bess_bop",
            "bess_battery_fixed_om",
            "bess_power_contingency",
        }
        quantities = tuple(
            InstalledAssetQuantity(
                asset_id,
                pcs_power_mw if asset_id in power_assets else nominal_energy_mwh,
            )
            for asset_id in portfolio.asset_ids
        )
        variable_om = self.convert_variable_om_spec(conversion).converted_spec
        return AnnualEconomicsSpec(
            horizon=horizon,
            non_cell_cost=FixedCapacityNonCellCost(
                portfolio=portfolio,
                quantities=quantities,
            ),
            bess_cell_cost=cell_cost,
            bess_variable_om=variable_om,
        )

    def build_planning_economics(
        self,
        *,
        finance: ProjectFinance,
        conversion: PriceBasisConversion,
        reference_annual_ac_efc: float,
        ac_deliverable_fraction: float,
    ) -> BESSPlanningEconomics:
        """Build endogenous common-PCS coefficients from the resolved evidence.

        Unlike ``build_annual_economics``, this method does not bind quantities.
        It annualizes every per-unit ledger once and exposes linear CNY2024
        coefficients for the capacity variables in the planning model.
        """

        degradation = self.convert_cell_degradation_spec(
            reference_annual_ac_efc=reference_annual_ac_efc,
            ac_deliverable_fraction=ac_deliverable_fraction,
            conversion=conversion,
        )
        cell_cost = calibrate_bess_cell_cost(degradation, finance)
        converted_specs = tuple(
            item.converted_spec
            for item in self.source_basis.convert_non_cell_specs(conversion)
        )
        portfolio = build_lifecycle_cost_portfolio(
            converted_specs,
            finance,
            bess_cell_cost=cell_cost,
        )
        power_eac = 0.0
        energy_eac = 0.0
        for ledger in portfolio.ledgers:
            if ledger.spec.capacity_unit == "MW_ac":
                power_eac += ledger.total_equivalent_annual_cost
            elif ledger.spec.capacity_unit == "MWh_internal":
                energy_eac += ledger.total_equivalent_annual_cost
            else:
                raise ValueError(
                    "formal BESS non-cell ledger has an unsupported planning basis"
                )
        variable_om = self.convert_variable_om_spec(conversion).converted_spec
        return BESSPlanningEconomics(
            annual_capacity_cost=BESSAnnualCapacityCost(
                energy_cny_per_mwh_year=(
                    cell_cost.calendar_cost_per_nominal_mwh_year + energy_eac
                ),
                common_pcs_power_cny_per_mw_year=power_eac,
            ),
            cycle_cost_cny_per_ac_discharge_mwh=(
                cell_cost.cycle_cost_per_ac_discharge_mwh
            ),
            variable_om_cny_per_ac_discharge_mwh=(
                variable_om.cost_per_ac_discharge_mwh
            ),
            reference_annual_ac_efc=reference_annual_ac_efc,
            ac_deliverable_fraction=ac_deliverable_fraction,
            minimum_installed_pcs_power_mw=self.pcs_source_min_mw,
            maximum_installed_pcs_power_mw=self.pcs_source_max_mw,
            source_id=RAHMAN_EVIDENCE_ID,
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


def build_resolved_rahman_bess_join_contract(
    evidence_audit: CostEvidenceAudit | None = None,
) -> RahmanBESSResolvedJoinContract:
    """Resolve the three model joins while preserving source/model ownership."""

    return RahmanBESSResolvedJoinContract(
        source_basis=build_rahman2019_bess_cost_basis(evidence_audit)
    )
