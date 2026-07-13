"""Evidence disclosure contract for the five molten-salt TES pathways."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from tes_bess_boundary.model import TESFixedSpec


class TESPath(str, Enum):
    """Externally priced physical pathways in the reduced-order TES model."""

    ELECTRIC_LT_TO_HT = "electric_lt_to_ht"
    STEAM_LT_TO_HT = "steam_lt_to_ht"
    STEAM_LT_TO_MT = "steam_lt_to_mt"
    POWER_HT_TO_MT = "power_ht_to_mt"
    HEAT_MT_TO_LT = "heat_mt_to_lt"


class TopologyEvidenceGrade(str, Enum):
    """Strength of evidence for mapping a physical route into the MILP."""

    CORE_DIRECT = "core_direct"
    CORE_REDUCED_ORDER = "core_reduced_order"
    CORE_MODULAR_SYNTHESIS = "core_modular_synthesis"
    PROPOSED_EXTENSION = "proposed_extension"
    BLOCKED = "blocked"


_CAP_BY_PATH = {
    TESPath.ELECTRIC_LT_TO_HT: "electric_charge_input_mw",
    TESPath.STEAM_LT_TO_HT: "steam_to_ht_reference_input_mw",
    TESPath.STEAM_LT_TO_MT: "steam_to_mt_reference_input_mw",
    TESPath.POWER_HT_TO_MT: "electric_output_mw",
    TESPath.HEAT_MT_TO_LT: "heat_output_mw",
}

_CORE_GRADES = {
    TopologyEvidenceGrade.CORE_DIRECT,
    TopologyEvidenceGrade.CORE_REDUCED_ORDER,
    TopologyEvidenceGrade.CORE_MODULAR_SYNTHESIS,
}


@dataclass(frozen=True)
class TESPathEvidence:
    """One disclosed evidence claim for one model pathway."""

    path: TESPath
    grade: TopologyEvidenceGrade
    source_dois: tuple[str, ...]
    claim: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, TESPath):
            raise ValueError("path must be selected with TESPath")
        if not isinstance(self.grade, TopologyEvidenceGrade):
            raise ValueError("grade must be selected with TopologyEvidenceGrade")
        if not isinstance(self.source_dois, tuple) or any(
            not isinstance(doi, str)
            or not doi.strip().lower().startswith("10.")
            for doi in self.source_dois
        ):
            raise ValueError("source_dois must be an immutable DOI tuple")
        if self.grade in _CORE_GRADES and not self.source_dois:
            raise ValueError("core evidence grades require at least one DOI")
        if not isinstance(self.claim, str) or not self.claim.strip():
            raise ValueError("claim must disclose the scope of the evidence")


@dataclass(frozen=True)
class TESTopologyEvidenceAudit:
    """Complete evidence coverage for every active port in one fixed TES spec."""

    tes: TESFixedSpec
    evidence: tuple[TESPathEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.tes, TESFixedSpec):
            raise ValueError("tes must be a TESFixedSpec")
        if not isinstance(self.evidence, tuple) or any(
            not isinstance(item, TESPathEvidence) for item in self.evidence
        ):
            raise ValueError("evidence must be an immutable TES path tuple")
        paths = tuple(item.path for item in self.evidence)
        if len(set(paths)) != len(paths):
            raise ValueError("each TES path may have only one evidence claim")
        if set(paths) != set(self.active_paths):
            raise ValueError("evidence must exactly cover every active TES path")

    @property
    def active_paths(self) -> tuple[TESPath, ...]:
        """Return deterministic paths whose corresponding port cap is positive."""

        return tuple(
            path
            for path in TESPath
            if getattr(self.tes.port_caps, _CAP_BY_PATH[path]) > 0.0
        )

    @property
    def proposed_extensions(self) -> tuple[TESPath, ...]:
        return tuple(
            item.path
            for item in self.evidence
            if item.grade is TopologyEvidenceGrade.PROPOSED_EXTENSION
        )

    @property
    def blocked_paths(self) -> tuple[TESPath, ...]:
        return tuple(
            item.path
            for item in self.evidence
            if item.grade is TopologyEvidenceGrade.BLOCKED
        )

    def certify_formal_use(
        self,
        *,
        disclosed_proposed_extensions: tuple[TESPath, ...] = (),
    ) -> None:
        """Reject blocked routes and undisclosed claims of architectural novelty."""

        if self.blocked_paths:
            names = ", ".join(path.value for path in self.blocked_paths)
            raise ValueError(f"active TES paths remain evidence-blocked: {names}")
        if len(set(disclosed_proposed_extensions)) != len(
            disclosed_proposed_extensions
        ) or any(
            not isinstance(path, TESPath) for path in disclosed_proposed_extensions
        ):
            raise ValueError(
                "disclosed_proposed_extensions must be a unique TESPath tuple"
            )
        if set(disclosed_proposed_extensions) != set(self.proposed_extensions):
            raise ValueError(
                "every proposed TES extension must be explicitly disclosed"
            )


def build_e0d6_reference_topology_audit(
    tes: TESFixedSpec,
) -> TESTopologyEvidenceAudit:
    """Build the current Energy+ evidence map without claiming whole-system precedent."""

    claims = {
        TESPath.ELECTRIC_LT_TO_HT: TESPathEvidence(
            path=TESPath.ELECTRIC_LT_TO_HT,
            grade=TopologyEvidenceGrade.CORE_DIRECT,
            source_dois=(
                "10.1016/j.enconman.2022.116362",
                "10.1016/j.apenergy.2024.124524",
            ),
            claim="Electric heating of molten salt is directly supported; the cited "
            "papers do not validate the complete three-state dual-service system.",
        ),
        TESPath.STEAM_LT_TO_HT: TESPathEvidence(
            path=TESPath.STEAM_LT_TO_HT,
            grade=TopologyEvidenceGrade.CORE_REDUCED_ORDER,
            source_dois=("10.1016/j.energy.2025.135580",),
            claim="The two-stage cold-to-medium-to-hot charging process is represented "
            "as one aggregate cold-to-hot inventory transfer at dispatch resolution.",
        ),
        TESPath.STEAM_LT_TO_MT: TESPathEvidence(
            path=TESPath.STEAM_LT_TO_MT,
            grade=TopologyEvidenceGrade.CORE_DIRECT,
            source_dois=("10.1016/j.energy.2025.135580",),
            claim="The first cold-to-medium charging stage is directly supported by "
            "the Energy three-tank study.",
        ),
        TESPath.POWER_HT_TO_MT: TESPathEvidence(
            path=TESPath.POWER_HT_TO_MT,
            grade=TopologyEvidenceGrade.CORE_MODULAR_SYNTHESIS,
            source_dois=(
                "10.1016/j.energy.2024.133755",
                "10.1016/j.energy.2025.135580",
            ),
            claim="Molten-salt heat release to a turbine and three-state inventory are "
            "supported separately; their exact reduced-order coupling is synthesized.",
        ),
        TESPath.HEAT_MT_TO_LT: TESPathEvidence(
            path=TESPath.HEAT_MT_TO_LT,
            grade=TopologyEvidenceGrade.PROPOSED_EXTENSION,
            source_dois=("10.1016/j.energy.2024.133755",),
            claim="The Energy CHP study supports a useful-heat outlet, but assigning "
            "that service specifically to the medium-to-low salt interval is the "
            "proposed cascade extension and still requires pinch validation.",
        ),
    }
    active = tuple(
        path
        for path in TESPath
        if getattr(tes.port_caps, _CAP_BY_PATH[path]) > 0.0
    )
    return TESTopologyEvidenceAudit(
        tes=tes,
        evidence=tuple(claims[path] for path in active),
    )
