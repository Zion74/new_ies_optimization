from __future__ import annotations

from dataclasses import replace

import pytest


def _eligible_record(evidence_id: str, source_locator: str):
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
        source_locator=source_locator,
        venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
        price_base_status=PriceBaseStatus.EXPLICIT,
        currency="EUR",
        price_base_year=2023,
        capacity_denominator="component_specific",
        technology_fit=TechnologyBoundaryFit.DIRECT,
        provenance=CostSourceProvenance.AUTHOR_BOTTOM_UP_OR_NORMALIZED,
        allowed_use=CostEvidenceUse.FORMAL_CANDIDATE,
        note="Synthetic formal TES package used only for gate tests.",
    )


def _uniform_requirements(evidence_ids: tuple[str, ...]):
    from tes_bess_boundary.formal_tes_costs import (
        TESFormalCostAccount,
        TESFormalCostRequirement,
        TESFormalEvidenceRequest,
    )

    return tuple(
        TESFormalCostRequirement(
            account,
            (
                TESFormalEvidenceRequest(
                    evidence_ids[index % len(evidence_ids)],
                    "component_specific",
                ),
            ),
        )
        for index, account in enumerate(TESFormalCostAccount)
    )


def test_current_e0d15_tes_cost_route_is_explicitly_blocked() -> None:
    from tes_bess_boundary.formal_tes_costs import (
        TESFormalCostAccount,
        build_e0d15_tes_formal_cost_readiness,
    )

    readiness = build_e0d15_tes_formal_cost_readiness()

    assert readiness.formal_portfolio_ready is False
    assert readiness.blocked_accounts == tuple(TESFormalCostAccount)
    assert readiness.ambiguous_accounts == ()
    assert readiness.aggregate_anchor_ids == (
        "klasing2025_system_anchor",
        "li2026_tes_retrofit",
        "dlr2021_csp_tes_aggregate",
    )
    electric_heater = dict(
        readiness.candidate_blockers(TESFormalCostAccount.ELECTRIC_HEATER)
    )
    assert electric_heater["guccione2023_electric_heater_quote"] == (
        "allowed_use",
        "price_base",
    )
    assert electric_heater["trevisan2022_tes_components"] == (
        "allowed_use",
        "price_base",
        "source_provenance",
    )
    assert readiness.candidate_blockers(
        TESFormalCostAccount.HIGH_GRADE_STEAM_CHARGE_HX
    ) == ()

    with pytest.raises(ValueError, match="blocked TES cost accounts"):
        readiness.certify()


def test_aggregate_engineering_anchor_cannot_enter_component_candidates() -> None:
    from tes_bess_boundary.formal_tes_costs import (
        TESFormalCostAccount,
        TESFormalCostReadinessAudit,
        TESFormalCostRequirement,
        TESFormalEvidenceRequest,
        build_e0d15_tes_formal_cost_readiness,
    )

    current = build_e0d15_tes_formal_cost_readiness()
    requirements = tuple(
        TESFormalCostRequirement(
            item.account,
            (
                TESFormalEvidenceRequest(
                    "dlr2021_csp_tes_aggregate",
                    "kWh_th_net",
                ),
            )
            if item.account is TESFormalCostAccount.STORAGE_VESSELS
            else item.candidates,
        )
        for item in current.requirements
    )

    with pytest.raises(ValueError, match="cannot satisfy component accounts"):
        TESFormalCostReadinessAudit(
            evidence_audit=current.evidence_audit,
            requirements=requirements,
            aggregate_anchor_ids=current.aggregate_anchor_ids,
        )


def test_single_source_formal_package_can_cover_all_accounts_once() -> None:
    from tes_bess_boundary.cost_evidence import CostEvidenceAudit
    from tes_bess_boundary.formal_tes_costs import TESFormalCostReadinessAudit

    evidence = _eligible_record(
        "formal_tes_package",
        "10.1016/j.apenergy.2026.000001",
    )
    readiness = TESFormalCostReadinessAudit(
        evidence_audit=CostEvidenceAudit((evidence,)),
        requirements=_uniform_requirements((evidence.evidence_id,)),
        aggregate_anchor_ids=(),
    )

    assert readiness.formal_portfolio_ready is True
    certificate = readiness.certify()
    assert certificate.evidence_ids == ("formal_tes_package",)
    assert len(certificate.assignments) == 12
    assert certificate.composite_route_approved is False


def test_multi_source_formal_package_requires_separate_route_approval() -> None:
    from tes_bess_boundary.cost_evidence import CostEvidenceAudit
    from tes_bess_boundary.formal_tes_costs import TESFormalCostReadinessAudit

    first = _eligible_record(
        "formal_tes_first",
        "10.1016/j.apenergy.2026.000001",
    )
    second = replace(
        _eligible_record(
            "formal_tes_second",
            "10.1016/j.energy.2026.000002",
        ),
        currency="USD",
        price_base_year=2020,
    )
    audit = CostEvidenceAudit((first, second))
    requirements = _uniform_requirements(
        (first.evidence_id, second.evidence_id)
    )

    blocked = TESFormalCostReadinessAudit(
        evidence_audit=audit,
        requirements=requirements,
        aggregate_anchor_ids=(),
    )
    assert blocked.formal_portfolio_ready is False
    with pytest.raises(ValueError, match="composite-route approval"):
        blocked.certify()

    approved = replace(blocked, composite_route_approved=True)
    assert approved.formal_portfolio_ready is True
    certificate = approved.certify()
    assert certificate.evidence_ids == (
        "formal_tes_first",
        "formal_tes_second",
    )
    assert certificate.composite_route_approved is True
