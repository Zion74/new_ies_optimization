"""Public, sensitivity-only TES cost portfolios for mechanism experiments.

These portfolios deliberately do not certify project-specific Yangling costs.
They provide two mutually exclusive accounting routes so that public evidence
can support controlled boundary experiments without double counting aggregate
storage packages and their constituent salt, tanks, and circulation systems.
"""

from __future__ import annotations

import math
import os
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from tes_bess_boundary.economics import (
    LifecycleAssetClass,
    LifecycleCostSpec,
    ProjectFinance,
    annualize_lifecycle_cost,
)
from tes_bess_boundary.formal_tes_costs import TESFormalCostAccount
from tes_bess_boundary.price_basis import (
    OfficialPriceBasisSnapshot,
    load_price_basis_snapshot,
)
from tes_bess_boundary.tes_cost_mapping import TESCapacityBasis, TESComponent


ENERGY_CURRENT_IMPACT_FACTOR = 9.4


class PublicTESCostMode(str, Enum):
    """Mutually exclusive public-cost accounting routes."""

    AGGREGATE_STORAGE = "aggregate_storage"
    COMPONENT_LEDGER = "component_ledger"


class PublicTESCostScenario(str, Enum):
    """Ordered public-parameter sensitivity levels."""

    LOW = "low"
    BASE = "base"
    HIGH = "high"


class PublicEvidenceQuality(str, Enum):
    """Evidence tier; only the first tier is a journal cost source."""

    ENERGY_PLUS_JOURNAL = "energy_plus_journal"
    OFFICIAL_ENGINEERING = "official_engineering"
    MODEL_BOUNDARY = "model_boundary"


class PublicEvidenceMapping(str, Enum):
    """How directly a source quantity maps to the E0 TES topology."""

    DIRECT = "direct"
    AGGREGATE_ANCHOR = "aggregate_anchor"
    SIMILAR_COMPONENT_PROXY = "similar_component_proxy"
    AUTHOR_INTERPOLATION = "author_interpolation"
    MODEL_BOUNDARY = "model_boundary"


class PriceYearStatus(str, Enum):
    """Whether the price base year is stated by the source or assumed here."""

    EXPLICIT = "explicit"
    AUTHOR_ASSUMED = "author_assumed"


@dataclass(frozen=True)
class PublicTESCostItem:
    """One public unit cost and its complete evidence/mapping disclosure."""

    asset_id: str
    component: TESComponent
    basis: TESCapacityBasis
    source_value_per_unit: float
    source_currency: str
    source_price_year: int
    price_year_status: PriceYearStatus
    evidence_id: str
    source_locator: str
    venue: str
    evidence_quality: PublicEvidenceQuality
    current_impact_factor: float | None
    evidence_mapping: PublicEvidenceMapping
    covered_accounts: frozenset[TESFormalCostAccount]
    boundary_note: str
    apply_project_addition_multiplier: bool = True

    def __post_init__(self) -> None:
        for field_name in (
            "asset_id",
            "evidence_id",
            "source_locator",
            "venue",
            "boundary_note",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.component, TESComponent):
            raise ValueError("component must be selected with TESComponent")
        if not isinstance(self.basis, TESCapacityBasis):
            raise ValueError("basis must be selected with TESCapacityBasis")
        if (
            not isinstance(self.source_value_per_unit, (int, float))
            or isinstance(self.source_value_per_unit, bool)
            or not math.isfinite(float(self.source_value_per_unit))
            or self.source_value_per_unit < 0.0
        ):
            raise ValueError("source_value_per_unit must be finite and non-negative")
        if (
            len(self.source_currency) != 3
            or not self.source_currency.isalpha()
            or self.source_currency != self.source_currency.upper()
        ):
            raise ValueError("source_currency must be an uppercase ISO 4217 code")
        if (
            isinstance(self.source_price_year, bool)
            or not isinstance(self.source_price_year, int)
            or self.source_price_year <= 0
        ):
            raise ValueError("source_price_year must be a positive integer")
        if not isinstance(self.price_year_status, PriceYearStatus):
            raise ValueError("price_year_status must be selected with its enum")
        if not isinstance(self.evidence_quality, PublicEvidenceQuality):
            raise ValueError("evidence_quality must be selected with its enum")
        if not isinstance(self.evidence_mapping, PublicEvidenceMapping):
            raise ValueError("evidence_mapping must be selected with its enum")
        if not isinstance(self.covered_accounts, frozenset) or not self.covered_accounts:
            raise ValueError("covered_accounts must be a non-empty frozenset")
        if any(
            not isinstance(account, TESFormalCostAccount)
            for account in self.covered_accounts
        ):
            raise ValueError("covered_accounts must contain TES formal accounts")
        if self.evidence_quality is PublicEvidenceQuality.ENERGY_PLUS_JOURNAL:
            if (
                self.current_impact_factor is None
                or not math.isfinite(self.current_impact_factor)
                or self.current_impact_factor < ENERGY_CURRENT_IMPACT_FACTOR
            ):
                raise ValueError("journal evidence must meet the current Energy IF floor")
        elif self.current_impact_factor is not None:
            raise ValueError("non-journal evidence must not carry a journal IF")
        if (
            self.evidence_quality is PublicEvidenceQuality.MODEL_BOUNDARY
            and self.evidence_mapping is not PublicEvidenceMapping.MODEL_BOUNDARY
        ):
            raise ValueError("model-boundary evidence requires model-boundary mapping")
        if (
            self.source_value_per_unit == 0.0
            and self.evidence_quality is not PublicEvidenceQuality.MODEL_BOUNDARY
        ):
            raise ValueError("zero public unit cost is allowed only as a model boundary")
        if not isinstance(self.apply_project_addition_multiplier, bool):
            raise ValueError("apply_project_addition_multiplier must be boolean")


@dataclass(frozen=True)
class PublicTESLifecyclePolicy:
    """Disclosed scenario-wide project additions and lifecycle assumptions."""

    project_years: int
    service_life_years: float
    real_discount_rate: float
    project_addition_multiplier: float
    fixed_om_fraction_per_year: float
    decommission_fraction: float
    evidence_ids: tuple[str, ...]
    covered_accounts: frozenset[TESFormalCostAccount] = frozenset(
        {
            TESFormalCostAccount.PROJECT_ADDITIONS,
            TESFormalCostAccount.LIFECYCLE_TERMS,
        }
    )

    def __post_init__(self) -> None:
        if (
            isinstance(self.project_years, bool)
            or not isinstance(self.project_years, int)
            or self.project_years <= 0
        ):
            raise ValueError("project_years must be a positive integer")
        positive = (
            self.service_life_years,
            self.project_addition_multiplier,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("lifecycle positive parameters must be finite")
        if not 0.0 <= self.real_discount_rate < 1.0:
            raise ValueError("real_discount_rate must lie in [0, 1)")
        if not 0.0 <= self.fixed_om_fraction_per_year < 1.0:
            raise ValueError("fixed_om_fraction_per_year must lie in [0, 1)")
        if not 0.0 <= self.decommission_fraction < 1.0:
            raise ValueError("decommission_fraction must lie in [0, 1)")
        if self.project_addition_multiplier < 1.0:
            raise ValueError("project_addition_multiplier must be at least one")
        if not self.evidence_ids or any(
            not isinstance(value, str) or not value.strip()
            for value in self.evidence_ids
        ):
            raise ValueError("evidence_ids must be a non-empty string tuple")
        if self.covered_accounts != frozenset(
            {
                TESFormalCostAccount.PROJECT_ADDITIONS,
                TESFormalCostAccount.LIFECYCLE_TERMS,
            }
        ):
            raise ValueError("lifecycle policy must cover its two canonical accounts")


@dataclass(frozen=True)
class PublicTESAnnualizedCostCoefficient:
    """Converted CNY2024 annual cost for one unit of a model quantity."""

    item: PublicTESCostItem
    direct_cost_cny2024_per_unit: float
    installed_cost_cny2024_per_unit: float
    lifecycle_eac_cny2024_per_unit_year: float
    decommission_eac_cny2024_per_unit_year: float
    total_eac_cny2024_per_unit_year: float

    def __post_init__(self) -> None:
        values = (
            self.direct_cost_cny2024_per_unit,
            self.installed_cost_cny2024_per_unit,
            self.lifecycle_eac_cny2024_per_unit_year,
            self.decommission_eac_cny2024_per_unit_year,
            self.total_eac_cny2024_per_unit_year,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("annualized cost coefficients must be finite and non-negative")
        expected = (
            self.lifecycle_eac_cny2024_per_unit_year
            + self.decommission_eac_cny2024_per_unit_year
        )
        if not math.isclose(
            self.total_eac_cny2024_per_unit_year,
            expected,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("total EAC must equal lifecycle plus decommission EAC")


@dataclass(frozen=True)
class PublicTESCostPortfolio:
    """Complete public portfolio with strict sensitivity-only readiness gates."""

    mode: PublicTESCostMode
    scenario: PublicTESCostScenario
    items: tuple[PublicTESCostItem, ...]
    lifecycle_policy: PublicTESLifecyclePolicy
    price_basis_snapshot: OfficialPriceBasisSnapshot
    author_assumptions_acknowledged: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.mode, PublicTESCostMode):
            raise ValueError("mode must be selected with PublicTESCostMode")
        if not isinstance(self.scenario, PublicTESCostScenario):
            raise ValueError("scenario must be selected with PublicTESCostScenario")
        if not self.items or any(
            not isinstance(item, PublicTESCostItem) for item in self.items
        ):
            raise ValueError("items must be a non-empty public cost tuple")
        if len({item.asset_id for item in self.items}) != len(self.items):
            raise ValueError("public cost asset_id values must be unique")
        if not isinstance(self.lifecycle_policy, PublicTESLifecyclePolicy):
            raise ValueError("lifecycle_policy must be canonical")
        if not isinstance(self.price_basis_snapshot, OfficialPriceBasisSnapshot):
            raise ValueError("price_basis_snapshot must be official and canonical")
        if not isinstance(self.author_assumptions_acknowledged, bool):
            raise ValueError("author_assumptions_acknowledged must be boolean")
        if (
            self.price_basis_snapshot.target_currency != "CNY"
            or self.price_basis_snapshot.target_year != 2024
        ):
            raise ValueError("public portfolios must convert to constant CNY2024")

        account_counts = Counter(
            account
            for item in self.items
            for account in item.covered_accounts
        )
        account_counts.update(self.lifecycle_policy.covered_accounts)
        if set(account_counts) != set(TESFormalCostAccount) or any(
            count != 1 for count in account_counts.values()
        ):
            raise ValueError("public portfolio must cover every TES account exactly once")

        components = {item.component for item in self.items}
        aggregate_accounts = frozenset(
            {
                TESFormalCostAccount.SALT_INVENTORY,
                TESFormalCostAccount.STORAGE_VESSELS,
                TESFormalCostAccount.SALT_CIRCULATION,
            }
        )
        aggregate = any(
            item.covered_accounts == aggregate_accounts for item in self.items
        )
        detailed = {
            TESComponent.SALT,
            TESComponent.CIRCULATION,
        }.issubset(components)
        if self.mode is PublicTESCostMode.AGGREGATE_STORAGE:
            if not aggregate or TESComponent.SALT in components or TESComponent.CIRCULATION in components:
                raise ValueError("aggregate mode forbids separate salt/circulation costs")
        elif aggregate or not detailed:
            raise ValueError("component mode requires salt and circulation without an aggregate package")

    @property
    def formal_project_eligible(self) -> bool:
        """Public proxy portfolios can never certify Yangling project TAC."""

        return False

    @property
    def assumed_price_year_count(self) -> int:
        return sum(
            item.price_year_status is PriceYearStatus.AUTHOR_ASSUMED
            for item in self.items
        )

    @property
    def proxy_account_count(self) -> int:
        proxy_mappings = {
            PublicEvidenceMapping.AGGREGATE_ANCHOR,
            PublicEvidenceMapping.SIMILAR_COMPONENT_PROXY,
            PublicEvidenceMapping.AUTHOR_INTERPOLATION,
        }
        return sum(
            len(item.covered_accounts)
            for item in self.items
            if item.evidence_mapping in proxy_mappings
        )

    @property
    def public_sensitivity_ready(self) -> bool:
        """Open only after the author explicitly accepts disclosed assumptions."""

        return self.author_assumptions_acknowledged

    def annualized_coefficients(
        self,
    ) -> tuple[PublicTESAnnualizedCostCoefficient, ...]:
        """Convert, annualize, and retain a per-item audit trail."""

        policy = self.lifecycle_policy
        finance = ProjectFinance(policy.project_years, policy.real_discount_rate)
        coefficients: list[PublicTESAnnualizedCostCoefficient] = []
        for item in self.items:
            conversion = self.price_basis_snapshot.to_conversion(
                item.source_currency,
                item.source_price_year,
            )
            direct = item.source_value_per_unit * conversion.conversion_factor
            installed = direct * (
                policy.project_addition_multiplier
                if item.apply_project_addition_multiplier
                else 1.0
            )
            asset_class = (
                LifecycleAssetClass.EXISTING_TURBINE_REUSE
                if item.component is TESComponent.EXISTING_TURBINE_REUSE
                else LifecycleAssetClass.TES_COMPONENT
            )
            spec = LifecycleCostSpec(
                asset_id=item.asset_id,
                capacity_unit=item.basis.capacity_unit,
                currency="CNY",
                price_base_year=2024,
                initial_cost_per_unit=installed,
                service_life_years=policy.service_life_years,
                asset_class=asset_class,
                fixed_om_per_unit_year=(
                    direct * policy.fixed_om_fraction_per_year
                ),
            )
            lifecycle_eac = annualize_lifecycle_cost(
                spec,
                finance,
            ).total_equivalent_annual_cost
            decommission_npv = (
                direct
                * policy.decommission_fraction
                * finance.discount_factor(float(policy.project_years))
            )
            decommission_eac = finance.equivalent_annual_cost(decommission_npv)
            coefficients.append(
                PublicTESAnnualizedCostCoefficient(
                    item=item,
                    direct_cost_cny2024_per_unit=direct,
                    installed_cost_cny2024_per_unit=installed,
                    lifecycle_eac_cny2024_per_unit_year=lifecycle_eac,
                    decommission_eac_cny2024_per_unit_year=decommission_eac,
                    total_eac_cny2024_per_unit_year=(
                        lifecycle_eac + decommission_eac
                    ),
                )
            )
        return tuple(coefficients)

    def total_annual_cost_cny2024(
        self,
        quantities: Mapping[TESCapacityBasis, float],
    ) -> float:
        """Evaluate a disclosed quantity vector without merging unlike bases."""

        total = 0.0
        for coefficient in self.annualized_coefficients():
            basis = coefficient.item.basis
            if basis not in quantities:
                raise ValueError(f"missing public TES quantity for {basis.name}")
            quantity = quantities[basis]
            if (
                isinstance(quantity, bool)
                or not isinstance(quantity, (int, float))
                or not math.isfinite(float(quantity))
                or quantity < 0.0
            ):
                raise ValueError("public TES quantities must be finite and non-negative")
            total += coefficient.total_eac_cny2024_per_unit_year * float(quantity)
        return total


def default_price_basis_snapshot_path() -> Path:
    """Return the repository's registered official CNY2024 snapshot directory."""

    environment_path = os.environ.get("TES_BESS_PRICE_BASIS_DIR")
    if environment_path:
        candidate = Path(environment_path).expanduser()
        if not (candidate / "manifest.json").is_file():
            raise ValueError(
                "TES_BESS_PRICE_BASIS_DIR must contain the registered manifest"
            )
        return candidate

    workspace_root = Path(__file__).resolve().parents[3]
    candidates = (
        workspace_root / "数据采集" / "e0d4_price_basis_2024",
        workspace_root / "formal_data" / "e0d4_price_basis_2024",
    )
    for candidate in candidates:
        if (candidate / "manifest.json").is_file():
            return candidate
    checked = ", ".join(str(candidate) for candidate in candidates)
    raise ValueError(f"registered E0-D-4 price snapshot not found; checked: {checked}")


def _journal_item(
    *,
    asset_id: str,
    component: TESComponent,
    basis: TESCapacityBasis,
    value: float,
    currency: str,
    price_year: int,
    price_year_status: PriceYearStatus,
    evidence_id: str,
    doi: str,
    venue: str,
    impact_factor: float,
    mapping: PublicEvidenceMapping,
    accounts: frozenset[TESFormalCostAccount],
    note: str,
) -> PublicTESCostItem:
    return PublicTESCostItem(
        asset_id=asset_id,
        component=component,
        basis=basis,
        source_value_per_unit=value,
        source_currency=currency,
        source_price_year=price_year,
        price_year_status=price_year_status,
        evidence_id=evidence_id,
        source_locator=doi,
        venue=venue,
        evidence_quality=PublicEvidenceQuality.ENERGY_PLUS_JOURNAL,
        current_impact_factor=impact_factor,
        evidence_mapping=mapping,
        covered_accounts=accounts,
        boundary_note=note,
    )


def _scenario_value(
    scenario: PublicTESCostScenario,
    low: float,
    base: float,
    high: float,
) -> float:
    return {
        PublicTESCostScenario.LOW: low,
        PublicTESCostScenario.BASE: base,
        PublicTESCostScenario.HIGH: high,
    }[scenario]


def build_public_tes_cost_portfolio(
    mode: PublicTESCostMode | str,
    scenario: PublicTESCostScenario | str,
    *,
    acknowledge_author_assumptions: bool = False,
    price_basis_snapshot: OfficialPriceBasisSnapshot | None = None,
    price_basis_path: str | Path | None = None,
) -> PublicTESCostPortfolio:
    """Build one complete, explicitly sensitivity-only public TES portfolio."""

    mode = PublicTESCostMode(mode)
    scenario = PublicTESCostScenario(scenario)
    if price_basis_snapshot is not None and price_basis_path is not None:
        raise ValueError("provide price_basis_snapshot or price_basis_path, not both")
    snapshot = price_basis_snapshot or load_price_basis_snapshot(
        price_basis_path or default_price_basis_snapshot_path()
    )

    trevisan_doi = "https://doi.org/10.1016/j.enconman.2022.116362"
    klasing_doi = "https://doi.org/10.1016/j.apenergy.2024.124524"
    mctigue_doi = "https://doi.org/10.1016/j.enconman.2021.115016"
    items: list[PublicTESCostItem] = []

    if mode is PublicTESCostMode.AGGREGATE_STORAGE:
        items.append(
            PublicTESCostItem(
                asset_id="dlr_two_tank_solar_salt_package",
                component=TESComponent.STORAGE_TANK_SYSTEM,
                basis=TESCapacityBasis.FULL_SENSIBLE_HEAT_KWH_TH,
                source_value_per_unit=_scenario_value(scenario, 20.0, 21.0, 22.0),
                source_currency="EUR",
                source_price_year=2020,
                price_year_status=PriceYearStatus.EXPLICIT,
                evidence_id="dlr2021_two_tank_solar_salt",
                source_locator="https://elib.dlr.de/141315/",
                venue="DLR official engineering report",
                evidence_quality=PublicEvidenceQuality.OFFICIAL_ENGINEERING,
                current_impact_factor=None,
                evidence_mapping=PublicEvidenceMapping.AGGREGATE_ANCHOR,
                covered_accounts=frozenset(
                    {
                        TESFormalCostAccount.SALT_INVENTORY,
                        TESFormalCostAccount.STORAGE_VESSELS,
                        TESFormalCostAccount.SALT_CIRCULATION,
                    }
                ),
                boundary_note=(
                    "Two-tank Solar Salt aggregate anchor; covers salt, vessels, "
                    "and circulation only and is not a three-temperature quote. "
                    "Its internal BoP and markups are already included."
                ),
                apply_project_addition_multiplier=False,
            )
        )
    else:
        salt_value = _scenario_value(scenario, 0.5, 0.9, 1.3)
        items.extend(
            (
                _journal_item(
                    asset_id="mctigue_nitrate_salt_inventory",
                    component=TESComponent.SALT,
                    basis=TESCapacityBasis.SALT_INVENTORY_KG,
                    value=salt_value,
                    currency="USD",
                    price_year=2020,
                    price_year_status=PriceYearStatus.EXPLICIT,
                    evidence_id="mctigue2022_nitrate_salt",
                    doi=mctigue_doi,
                    venue="Energy Conversion and Management",
                    impact_factor=10.9,
                    mapping=(
                        PublicEvidenceMapping.AUTHOR_INTERPOLATION
                        if scenario is PublicTESCostScenario.BASE
                        else PublicEvidenceMapping.SIMILAR_COMPONENT_PROXY
                    ),
                    accounts=frozenset({TESFormalCostAccount.SALT_INVENTORY}),
                    note=(
                        "PTES nitrate-salt range used as a topology-mismatched "
                        "sensitivity proxy; 0.9 USD2020/kg is the author midpoint."
                    ),
                ),
                _journal_item(
                    asset_id="trevisan_storage_tank_system",
                    component=TESComponent.STORAGE_TANK_SYSTEM,
                    basis=TESCapacityBasis.FULL_SENSIBLE_HEAT_KWH_TH,
                    value=30.0,
                    currency="EUR",
                    price_year=2022,
                    price_year_status=PriceYearStatus.AUTHOR_ASSUMED,
                    evidence_id="trevisan2022_storage_tanks",
                    doi=trevisan_doi,
                    venue="Energy Conversion and Management",
                    impact_factor=10.9,
                    mapping=PublicEvidenceMapping.SIMILAR_COMPONENT_PROXY,
                    accounts=frozenset({TESFormalCostAccount.STORAGE_VESSELS}),
                    note="Published storage-tank rate; topology transfer is a proxy.",
                ),
                _journal_item(
                    asset_id="trevisan_salt_circulation",
                    component=TESComponent.CIRCULATION,
                    basis=TESCapacityBasis.FULL_SENSIBLE_HEAT_KWH_TH,
                    value=25.0,
                    currency="EUR",
                    price_year=2022,
                    price_year_status=PriceYearStatus.AUTHOR_ASSUMED,
                    evidence_id="trevisan2022_circulation",
                    doi=trevisan_doi,
                    venue="Energy Conversion and Management",
                    impact_factor=10.9,
                    mapping=PublicEvidenceMapping.SIMILAR_COMPONENT_PROXY,
                    accounts=frozenset({TESFormalCostAccount.SALT_CIRCULATION}),
                    note="Published circulation-system rate; topology transfer is a proxy.",
                ),
            )
        )
    heater_value = _scenario_value(scenario, 50.0, 100.0, 140.0)
    if scenario is PublicTESCostScenario.LOW:
        heater_source = (trevisan_doi, "trevisan2022_electric_heater", 2022, 10.9)
        heater_venue = "Energy Conversion and Management"
    else:
        heater_source = (klasing_doi, "klasing2025_electric_heater", 2024, 11.0)
        heater_venue = "Applied Energy"
    steam_generator_value = _scenario_value(scenario, 28.0, 46.0, 120.0)
    items.extend(
        (
            _journal_item(
                asset_id="trevisan_transformer",
                component=TESComponent.TRANSFORMER,
                basis=TESCapacityBasis.ELECTRIC_HEATER_INPUT_KW_EL,
                value=30.0,
                currency="EUR",
                price_year=2022,
                price_year_status=PriceYearStatus.AUTHOR_ASSUMED,
                evidence_id="trevisan2022_transformer",
                doi=trevisan_doi,
                venue="Energy Conversion and Management",
                impact_factor=10.9,
                mapping=PublicEvidenceMapping.SIMILAR_COMPONENT_PROXY,
                accounts=frozenset(
                    {TESFormalCostAccount.TRANSFORMER_AND_ELECTRICAL_CONNECTION}
                ),
                note="Published transformer rate; site connection scope is a proxy.",
            ),
            _journal_item(
                asset_id="public_electric_heater",
                component=TESComponent.ELECTRIC_HEATER,
                basis=TESCapacityBasis.ELECTRIC_HEATER_INPUT_KW_EL,
                value=heater_value,
                currency="EUR",
                price_year=heater_source[2],
                price_year_status=PriceYearStatus.AUTHOR_ASSUMED,
                evidence_id=heater_source[1],
                doi=heater_source[0],
                venue=heater_venue,
                impact_factor=heater_source[3],
                mapping=PublicEvidenceMapping.SIMILAR_COMPONENT_PROXY,
                accounts=frozenset({TESFormalCostAccount.ELECTRIC_HEATER}),
                note="Published heater rate transferred to the E0 electric-charge port.",
            ),
            _journal_item(
                asset_id="public_high_grade_steam_hx",
                component=TESComponent.HIGH_GRADE_STEAM_HX,
                basis=TESCapacityBasis.HIGH_GRADE_STEAM_HX_INPUT_KW_TH,
                value=steam_generator_value,
                currency="EUR",
                price_year=2024,
                price_year_status=PriceYearStatus.AUTHOR_ASSUMED,
                evidence_id="klasing2025_sgs_proxy_high_grade_hx",
                doi=klasing_doi,
                venue="Applied Energy",
                impact_factor=11.0,
                mapping=PublicEvidenceMapping.SIMILAR_COMPONENT_PROXY,
                accounts=frozenset(
                    {TESFormalCostAccount.HIGH_GRADE_STEAM_CHARGE_HX}
                ),
                note="Steam-generator range used as a disclosed charge-HX proxy.",
            ),
            _journal_item(
                asset_id="public_medium_grade_steam_hx",
                component=TESComponent.MEDIUM_GRADE_STEAM_HX,
                basis=TESCapacityBasis.MEDIUM_GRADE_STEAM_HX_INPUT_KW_TH,
                value=steam_generator_value,
                currency="EUR",
                price_year=2024,
                price_year_status=PriceYearStatus.AUTHOR_ASSUMED,
                evidence_id="klasing2025_sgs_proxy_medium_grade_hx",
                doi=klasing_doi,
                venue="Applied Energy",
                impact_factor=11.0,
                mapping=PublicEvidenceMapping.SIMILAR_COMPONENT_PROXY,
                accounts=frozenset(
                    {TESFormalCostAccount.MEDIUM_GRADE_STEAM_CHARGE_HX}
                ),
                note="Steam-generator range used as a disclosed charge-HX proxy.",
            ),
            _journal_item(
                asset_id="klasing_salt_to_steam_generator",
                component=TESComponent.SALT_TO_STEAM_GENERATOR,
                basis=TESCapacityBasis.SALT_TO_STEAM_GENERATOR_INPUT_KW_TH,
                value=steam_generator_value,
                currency="EUR",
                price_year=2024,
                price_year_status=PriceYearStatus.AUTHOR_ASSUMED,
                evidence_id="klasing2025_steam_generator",
                doi=klasing_doi,
                venue="Applied Energy",
                impact_factor=11.0,
                mapping=PublicEvidenceMapping.DIRECT,
                accounts=frozenset(
                    {TESFormalCostAccount.SALT_TO_STEAM_GENERATOR}
                ),
                note="Published steam-generator range on thermal input capacity.",
            ),
            _journal_item(
                asset_id="public_heat_delivery_hx",
                component=TESComponent.HEAT_DELIVERY_HX,
                basis=TESCapacityBasis.HEAT_DELIVERY_HX_INPUT_KW_TH,
                value=steam_generator_value,
                currency="EUR",
                price_year=2024,
                price_year_status=PriceYearStatus.AUTHOR_ASSUMED,
                evidence_id="klasing2025_sgs_proxy_heat_delivery_hx",
                doi=klasing_doi,
                venue="Applied Energy",
                impact_factor=11.0,
                mapping=PublicEvidenceMapping.SIMILAR_COMPONENT_PROXY,
                accounts=frozenset({TESFormalCostAccount.HEAT_DELIVERY_HX}),
                note="Steam-generator range used as a disclosed delivery-HX proxy.",
            ),
            PublicTESCostItem(
                asset_id="existing_turbine_reuse_boundary",
                component=TESComponent.EXISTING_TURBINE_REUSE,
                basis=TESCapacityBasis.SYSTEM_COUNT,
                source_value_per_unit=0.0,
                source_currency="CNY",
                source_price_year=2024,
                price_year_status=PriceYearStatus.EXPLICIT,
                evidence_id="e0_existing_turbine_reuse_boundary",
                source_locator="model://e0/existing-turbine-reuse",
                venue="E0 model boundary",
                evidence_quality=PublicEvidenceQuality.MODEL_BOUNDARY,
                current_impact_factor=None,
                evidence_mapping=PublicEvidenceMapping.MODEL_BOUNDARY,
                covered_accounts=frozenset(
                    {TESFormalCostAccount.POWER_BLOCK_RETROFIT}
                ),
                boundary_note=(
                    "Zero means existing-turbine reuse is inside the declared model "
                    "boundary; it is not evidence that retrofit cost is zero."
                ),
                apply_project_addition_multiplier=False,
            ),
        )
    )

    lifecycle_policy = PublicTESLifecyclePolicy(
        project_years=30,
        service_life_years=_scenario_value(scenario, 35.0, 30.0, 25.0),
        real_discount_rate=0.05,
        project_addition_multiplier=_scenario_value(scenario, 1.1, 1.3, 1.5),
        fixed_om_fraction_per_year=_scenario_value(scenario, 0.01, 0.03, 0.05),
        decommission_fraction=0.02,
        evidence_ids=(
            "mctigue2022_lifecycle_sensitivity",
            "trevisan2022_project_additions_lifecycle",
        ),
    )
    return PublicTESCostPortfolio(
        mode=mode,
        scenario=scenario,
        items=tuple(items),
        lifecycle_policy=lifecycle_policy,
        price_basis_snapshot=snapshot,
        author_assumptions_acknowledged=acknowledge_author_assumptions,
    )
