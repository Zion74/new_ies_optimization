from __future__ import annotations

from dataclasses import replace

import pytest


def _tes_spec():
    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
    )
    from tes_bess_boundary.model import TESFixedSpec, TESPortCaps

    return TESFixedSpec(
        physics=MoltenSaltPhysics(
            salt_mass_t=10.0,
            ht_tank_capacity_t=10.0,
            mt_tank_capacity_t=10.0,
            lt_tank_capacity_t=10.0,
            specific_heat_mwh_per_tonne_k=0.0004,
            temperature_ht=390.0,
            temperature_mt=280.0,
            temperature_lt=180.0,
            electric_heater_efficiency=0.98,
            steam_to_ht_efficiency=0.95,
            steam_to_mt_efficiency=0.95,
            power_block_efficiency=0.4,
            heat_exchanger_efficiency=0.95,
        ),
        initial_inventory=SaltInventory(0.0, 0.0, 10.0),
        port_caps=TESPortCaps(3.0, 4.0, 5.0, 6.0, 7.0),
    )


def test_reference_audit_covers_all_active_paths_and_discloses_novelty() -> None:
    from tes_bess_boundary.tes_topology_evidence import (
        TESPath,
        TopologyEvidenceGrade,
        build_e0d6_reference_topology_audit,
    )

    audit = build_e0d6_reference_topology_audit(_tes_spec())

    assert audit.active_paths == tuple(TESPath)
    assert {item.grade for item in audit.evidence} >= {
        TopologyEvidenceGrade.CORE_DIRECT,
        TopologyEvidenceGrade.CORE_REDUCED_ORDER,
        TopologyEvidenceGrade.CORE_MODULAR_SYNTHESIS,
        TopologyEvidenceGrade.PROPOSED_EXTENSION,
    }
    assert audit.proposed_extensions == (TESPath.HEAT_MT_TO_LT,)
    assert audit.blocked_paths == ()

    with pytest.raises(ValueError, match="explicitly disclosed"):
        audit.certify_formal_use()
    audit.certify_formal_use(
        disclosed_proposed_extensions=(TESPath.HEAT_MT_TO_LT,)
    )


def test_reference_audit_omits_disabled_paths_instead_of_claiming_evidence() -> None:
    from tes_bess_boundary.model import TESPortCaps
    from tes_bess_boundary.tes_topology_evidence import (
        TESPath,
        build_e0d6_reference_topology_audit,
    )

    tes = _tes_spec()
    tes = replace(
        tes,
        port_caps=TESPortCaps(0.0, 0.0, 5.0, 0.0, 7.0),
    )

    audit = build_e0d6_reference_topology_audit(tes)

    assert audit.active_paths == (
        TESPath.STEAM_LT_TO_MT,
        TESPath.HEAT_MT_TO_LT,
    )
    assert tuple(item.path for item in audit.evidence) == audit.active_paths


def test_audit_rejects_missing_duplicate_and_blocked_active_routes() -> None:
    from tes_bess_boundary.tes_topology_evidence import (
        TESPath,
        TESPathEvidence,
        TESTopologyEvidenceAudit,
        TopologyEvidenceGrade,
        build_e0d6_reference_topology_audit,
    )

    tes = _tes_spec()
    reference = build_e0d6_reference_topology_audit(tes)

    with pytest.raises(ValueError, match="exactly cover"):
        TESTopologyEvidenceAudit(tes, reference.evidence[:-1])
    with pytest.raises(ValueError, match="only one"):
        TESTopologyEvidenceAudit(
            tes,
            reference.evidence + (reference.evidence[0],),
        )

    blocked = TESPathEvidence(
        path=TESPath.HEAT_MT_TO_LT,
        grade=TopologyEvidenceGrade.BLOCKED,
        source_dois=(),
        claim="The medium-temperature outlet has not been validated.",
    )
    evidence = tuple(
        blocked if item.path is TESPath.HEAT_MT_TO_LT else item
        for item in reference.evidence
    )
    audit = TESTopologyEvidenceAudit(tes, evidence)
    with pytest.raises(ValueError, match="evidence-blocked"):
        audit.certify_formal_use()


def test_core_grade_requires_a_doi_and_claim() -> None:
    from tes_bess_boundary.tes_topology_evidence import (
        TESPath,
        TESPathEvidence,
        TopologyEvidenceGrade,
    )

    with pytest.raises(ValueError, match="at least one DOI"):
        TESPathEvidence(
            TESPath.ELECTRIC_LT_TO_HT,
            TopologyEvidenceGrade.CORE_DIRECT,
            (),
            "Direct route.",
        )
    with pytest.raises(ValueError, match="scope"):
        TESPathEvidence(
            TESPath.ELECTRIC_LT_TO_HT,
            TopologyEvidenceGrade.CORE_DIRECT,
            ("10.1016/j.energy.2025.135580",),
            "",
        )
