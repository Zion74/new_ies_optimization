"""Sensitivity-only engineering cost anchors with auditable source boundaries.

This module deliberately does not issue formal cost-evidence certificates.  It
loads an official NREL engineering anchor, preserves its power/usable-energy
denominators, and prevents the source FOM augmentation allowance from being
combined with a separate replacement ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

from tes_bess_boundary.cost_evidence import (
    CostEvidenceAudit,
    CostEvidenceRecord,
    CostEvidenceUse,
    CostSourceProvenance,
    PriceBaseStatus,
    TechnologyBoundaryFit,
    VenueEvidenceTier,
    build_e0d10_reference_cost_audit,
)
from tes_bess_boundary.economics import PriceBasisConversion


ANCHOR_SCHEMA = "tes_bess_boundary.e0d11_sensitivity_cost_anchor.v1"
MANIFEST_SCHEMA = "tes_bess_boundary.e0d11_sensitivity_cost_anchor_manifest.v1"
NREL_EVIDENCE_ID = "nrel2022_utility_bess"
NREL_CAPACITY_DENOMINATOR = "kW_DC_and_kWh_DC"


def _positive_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be finite and positive")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{field_name} must be finite and positive")
    return number


def _positive_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _json_object(path: Path, description: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{description} must be readable valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{description} must contain a JSON object")
    return value


def _registered_file(
    directory: Path,
    entry: object,
    description: str,
) -> tuple[Path, str]:
    if not isinstance(entry, dict):
        raise ValueError(f"manifest must register {description}")
    file_name = _non_empty_string(entry.get("file"), f"{description} file")
    recorded_sha256 = entry.get("sha256")
    if (
        not isinstance(recorded_sha256, str)
        or len(recorded_sha256) != 64
        or any(character not in "0123456789abcdef" for character in recorded_sha256)
    ):
        raise ValueError(f"{description} SHA-256 must be lowercase hexadecimal")
    path = (directory / file_name).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError(f"{description} file must stay inside the anchor directory")
    try:
        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError(f"{description} file must be readable") from error
    if actual_sha256 != recorded_sha256:
        raise ValueError(f"{description} SHA-256 does not match the registered file")
    return path, recorded_sha256


def _object(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return value


def _official_engineering_evidence(record: CostEvidenceRecord) -> None:
    if not isinstance(record, CostEvidenceRecord):
        raise ValueError("evidence must be a canonical CostEvidenceRecord")
    required = (
        record.venue_tier is VenueEvidenceTier.OFFICIAL_ENGINEERING,
        record.allowed_use is CostEvidenceUse.OFFICIAL_ENGINEERING_ANCHOR,
        record.price_base_status is PriceBaseStatus.EXPLICIT,
        record.technology_fit is TechnologyBoundaryFit.DIRECT,
        record.provenance is CostSourceProvenance.OFFICIAL_BOTTOM_UP,
        record.capacity_denominator == NREL_CAPACITY_DENOMINATOR,
    )
    if not all(required):
        raise ValueError(
            "sensitivity cost evidence must remain an official engineering anchor "
            "with an explicit direct bottom-up kW_DC/kWh_DC boundary"
        )


@dataclass(frozen=True)
class SensitivityBESSCostAnchor:
    """One source-locked BESS cost anchor that is ineligible for formal use."""

    anchor_id: str
    evidence: CostEvidenceRecord
    benchmark_year: int
    source_currency: str
    price_base_year: int
    rated_power_kw_dc: float
    usable_energy_kwh_dc: float
    minimum_duration_hours: float
    maximum_duration_hours: float
    analysis_life_years: int
    energy_cost_per_kwh_usable: float
    power_cost_per_kw: float
    reported_total_cost_per_kw: float
    fixed_om_fraction_of_capex_per_year: float
    reported_fixed_om_per_kw_year: float
    augmentation_years: tuple[int, ...]
    augmentation_fraction_each: float
    source_workbook_sha256: str
    source_workbook_url: str
    source_pages: tuple[str, ...]
    source_cells: tuple[str, ...]
    excluded_performance_parameters: tuple[str, ...]

    def __post_init__(self) -> None:
        _non_empty_string(self.anchor_id, "anchor_id")
        _official_engineering_evidence(self.evidence)
        if self.evidence.evidence_id != NREL_EVIDENCE_ID:
            raise ValueError(f"evidence_id must be {NREL_EVIDENCE_ID}")
        _positive_integer(self.benchmark_year, "benchmark_year")
        _positive_integer(self.price_base_year, "price_base_year")
        _positive_integer(self.analysis_life_years, "analysis_life_years")
        if self.source_currency != "USD" or self.price_base_year != 2020:
            raise ValueError("the NREL anchor source basis must remain 2020 USD")
        if (
            self.evidence.currency != self.source_currency
            or self.evidence.price_base_year != self.price_base_year
        ):
            raise ValueError("anchor price basis must match its evidence record")
        for field_name in (
            "rated_power_kw_dc",
            "usable_energy_kwh_dc",
            "minimum_duration_hours",
            "maximum_duration_hours",
            "energy_cost_per_kwh_usable",
            "power_cost_per_kw",
            "reported_total_cost_per_kw",
            "fixed_om_fraction_of_capex_per_year",
            "reported_fixed_om_per_kw_year",
            "augmentation_fraction_each",
        ):
            _positive_number(getattr(self, field_name), field_name)
        if self.minimum_duration_hours >= self.maximum_duration_hours:
            raise ValueError("supported duration bounds must be increasing")
        if not (
            self.minimum_duration_hours
            <= self.duration_hours
            <= self.maximum_duration_hours
        ):
            raise ValueError("reference duration must lie inside supported duration")
        if self.analysis_life_years != 30:
            raise ValueError("the source FOM boundary is defined for a 30-year life")
        if self.augmentation_years != (10, 20):
            raise ValueError("source augmentation years must remain (10, 20)")
        if not math.isclose(
            self.augmentation_fraction_each,
            0.2,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("each source augmentation must remain 20%")
        if not math.isclose(
            self.reconciled_total_cost_per_kw,
            self.reported_total_cost_per_kw,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError("power and energy cost components do not reconcile")
        if not math.isclose(
            self.reconciled_fixed_om_per_kw_year,
            self.reported_fixed_om_per_kw_year,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError("source FOM does not reconcile to its CAPEX fraction")
        if len(self.source_workbook_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in self.source_workbook_sha256
        ):
            raise ValueError("source_workbook_sha256 must be lowercase hexadecimal")
        if not self.source_workbook_url.startswith("https://"):
            raise ValueError("source_workbook_url must use HTTPS")
        for field_name in (
            "source_pages",
            "source_cells",
            "excluded_performance_parameters",
        ):
            values = getattr(self, field_name)
            if not isinstance(values, tuple) or not values:
                raise ValueError(f"{field_name} must be a non-empty immutable tuple")
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{field_name} entries must be non-empty strings")
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} entries must be unique")
        if any(not page.startswith("https://") for page in self.source_pages):
            raise ValueError("source_pages entries must use HTTPS")

    @property
    def duration_hours(self) -> float:
        return self.usable_energy_kwh_dc / self.rated_power_kw_dc

    @property
    def reconciled_total_cost_per_kw(self) -> float:
        return (
            self.energy_cost_per_kwh_usable * self.duration_hours
            + self.power_cost_per_kw
        )

    @property
    def reconciliation_error_per_kw(self) -> float:
        return self.reconciled_total_cost_per_kw - self.reported_total_cost_per_kw

    @property
    def reconciled_fixed_om_per_kw_year(self) -> float:
        return (
            self.fixed_om_fraction_of_capex_per_year * self.reconciled_total_cost_per_kw
        )

    @property
    def formal_baseline_eligible(self) -> bool:
        return False

    def build_ledger(
        self,
        *,
        power_kw: float,
        usable_energy_kwh: float,
        use_source_fixed_om: bool = True,
        has_separate_replacement_ledger: bool = False,
    ) -> SensitivityBESSCostLedger:
        """Scale the disclosed two-denominator ledger inside its duration range."""

        return SensitivityBESSCostLedger(
            anchor=self,
            power_kw=power_kw,
            usable_energy_kwh=usable_energy_kwh,
            use_source_fixed_om=use_source_fixed_om,
            has_separate_replacement_ledger=has_separate_replacement_ledger,
        )


@dataclass(frozen=True)
class SensitivityBESSCostLedger:
    """Scaled source-basis ledger with an explicit maintenance-cost choice."""

    anchor: SensitivityBESSCostAnchor
    power_kw: float
    usable_energy_kwh: float
    use_source_fixed_om: bool
    has_separate_replacement_ledger: bool

    def __post_init__(self) -> None:
        if not isinstance(self.anchor, SensitivityBESSCostAnchor):
            raise ValueError("anchor must be a SensitivityBESSCostAnchor")
        _positive_number(self.power_kw, "power_kw")
        _positive_number(self.usable_energy_kwh, "usable_energy_kwh")
        for field_name in (
            "use_source_fixed_om",
            "has_separate_replacement_ledger",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be boolean")
        if not (
            self.anchor.minimum_duration_hours
            <= self.duration_hours
            <= self.anchor.maximum_duration_hours
        ):
            raise ValueError("ledger duration is outside the source-supported duration")
        if self.use_source_fixed_om and self.has_separate_replacement_ledger:
            raise ValueError(
                "source FOM already includes augmentations; combining it with a "
                "separate replacement ledger would double count cell replacement"
            )

    @property
    def duration_hours(self) -> float:
        return self.usable_energy_kwh / self.power_kw

    @property
    def power_component_cost(self) -> float:
        return self.power_kw * self.anchor.power_cost_per_kw

    @property
    def energy_component_cost(self) -> float:
        return self.usable_energy_kwh * self.anchor.energy_cost_per_kwh_usable

    @property
    def initial_capital_cost(self) -> float:
        return self.power_component_cost + self.energy_component_cost

    @property
    def annual_fixed_om_cost(self) -> float:
        if not self.use_source_fixed_om:
            return 0.0
        return (
            self.anchor.fixed_om_fraction_of_capex_per_year * self.initial_capital_cost
        )

    @property
    def is_reference_duration(self) -> bool:
        return math.isclose(
            self.duration_hours,
            self.anchor.duration_hours,
            rel_tol=1e-12,
            abs_tol=1e-12,
        )

    @property
    def is_reference_scale(self) -> bool:
        return math.isclose(
            self.power_kw,
            self.anchor.rated_power_kw_dc,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ) and math.isclose(
            self.usable_energy_kwh,
            self.anchor.usable_energy_kwh_dc,
            rel_tol=1e-12,
            abs_tol=1e-9,
        )


@dataclass(frozen=True)
class SensitivityBESSCostConversion:
    """One-time price-basis conversion that retains the source ledger."""

    source_ledger: SensitivityBESSCostLedger
    conversion: PriceBasisConversion

    def __post_init__(self) -> None:
        if not isinstance(self.source_ledger, SensitivityBESSCostLedger):
            raise ValueError("source_ledger must be a SensitivityBESSCostLedger")
        if not isinstance(self.conversion, PriceBasisConversion):
            raise ValueError("conversion must be a PriceBasisConversion")
        anchor = self.source_ledger.anchor
        if (
            self.conversion.source_currency != anchor.source_currency
            or self.conversion.source_price_base_year != anchor.price_base_year
        ):
            raise ValueError("conversion source must match the engineering anchor")

    @property
    def conversion_factor(self) -> float:
        return self.conversion.conversion_factor

    @property
    def currency(self) -> str:
        return self.conversion.target_currency

    @property
    def price_base_year(self) -> int:
        return self.conversion.target_price_base_year

    @property
    def power_component_cost(self) -> float:
        return self.source_ledger.power_component_cost * self.conversion_factor

    @property
    def energy_component_cost(self) -> float:
        return self.source_ledger.energy_component_cost * self.conversion_factor

    @property
    def initial_capital_cost(self) -> float:
        return self.source_ledger.initial_capital_cost * self.conversion_factor

    @property
    def annual_fixed_om_cost(self) -> float:
        return self.source_ledger.annual_fixed_om_cost * self.conversion_factor


def convert_sensitivity_cost_ledger(
    ledger: SensitivityBESSCostLedger,
    conversion: PriceBasisConversion,
) -> SensitivityBESSCostConversion:
    """Convert a sensitivity ledger while preserving the source evidence object."""

    return SensitivityBESSCostConversion(
        source_ledger=ledger,
        conversion=conversion,
    )


def load_nrel_atb_2022_bess_cost_anchor(
    directory: str | Path,
    *,
    evidence_audit: CostEvidenceAudit | None = None,
) -> SensitivityBESSCostAnchor:
    """Load and hash-check the E0-D-11 official engineering anchor directory."""

    directory = Path(directory)
    manifest = _json_object(directory / "manifest.json", "anchor manifest")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"anchor manifest schema must be {MANIFEST_SCHEMA}")
    workbook_entry = manifest.get("source_workbook")
    _, workbook_sha256 = _registered_file(
        directory,
        workbook_entry,
        "source workbook",
    )
    assert isinstance(workbook_entry, dict)
    workbook_url = _non_empty_string(
        workbook_entry.get("url"),
        "source workbook URL",
    )
    if not workbook_url.startswith("https://"):
        raise ValueError("source workbook URL must use HTTPS")
    extraction_path, _ = _registered_file(
        directory,
        manifest.get("extraction"),
        "extraction",
    )
    source_pages_raw = manifest.get("source_pages")
    if not isinstance(source_pages_raw, list) or not source_pages_raw:
        raise ValueError("source_pages must be a non-empty list")
    source_pages = tuple(
        _non_empty_string(page, "source page") for page in source_pages_raw
    )

    raw = _json_object(extraction_path, "anchor extraction")
    if raw.get("schema") != ANCHOR_SCHEMA:
        raise ValueError(f"anchor extraction schema must be {ANCHOR_SCHEMA}")
    evidence_id = _non_empty_string(raw.get("evidence_id"), "evidence_id")
    audit = evidence_audit or build_e0d10_reference_cost_audit()
    if not isinstance(audit, CostEvidenceAudit):
        raise ValueError("evidence_audit must be a CostEvidenceAudit")
    evidence = audit.get(evidence_id)

    system = _object(raw.get("system"), "system")
    supported_duration = system.get("supported_duration_hours")
    if not isinstance(supported_duration, list) or len(supported_duration) != 2:
        raise ValueError("supported_duration_hours must contain two bounds")
    capital_cost = _object(raw.get("capital_cost"), "capital_cost")
    fixed_om = _object(raw.get("fixed_om"), "fixed_om")
    if fixed_om.get("includes_capacity_augmentation") is not True:
        raise ValueError("source FOM must disclose included capacity augmentation")
    augmentation_years_raw = fixed_om.get("augmentation_years")
    if not isinstance(augmentation_years_raw, list):
        raise ValueError("augmentation_years must be a list")
    augmentation_years = tuple(
        _positive_integer(year, "augmentation year") for year in augmentation_years_raw
    )

    source_cells_raw = raw.get("source_cells")
    if not isinstance(source_cells_raw, list):
        raise ValueError("source_cells must be a list")
    source_cells = tuple(
        _non_empty_string(cell, "source cell") for cell in source_cells_raw
    )
    conflicts_raw = raw.get("excluded_performance_conflicts")
    if not isinstance(conflicts_raw, list) or not conflicts_raw:
        raise ValueError("excluded_performance_conflicts must be a non-empty list")
    excluded_parameters: list[str] = []
    for conflict in conflicts_raw:
        conflict_object = _object(conflict, "performance conflict")
        if conflict_object.get("decision") != "excluded_from_cost_anchor":
            raise ValueError("performance conflicts must remain excluded")
        excluded_parameters.append(
            _non_empty_string(
                conflict_object.get("parameter"),
                "excluded performance parameter",
            )
        )

    return SensitivityBESSCostAnchor(
        anchor_id=_non_empty_string(raw.get("anchor_id"), "anchor_id"),
        evidence=evidence,
        benchmark_year=_positive_integer(raw.get("benchmark_year"), "benchmark_year"),
        source_currency=_non_empty_string(
            raw.get("source_currency"),
            "source_currency",
        ),
        price_base_year=_positive_integer(
            raw.get("price_base_year"),
            "price_base_year",
        ),
        rated_power_kw_dc=_positive_number(
            system.get("rated_power_kw_dc"),
            "rated_power_kw_dc",
        ),
        usable_energy_kwh_dc=_positive_number(
            system.get("usable_energy_kwh_dc"),
            "usable_energy_kwh_dc",
        ),
        minimum_duration_hours=_positive_number(
            supported_duration[0],
            "minimum_duration_hours",
        ),
        maximum_duration_hours=_positive_number(
            supported_duration[1],
            "maximum_duration_hours",
        ),
        analysis_life_years=_positive_integer(
            system.get("analysis_life_years"),
            "analysis_life_years",
        ),
        energy_cost_per_kwh_usable=_positive_number(
            capital_cost.get("energy_cost_per_kwh_usable"),
            "energy_cost_per_kwh_usable",
        ),
        power_cost_per_kw=_positive_number(
            capital_cost.get("power_cost_per_kw"),
            "power_cost_per_kw",
        ),
        reported_total_cost_per_kw=_positive_number(
            capital_cost.get("reported_total_cost_per_kw_4h"),
            "reported_total_cost_per_kw_4h",
        ),
        fixed_om_fraction_of_capex_per_year=_positive_number(
            fixed_om.get("fraction_of_capex_per_year"),
            "fraction_of_capex_per_year",
        ),
        reported_fixed_om_per_kw_year=_positive_number(
            fixed_om.get("reported_cost_per_kw_year_4h"),
            "reported_cost_per_kw_year_4h",
        ),
        augmentation_years=augmentation_years,
        augmentation_fraction_each=_positive_number(
            fixed_om.get("augmentation_fraction_each"),
            "augmentation_fraction_each",
        ),
        source_workbook_sha256=workbook_sha256,
        source_workbook_url=workbook_url,
        source_pages=source_pages,
        source_cells=source_cells,
        excluded_performance_parameters=tuple(excluded_parameters),
    )
