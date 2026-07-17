from __future__ import annotations

import json

import pytest


def test_e0d24_covers_all_tes_and_operating_accounts_once() -> None:
    from tes_bess_boundary.formal_tac_evidence_route import (
        EvidenceRouteStatus,
        TACAccountFamily,
        build_e0d24_formal_tac_evidence_route_audit,
    )
    from tes_bess_boundary.formal_tes_costs import TESFormalCostAccount
    from tes_bess_boundary.operating_cost_evidence import OperatingCostAccount

    audit = build_e0d24_formal_tac_evidence_route_audit()

    assert len(audit.account_routes) == 16
    assert len({(row.family, row.account) for row in audit.account_routes}) == 16
    assert {
        row.account
        for row in audit.account_routes
        if row.family is TACAccountFamily.TES_OWNERSHIP
    } == {account.value for account in TESFormalCostAccount}
    assert {
        row.account
        for row in audit.account_routes
        if row.family is TACAccountFamily.NONFUEL_OPERATING
    } == {account.value for account in OperatingCostAccount}
    assert audit.strict_formal_account_count == 0
    assert audit.formal_tac_ready is False
    assert audit.e1_ready is False
    assert all(
        row.status is EvidenceRouteStatus.PROJECT_PRIMARY_REQUIRED
        for row in audit.account_routes
        if row.family is TACAccountFamily.NONFUEL_OPERATING
    )


def test_d24_preserves_missing_direct_tes_candidates() -> None:
    from tes_bess_boundary.formal_tac_evidence_route import (
        EvidenceRouteStatus,
        TACAccountFamily,
        build_e0d24_formal_tac_evidence_route_audit,
    )

    audit = build_e0d24_formal_tac_evidence_route_audit()
    missing = {
        row.account
        for row in audit.account_routes
        if row.family is TACAccountFamily.TES_OWNERSHIP
        and row.status is EvidenceRouteStatus.NO_DIRECT_CANDIDATE
    }

    assert missing == {
        "high_grade_steam_charge_hx",
        "medium_grade_steam_charge_hx",
        "heat_delivery_hx",
        "power_block_retrofit",
    }


def test_energy_venue_metric_does_not_launder_aggregate_cost_evidence() -> None:
    from tes_bess_boundary.formal_tac_evidence_route import (
        PublicEvidenceLayer,
        PublicEvidenceUse,
        build_e0d24_formal_tac_evidence_route_audit,
    )

    audit = build_e0d24_formal_tac_evidence_route_audit()
    source = audit.public_source("zhang2024_energy_coal_tes_retrofit")

    assert source.layer is PublicEvidenceLayer.ENERGY_PLUS_PEER_REVIEWED
    assert source.venue == "Energy"
    assert source.publisher_metric_name == "Impact Factor"
    assert source.publisher_metric_value == pytest.approx(9.4)
    assert source.allowed_use is PublicEvidenceUse.AGGREGATE_TECHNOLOGY_ANCHOR
    assert source.component_account_eligible is False
    assert "allowed_use" in source.formal_component_blockers()
    assert "price_base" in source.formal_component_blockers()
    assert "component_boundary" in source.formal_component_blockers()


def test_official_engineering_reports_remain_separate_evidence_layer() -> None:
    from tes_bess_boundary.formal_tac_evidence_route import (
        PublicEvidenceLayer,
        build_e0d24_formal_tac_evidence_route_audit,
    )

    audit = build_e0d24_formal_tac_evidence_route_audit()
    official = tuple(
        source
        for source in audit.public_sources
        if source.layer is PublicEvidenceLayer.OFFICIAL_ENGINEERING
    )

    assert {source.source_id for source in official} == {
        "dlr2021_two_tank_solar_salt_aggregate",
        "nrel2011_tes_cost_methodology",
        "nrel2013_molten_salt_component_cost_model",
        "doe2016_molten_salt_capital_cost_estimate",
    }
    assert all(source.component_account_eligible is False for source in official)
    assert all("venue_gate" in source.formal_component_blockers() for source in official)


def test_layered_route_approval_alone_cannot_create_missing_evidence() -> None:
    from tes_bess_boundary.formal_tac_evidence_route import (
        build_e0d24_formal_tac_evidence_route_audit,
    )

    strict = build_e0d24_formal_tac_evidence_route_audit()
    approved = build_e0d24_formal_tac_evidence_route_audit(
        layered_route_approved=True
    )

    assert strict.layered_route_approved is False
    assert approved.layered_route_approved is True
    assert approved.strict_formal_account_count == 0
    assert approved.formal_tac_ready is False
    with pytest.raises(ValueError, match="formal TAC evidence is blocked"):
        approved.certify()


def test_d24_export_is_deterministic_and_records_prohibitions(tmp_path) -> None:
    from tes_bess_boundary.formal_tac_evidence_route import (
        E0D24_SCHEMA,
        build_e0d24_formal_tac_evidence_route_audit,
        write_e0d24_formal_tac_evidence_route,
    )

    audit = build_e0d24_formal_tac_evidence_route_audit()
    first = write_e0d24_formal_tac_evidence_route(audit, tmp_path / "first")
    second = write_e0d24_formal_tac_evidence_route(audit, tmp_path / "second")

    assert first.account_routes_sha256 == second.account_routes_sha256
    assert first.public_sources_sha256 == second.public_sources_sha256
    assert first.manifest_sha256 == second.manifest_sha256
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == E0D24_SCHEMA
    assert manifest["account_count"] == 16
    assert manifest["strict_formal_account_count"] == 0
    assert manifest["project_primary_required_count"] == 4
    assert manifest["layered_route_approved"] is False
    assert manifest["formal_tac_ready"] is False
    assert manifest["e1_ready"] is False
    assert manifest["prohibitions"] == [
        "no_public_source_substitution_for_project_primary_accounts",
        "no_venue_laundering_of_official_engineering_values",
        "no_aggregate_anchor_allocation_to_component_accounts",
        "no_formal_tac_or_technology_winner_claim",
    ]
