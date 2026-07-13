from __future__ import annotations

import pytest


def _eligible_record(evidence_id: str = "formal_tank_cost"):
    from tes_bess_boundary.cost_evidence import (
        CostEvidenceRecord,
        CostEvidenceUse,
        CostSourceProvenance,
        PriceBaseStatus,
        TechnologyBoundaryFit,
        VenueEvidenceTier,
    )

    return CostEvidenceRecord(
        evidence_id=evidence_id,
        source_locator="10.1016/j.apenergy.2026.000001",
        venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
        price_base_status=PriceBaseStatus.EXPLICIT,
        currency="EUR",
        price_base_year=2023,
        capacity_denominator="kWh_th",
        technology_fit=TechnologyBoundaryFit.DIRECT,
        provenance=CostSourceProvenance.AUTHOR_BOTTOM_UP_OR_NORMALIZED,
        allowed_use=CostEvidenceUse.FORMAL_CANDIDATE,
        note="Synthetic gold standard used only to test the evidence gate.",
    )


def test_e0d10_reference_audit_promotes_only_the_approved_linked_package() -> None:
    from tes_bess_boundary.cost_evidence import build_e0d10_reference_cost_audit

    audit = build_e0d10_reference_cost_audit()

    assert len(audit.records) == 12
    assert audit.formal_candidate_ids == (
        "rahman2021_bess_component_package",
    )
    assert audit.get("schmidt2019_bess_capex").formal_blockers() == (
        "allowed_use",
        "price_base",
        "source_provenance",
    )
    assert audit.get("nrel2022_utility_bess").formal_blockers() == (
        "venue_tier",
        "allowed_use",
        "source_provenance",
    )
    assert audit.get("vecchi2023_tmes_method").formal_blockers() == (
        "allowed_use",
        "technology_boundary",
    )

    with pytest.raises(ValueError, match="price_base"):
        audit.get("trevisan2022_tes_components").certify_formal_baseline(
            expected_capacity_denominator="component_specific"
        )
    with pytest.raises(ValueError, match="venue_tier"):
        audit.get("nrel2022_utility_bess").certify_formal_baseline(
            expected_capacity_denominator="kW_DC_and_kWh_DC"
        )

    rahman = audit.get("rahman2021_bess_component_package")
    certificate = rahman.certify_formal_baseline(
        expected_capacity_denominator=(
            "component_specific_kWh_kW_kW_year_MWh_m2"
        )
    )
    assert certificate.evidence.linked_author_expansion is not None
    assert (
        certificate.evidence.linked_author_expansion.source_locator
        == "10.7939/r3-jgnr-b764"
    )


def test_formal_certificate_requires_exact_capacity_denominator() -> None:
    record = _eligible_record()

    certificate = record.certify_formal_baseline(expected_capacity_denominator="kWh_th")
    assert certificate.evidence is record
    assert certificate.certified_capacity_denominator == "kWh_th"

    with pytest.raises(ValueError, match="capacity_denominator"):
        record.certify_formal_baseline(expected_capacity_denominator="kW_th")


def test_formal_portfolio_requires_unique_canonical_evidence() -> None:
    from tes_bess_boundary.cost_evidence import CostEvidenceAudit

    first = _eligible_record("tank_cost")
    second = _eligible_record("salt_cost")
    audit = CostEvidenceAudit((first, second))

    certificates = audit.certify_formal_portfolio(
        (("tank_cost", "kWh_th"), ("salt_cost", "kWh_th"))
    )
    assert tuple(item.evidence.evidence_id for item in certificates) == (
        "tank_cost",
        "salt_cost",
    )

    with pytest.raises(ValueError, match="must be unique"):
        CostEvidenceAudit((first, first))
    with pytest.raises(ValueError, match="must be unique"):
        audit.certify_formal_portfolio(
            (("tank_cost", "kWh_th"), ("tank_cost", "kWh_th"))
        )
    with pytest.raises(KeyError):
        audit.certify_formal_portfolio((("missing", "kWh_th"),))


def test_price_basis_and_source_invariants_are_strict() -> None:
    from dataclasses import replace

    from tes_bess_boundary.cost_evidence import (
        PriceBaseStatus,
        VenueEvidenceTier,
    )

    record = _eligible_record()

    with pytest.raises(ValueError, match="requires a DOI"):
        replace(record, source_locator="https://example.test/report")
    with pytest.raises(ValueError, match="currency"):
        replace(record, currency="$")
    with pytest.raises(ValueError, match="requires currency"):
        replace(record, currency=None)
    with pytest.raises(ValueError, match="cannot claim"):
        replace(
            record,
            price_base_status=PriceBaseStatus.AMBIGUOUS,
            price_base_year=2023,
        )

    official = replace(
        record,
        venue_tier=VenueEvidenceTier.OFFICIAL_ENGINEERING,
        source_locator="https://example.test/report",
    )
    assert official.source_locator.startswith("https://")


def test_linked_author_expansion_requires_an_official_locator() -> None:
    from tes_bess_boundary.cost_evidence import LinkedAuthorExpansion

    with pytest.raises(ValueError, match="DOI or HTTPS"):
        LinkedAuthorExpansion(
            source_locator="private-note.pdf",
            relationship="same_author_expansion",
            crosswalk_note="Synthetic invalid locator.",
        )
