"""Pre-model evidence gate for lifecycle cost inputs.

The economics kernel can validate currencies and price years once supplied.  This
module answers the earlier question: whether a source is eligible to supply a
formal baseline cost at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VenueEvidenceTier(str, Enum):
    """Evidence tier kept separate from a source's numerical precision."""

    CORE_PEER_REVIEWED = "core_peer_reviewed"
    OFFICIAL_ENGINEERING = "official_engineering"
    BELOW_USER_GATE = "below_user_gate"


class PriceBaseStatus(str, Enum):
    """Whether the currency price basis is auditable from the source."""

    EXPLICIT = "explicit"
    AMBIGUOUS = "ambiguous"
    NOT_REPORTED = "not_reported"
    NOT_APPLICABLE = "not_applicable"


class TechnologyBoundaryFit(str, Enum):
    """Fit between the reported cost boundary and the modeled asset."""

    DIRECT = "direct"
    SYSTEM_AGGREGATE = "system_aggregate"
    TOPOLOGY_MISMATCH = "topology_mismatch"
    SCALE_MISMATCH = "scale_mismatch"
    METHODOLOGY_ONLY = "methodology_only"
    EXCLUDED = "excluded"


class CostSourceProvenance(str, Enum):
    """Provenance of the underlying cost value, not merely the citing venue."""

    AUTHOR_BOTTOM_UP_OR_NORMALIZED = "author_bottom_up_or_normalized"
    MIXED_REUSED_SOURCES = "mixed_reused_sources"
    OFFICIAL_BOTTOM_UP = "official_bottom_up"
    SECONDARY_TRANSCRIPTION = "secondary_transcription"
    NOT_APPLICABLE = "not_applicable"


class CostEvidenceUse(str, Enum):
    """Only FORMAL_CANDIDATE is eligible for a formal baseline certificate."""

    FORMAL_CANDIDATE = "formal_candidate"
    BLOCKED_PENDING_PRICE_BASE = "blocked_pending_price_base"
    AGGREGATE_ANCHOR_ONLY = "aggregate_anchor_only"
    OFFICIAL_ENGINEERING_ANCHOR = "official_engineering_anchor"
    SENSITIVITY_ONLY = "sensitivity_only"
    METHODOLOGY_ONLY = "methodology_only"
    EXCLUDED = "excluded"


def _is_iso_currency(value: str) -> bool:
    return len(value) == 3 and value.isalpha() and value == value.upper()


@dataclass(frozen=True)
class LinkedAuthorExpansion:
    """Official same-author material that expands a peer-reviewed source."""

    source_locator: str
    relationship: str
    crosswalk_note: str

    def __post_init__(self) -> None:
        for field_name in ("source_locator", "relationship", "crosswalk_note"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        locator = self.source_locator.strip().lower()
        if not (locator.startswith("10.") or locator.startswith("https://")):
            raise ValueError(
                "linked author expansion requires a DOI or HTTPS official locator"
            )


@dataclass(frozen=True)
class CostEvidenceRecord:
    """One auditable claim about the eligibility of a cost parameter source."""

    evidence_id: str
    source_locator: str
    venue_tier: VenueEvidenceTier
    price_base_status: PriceBaseStatus
    currency: str | None
    price_base_year: int | None
    capacity_denominator: str
    technology_fit: TechnologyBoundaryFit
    provenance: CostSourceProvenance
    allowed_use: CostEvidenceUse
    note: str
    linked_author_expansion: LinkedAuthorExpansion | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "evidence_id",
            "source_locator",
            "capacity_denominator",
            "note",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        for field_name, enum_type in (
            ("venue_tier", VenueEvidenceTier),
            ("price_base_status", PriceBaseStatus),
            ("technology_fit", TechnologyBoundaryFit),
            ("provenance", CostSourceProvenance),
            ("allowed_use", CostEvidenceUse),
        ):
            if not isinstance(getattr(self, field_name), enum_type):
                raise ValueError(
                    f"{field_name} must be selected with {enum_type.__name__}"
                )
        if (
            self.venue_tier is VenueEvidenceTier.CORE_PEER_REVIEWED
            and not self.source_locator.strip().lower().startswith("10.")
        ):
            raise ValueError("core peer-reviewed cost evidence requires a DOI")
        if self.currency is not None and (
            not isinstance(self.currency, str) or not _is_iso_currency(self.currency)
        ):
            raise ValueError("currency must be an uppercase ISO 4217 code or None")
        if self.price_base_year is not None and (
            isinstance(self.price_base_year, bool)
            or not isinstance(self.price_base_year, int)
            or self.price_base_year <= 0
        ):
            raise ValueError("price_base_year must be a positive integer or None")
        if self.price_base_status is PriceBaseStatus.EXPLICIT:
            if self.currency is None or self.price_base_year is None:
                raise ValueError(
                    "an explicit price basis requires currency and price_base_year"
                )
        elif self.price_base_year is not None:
            raise ValueError(
                "a non-explicit price basis cannot claim a price_base_year"
            )
        if self.price_base_status is PriceBaseStatus.NOT_APPLICABLE and (
            self.currency is not None or self.price_base_year is not None
        ):
            raise ValueError(
                "a non-price record cannot claim currency or price_base_year"
            )
        if self.linked_author_expansion is not None and not isinstance(
            self.linked_author_expansion,
            LinkedAuthorExpansion,
        ):
            raise ValueError(
                "linked_author_expansion must be a LinkedAuthorExpansion or None"
            )

    def formal_blockers(
        self,
        *,
        expected_capacity_denominator: str | None = None,
    ) -> tuple[str, ...]:
        """Return deterministic reasons why this record cannot certify a baseline."""

        if expected_capacity_denominator is not None and (
            not isinstance(expected_capacity_denominator, str)
            or not expected_capacity_denominator.strip()
        ):
            raise ValueError(
                "expected_capacity_denominator must be a non-empty string or None"
            )
        blockers: list[str] = []
        if self.venue_tier is not VenueEvidenceTier.CORE_PEER_REVIEWED:
            blockers.append("venue_tier")
        if self.allowed_use is not CostEvidenceUse.FORMAL_CANDIDATE:
            blockers.append("allowed_use")
        if self.price_base_status is not PriceBaseStatus.EXPLICIT:
            blockers.append("price_base")
        if self.technology_fit is not TechnologyBoundaryFit.DIRECT:
            blockers.append("technology_boundary")
        if self.provenance is not CostSourceProvenance.AUTHOR_BOTTOM_UP_OR_NORMALIZED:
            blockers.append("source_provenance")
        if (
            expected_capacity_denominator is not None
            and self.capacity_denominator != expected_capacity_denominator
        ):
            blockers.append("capacity_denominator")
        return tuple(blockers)

    def certify_formal_baseline(
        self,
        *,
        expected_capacity_denominator: str,
    ) -> FormalCostEvidenceCertificate:
        """Issue a certificate only when every evidence dimension is admissible."""

        blockers = self.formal_blockers(
            expected_capacity_denominator=expected_capacity_denominator
        )
        if blockers:
            raise ValueError(
                f"cost evidence {self.evidence_id!r} is not formal-baseline eligible: "
                + ", ".join(blockers)
            )
        return FormalCostEvidenceCertificate(
            evidence=self,
            certified_capacity_denominator=expected_capacity_denominator,
        )


@dataclass(frozen=True)
class FormalCostEvidenceCertificate:
    """Non-forgeable-by-data certificate returned by the eligibility gate."""

    evidence: CostEvidenceRecord
    certified_capacity_denominator: str

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, CostEvidenceRecord):
            raise ValueError("evidence must be a CostEvidenceRecord")
        blockers = self.evidence.formal_blockers(
            expected_capacity_denominator=self.certified_capacity_denominator
        )
        if blockers:
            raise ValueError("a formal cost evidence certificate must be canonical")


@dataclass(frozen=True)
class CostEvidenceAudit:
    """Immutable registry used before constructing a formal cost portfolio."""

    records: tuple[CostEvidenceRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or not self.records:
            raise ValueError(
                "cost evidence records must be a non-empty immutable tuple"
            )
        if any(not isinstance(record, CostEvidenceRecord) for record in self.records):
            raise ValueError("cost evidence audit entries must be canonical records")
        evidence_ids = tuple(record.evidence_id for record in self.records)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("cost evidence_id values must be unique")

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(record.evidence_id for record in self.records)

    @property
    def formal_candidate_ids(self) -> tuple[str, ...]:
        return tuple(
            record.evidence_id
            for record in self.records
            if not record.formal_blockers()
        )

    def get(self, evidence_id: str) -> CostEvidenceRecord:
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            raise ValueError("evidence_id must be a non-empty string")
        for record in self.records:
            if record.evidence_id == evidence_id:
                return record
        raise KeyError(evidence_id)

    def certify_formal_portfolio(
        self,
        required_evidence: tuple[tuple[str, str], ...],
    ) -> tuple[FormalCostEvidenceCertificate, ...]:
        """Certify an exact, unique evidence-id/denominator portfolio request."""

        if not isinstance(required_evidence, tuple) or not required_evidence:
            raise ValueError("required_evidence must be a non-empty immutable tuple")
        if any(
            not isinstance(item, tuple)
            or len(item) != 2
            or any(not isinstance(value, str) or not value.strip() for value in item)
            for item in required_evidence
        ):
            raise ValueError(
                "required_evidence entries must be (evidence_id, denominator) pairs"
            )
        evidence_ids = tuple(item[0] for item in required_evidence)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("formal portfolio evidence_id values must be unique")
        return tuple(
            self.get(evidence_id).certify_formal_baseline(
                expected_capacity_denominator=denominator
            )
            for evidence_id, denominator in required_evidence
        )


def build_e0d10_reference_cost_audit() -> CostEvidenceAudit:
    """Build the current audited sources under the approved linked-source policy."""

    return CostEvidenceAudit(
        records=(
            CostEvidenceRecord(
                evidence_id="schmidt2019_bess_capex",
                source_locator="10.1016/j.joule.2018.12.008",
                venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
                price_base_status=PriceBaseStatus.AMBIGUOUS,
                currency="USD",
                price_base_year=None,
                capacity_denominator="kW_and_kWh",
                technology_fit=TechnologyBoundaryFit.DIRECT,
                provenance=CostSourceProvenance.MIXED_REUSED_SOURCES,
                allowed_use=CostEvidenceUse.BLOCKED_PENDING_PRICE_BASE,
                note="Table S4 has 2015 inputs while result figures report US$2018.",
            ),
            CostEvidenceRecord(
                evidence_id="trevisan2022_tes_components",
                source_locator="10.1016/j.enconman.2022.116362",
                venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
                price_base_status=PriceBaseStatus.NOT_REPORTED,
                currency="EUR",
                price_base_year=None,
                capacity_denominator="component_specific",
                technology_fit=TechnologyBoundaryFit.DIRECT,
                provenance=CostSourceProvenance.MIXED_REUSED_SOURCES,
                allowed_use=CostEvidenceUse.BLOCKED_PENDING_PRICE_BASE,
                note="Table 8 combines component values from several source vintages.",
            ),
            CostEvidenceRecord(
                evidence_id="klasing2025_tes_components",
                source_locator="10.1016/j.apenergy.2024.124524",
                venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
                price_base_status=PriceBaseStatus.NOT_REPORTED,
                currency="EUR",
                price_base_year=None,
                capacity_denominator="component_specific",
                technology_fit=TechnologyBoundaryFit.DIRECT,
                provenance=CostSourceProvenance.MIXED_REUSED_SOURCES,
                allowed_use=CostEvidenceUse.BLOCKED_PENDING_PRICE_BASE,
                note="Only selected author correlations have an explicit 2023 EUR basis.",
            ),
            CostEvidenceRecord(
                evidence_id="klasing2025_system_anchor",
                source_locator="10.1016/j.apenergy.2024.124524",
                venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
                price_base_status=PriceBaseStatus.NOT_REPORTED,
                currency="EUR",
                price_base_year=None,
                capacity_denominator="kWh_th_system",
                technology_fit=TechnologyBoundaryFit.SYSTEM_AGGREGATE,
                provenance=CostSourceProvenance.MIXED_REUSED_SOURCES,
                allowed_use=CostEvidenceUse.AGGREGATE_ANCHOR_ONLY,
                note="System total contains components that must not be counted again.",
            ),
            CostEvidenceRecord(
                evidence_id="wang2025_hitec_salt",
                source_locator="10.1016/j.apenergy.2025.126876",
                venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
                price_base_status=PriceBaseStatus.NOT_REPORTED,
                currency="USD",
                price_base_year=None,
                capacity_denominator="kg_salt",
                technology_fit=TechnologyBoundaryFit.DIRECT,
                provenance=CostSourceProvenance.MIXED_REUSED_SOURCES,
                allowed_use=CostEvidenceUse.SENSITIVITY_ONLY,
                note="HITEC material and temperatures are relevant but price year is absent.",
            ),
            CostEvidenceRecord(
                evidence_id="li2026_tes_retrofit",
                source_locator="10.1016/j.energy.2026.141711",
                venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
                price_base_status=PriceBaseStatus.NOT_REPORTED,
                currency="CNY",
                price_base_year=None,
                capacity_denominator="system",
                technology_fit=TechnologyBoundaryFit.SYSTEM_AGGREGATE,
                provenance=CostSourceProvenance.AUTHOR_BOTTOM_UP_OR_NORMALIZED,
                allowed_use=CostEvidenceUse.AGGREGATE_ANCHOR_ONLY,
                note="Aggregate CHP retrofit cost lacks an explicit price base year.",
            ),
            CostEvidenceRecord(
                evidence_id="mctigue2022_ptes",
                source_locator="10.1016/j.enconman.2021.115016",
                venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
                price_base_status=PriceBaseStatus.EXPLICIT,
                currency="USD",
                price_base_year=2020,
                capacity_denominator="component_specific",
                technology_fit=TechnologyBoundaryFit.TOPOLOGY_MISMATCH,
                provenance=CostSourceProvenance.AUTHOR_BOTTOM_UP_OR_NORMALIZED,
                allowed_use=CostEvidenceUse.SENSITIVITY_ONLY,
                note="PTES equipment differs from the dual-use CHP molten-salt retrofit.",
            ),
            CostEvidenceRecord(
                evidence_id="vecchi2023_tmes_method",
                source_locator="10.1016/j.apenergy.2022.120628",
                venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
                price_base_status=PriceBaseStatus.EXPLICIT,
                currency="USD",
                price_base_year=2020,
                capacity_denominator="component_specific",
                technology_fit=TechnologyBoundaryFit.METHODOLOGY_ONLY,
                provenance=CostSourceProvenance.AUTHOR_BOTTOM_UP_OR_NORMALIZED,
                allowed_use=CostEvidenceUse.METHODOLOGY_ONLY,
                note="The CEPCI/FX method is explicit but the TMES boundary differs.",
            ),
            CostEvidenceRecord(
                evidence_id="comello2019_residential_bess",
                source_locator="10.1038/s41467-019-09988-z",
                venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
                price_base_status=PriceBaseStatus.EXPLICIT,
                currency="USD",
                price_base_year=2019,
                capacity_denominator="kW_and_kWh",
                technology_fit=TechnologyBoundaryFit.SCALE_MISMATCH,
                provenance=CostSourceProvenance.AUTHOR_BOTTOM_UP_OR_NORMALIZED,
                allowed_use=CostEvidenceUse.SENSITIVITY_ONLY,
                note="The reported market prices are for small residential systems.",
            ),
            CostEvidenceRecord(
                evidence_id="nrel2022_utility_bess",
                source_locator=(
                    "https://atb.nrel.gov/electricity/2022/"
                    "utility-scale_battery_storage"
                ),
                venue_tier=VenueEvidenceTier.OFFICIAL_ENGINEERING,
                price_base_status=PriceBaseStatus.EXPLICIT,
                currency="USD",
                price_base_year=2020,
                capacity_denominator="kW_DC_and_kWh_DC",
                technology_fit=TechnologyBoundaryFit.DIRECT,
                provenance=CostSourceProvenance.OFFICIAL_BOTTOM_UP,
                allowed_use=CostEvidenceUse.OFFICIAL_ENGINEERING_ANCHOR,
                note="FOM includes augmentation and the source is not an Energy+ paper.",
            ),
            CostEvidenceRecord(
                evidence_id="bahloul2022_table9",
                source_locator="10.1016/j.energy.2022.123229",
                venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
                price_base_status=PriceBaseStatus.AMBIGUOUS,
                currency="USD",
                price_base_year=None,
                capacity_denominator="component_specific",
                technology_fit=TechnologyBoundaryFit.EXCLUDED,
                provenance=CostSourceProvenance.SECONDARY_TRANSCRIPTION,
                allowed_use=CostEvidenceUse.EXCLUDED,
                note="The underlying values and VOM unit fail the provenance audit.",
            ),
            CostEvidenceRecord(
                evidence_id="rahman2021_bess_component_package",
                source_locator="10.1016/j.apenergy.2020.116343",
                venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
                price_base_status=PriceBaseStatus.EXPLICIT,
                currency="USD",
                price_base_year=2019,
                capacity_denominator=(
                    "component_specific_kWh_kW_kW_year_MWh_m2"
                ),
                technology_fit=TechnologyBoundaryFit.DIRECT,
                provenance=(
                    CostSourceProvenance.AUTHOR_BOTTOM_UP_OR_NORMALIZED
                ),
                allowed_use=CostEvidenceUse.FORMAL_CANDIDATE,
                note=(
                    "Applied Energy supplies the peer-reviewed model; the official "
                    "same-author dissertation Chapter 3 expands Tables 3.1-3.6, "
                    "the 2019 USD basis, and inclusion/exclusion boundaries."
                ),
                linked_author_expansion=LinkedAuthorExpansion(
                    source_locator="10.7939/r3-jgnr-b764",
                    relationship="same_author_dissertation_chapter_expansion",
                    crosswalk_note=(
                        "The dissertation states that Chapter 3 was published as "
                        "Rahman et al., Applied Energy 283 (2021) 116343."
                    ),
                ),
            ),
        )
    )
