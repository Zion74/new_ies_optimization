"""Formal TES cost readiness gate for the E0 three-temperature topology.

The module intentionally contains no TES price values.  It requires every
incremental cost account to be backed by formal evidence before a system TAC
portfolio can be certified, and it keeps aggregate engineering anchors outside
the component ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from tes_bess_boundary.cost_evidence import (
    CostEvidenceAudit,
    CostEvidenceUse,
    FormalCostEvidenceCertificate,
    TechnologyBoundaryFit,
    build_e0d10_reference_cost_audit,
)


class TESFormalCostAccount(str, Enum):
    """Cost accounts that must be closed before formal system-level TES TAC."""

    SALT_INVENTORY = "salt_inventory"
    STORAGE_VESSELS = "storage_vessels"
    SALT_CIRCULATION = "salt_circulation"
    TRANSFORMER_AND_ELECTRICAL_CONNECTION = (
        "transformer_and_electrical_connection"
    )
    ELECTRIC_HEATER = "electric_heater"
    HIGH_GRADE_STEAM_CHARGE_HX = "high_grade_steam_charge_hx"
    MEDIUM_GRADE_STEAM_CHARGE_HX = "medium_grade_steam_charge_hx"
    SALT_TO_STEAM_GENERATOR = "salt_to_steam_generator"
    HEAT_DELIVERY_HX = "heat_delivery_hx"
    POWER_BLOCK_RETROFIT = "power_block_retrofit"
    PROJECT_ADDITIONS = "project_additions"
    LIFECYCLE_TERMS = "lifecycle_terms"


@dataclass(frozen=True)
class TESFormalEvidenceRequest:
    """One candidate evidence package and the denominator it must certify."""

    evidence_id: str
    expected_capacity_denominator: str

    def __post_init__(self) -> None:
        for field_name in ("evidence_id", "expected_capacity_denominator"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class TESFormalCostRequirement:
    """Candidate set for one non-optional TES cost account."""

    account: TESFormalCostAccount
    candidates: tuple[TESFormalEvidenceRequest, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.account, TESFormalCostAccount):
            raise ValueError("account must be selected with TESFormalCostAccount")
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(candidate, TESFormalEvidenceRequest)
            for candidate in self.candidates
        ):
            raise ValueError("candidates must be an immutable evidence-request tuple")
        keys = tuple(
            (candidate.evidence_id, candidate.expected_capacity_denominator)
            for candidate in self.candidates
        )
        if len(set(keys)) != len(keys):
            raise ValueError("candidate evidence requests must be unique")


@dataclass(frozen=True)
class TESFormalCostAssignment:
    """The unique ready evidence selected for one account."""

    account: TESFormalCostAccount
    request: TESFormalEvidenceRequest

    def __post_init__(self) -> None:
        if not isinstance(self.account, TESFormalCostAccount):
            raise ValueError("account must be selected with TESFormalCostAccount")
        if not isinstance(self.request, TESFormalEvidenceRequest):
            raise ValueError("request must be a TESFormalEvidenceRequest")


@dataclass(frozen=True)
class TESFormalCostPortfolioCertificate:
    """Certificate issued only after all accounts and route policy pass."""

    assignments: tuple[TESFormalCostAssignment, ...]
    evidence_certificates: tuple[FormalCostEvidenceCertificate, ...]
    composite_route_approved: bool

    def __post_init__(self) -> None:
        if not isinstance(self.assignments, tuple) or any(
            not isinstance(item, TESFormalCostAssignment)
            for item in self.assignments
        ):
            raise ValueError("assignments must be an immutable canonical tuple")
        if {item.account for item in self.assignments} != set(TESFormalCostAccount):
            raise ValueError("formal TES assignments must cover every account once")
        if len(self.assignments) != len(TESFormalCostAccount):
            raise ValueError("formal TES assignments must be unique by account")
        if not isinstance(self.evidence_certificates, tuple) or any(
            not isinstance(item, FormalCostEvidenceCertificate)
            for item in self.evidence_certificates
        ):
            raise ValueError(
                "evidence_certificates must be an immutable formal-certificate tuple"
            )
        certified = {
            (
                item.evidence.evidence_id,
                item.certified_capacity_denominator,
            )
            for item in self.evidence_certificates
        }
        requested = {
            (
                item.request.evidence_id,
                item.request.expected_capacity_denominator,
            )
            for item in self.assignments
        }
        if certified != requested:
            raise ValueError("formal TES assignments and evidence certificates differ")
        if not isinstance(self.composite_route_approved, bool):
            raise ValueError("composite_route_approved must be boolean")
        source_locators = {
            item.evidence.source_locator for item in self.evidence_certificates
        }
        if len(source_locators) > 1 and not self.composite_route_approved:
            raise ValueError("multi-source TES evidence requires explicit approval")

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(
            item.evidence.evidence_id for item in self.evidence_certificates
        )


@dataclass(frozen=True)
class TESFormalCostReadinessAudit:
    """Strict gate separating component evidence from aggregate calibration."""

    evidence_audit: CostEvidenceAudit
    requirements: tuple[TESFormalCostRequirement, ...]
    aggregate_anchor_ids: tuple[str, ...]
    composite_route_approved: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_audit, CostEvidenceAudit):
            raise ValueError("evidence_audit must be a CostEvidenceAudit")
        if not isinstance(self.requirements, tuple) or any(
            not isinstance(item, TESFormalCostRequirement)
            for item in self.requirements
        ):
            raise ValueError("requirements must be an immutable canonical tuple")
        accounts = tuple(item.account for item in self.requirements)
        if len(accounts) != len(TESFormalCostAccount) or set(accounts) != set(
            TESFormalCostAccount
        ):
            raise ValueError("requirements must cover each TES cost account once")
        if not isinstance(self.aggregate_anchor_ids, tuple) or any(
            not isinstance(evidence_id, str) or not evidence_id.strip()
            for evidence_id in self.aggregate_anchor_ids
        ):
            raise ValueError("aggregate_anchor_ids must be an immutable string tuple")
        if len(set(self.aggregate_anchor_ids)) != len(self.aggregate_anchor_ids):
            raise ValueError("aggregate_anchor_ids must be unique")
        if not isinstance(self.composite_route_approved, bool):
            raise ValueError("composite_route_approved must be boolean")

        candidate_ids = {
            candidate.evidence_id
            for requirement in self.requirements
            for candidate in requirement.candidates
        }
        if candidate_ids.intersection(self.aggregate_anchor_ids):
            raise ValueError(
                "aggregate calibration anchors cannot satisfy component accounts"
            )
        for evidence_id in candidate_ids:
            self.evidence_audit.get(evidence_id)
        for evidence_id in self.aggregate_anchor_ids:
            record = self.evidence_audit.get(evidence_id)
            if record.allowed_use not in {
                CostEvidenceUse.AGGREGATE_ANCHOR_ONLY,
                CostEvidenceUse.OFFICIAL_ENGINEERING_ANCHOR,
            }:
                raise ValueError(
                    "aggregate anchors must remain aggregate or engineering-only"
                )
            if record.technology_fit is not TechnologyBoundaryFit.SYSTEM_AGGREGATE:
                raise ValueError("aggregate anchors must have a system boundary")

    def requirement(
        self,
        account: TESFormalCostAccount,
    ) -> TESFormalCostRequirement:
        if not isinstance(account, TESFormalCostAccount):
            raise ValueError("account must be selected with TESFormalCostAccount")
        return next(item for item in self.requirements if item.account is account)

    def candidate_blockers(
        self,
        account: TESFormalCostAccount,
    ) -> tuple[tuple[str, tuple[str, ...]], ...]:
        requirement = self.requirement(account)
        return tuple(
            (
                candidate.evidence_id,
                self.evidence_audit.get(candidate.evidence_id).formal_blockers(
                    expected_capacity_denominator=(
                        candidate.expected_capacity_denominator
                    )
                ),
            )
            for candidate in requirement.candidates
        )

    def ready_candidates(
        self,
        account: TESFormalCostAccount,
    ) -> tuple[TESFormalEvidenceRequest, ...]:
        requirement = self.requirement(account)
        return tuple(
            candidate
            for candidate in requirement.candidates
            if not self.evidence_audit.get(candidate.evidence_id).formal_blockers(
                expected_capacity_denominator=(
                    candidate.expected_capacity_denominator
                )
            )
        )

    @property
    def blocked_accounts(self) -> tuple[TESFormalCostAccount, ...]:
        return tuple(
            account
            for account in TESFormalCostAccount
            if not self.ready_candidates(account)
        )

    @property
    def ambiguous_accounts(self) -> tuple[TESFormalCostAccount, ...]:
        return tuple(
            account
            for account in TESFormalCostAccount
            if len(self.ready_candidates(account)) > 1
        )

    def _unique_assignments(self) -> tuple[TESFormalCostAssignment, ...]:
        if self.blocked_accounts:
            names = ", ".join(account.value for account in self.blocked_accounts)
            raise ValueError(f"blocked TES cost accounts: {names}")
        if self.ambiguous_accounts:
            names = ", ".join(account.value for account in self.ambiguous_accounts)
            raise ValueError(f"ambiguous TES cost accounts: {names}")
        return tuple(
            TESFormalCostAssignment(
                account=account,
                request=self.ready_candidates(account)[0],
            )
            for account in TESFormalCostAccount
        )

    @property
    def formal_portfolio_ready(self) -> bool:
        try:
            assignments = self._unique_assignments()
        except ValueError:
            return False
        source_locators = {
            self.evidence_audit.get(item.request.evidence_id).source_locator
            for item in assignments
        }
        return len(source_locators) <= 1 or self.composite_route_approved

    def certify(self) -> TESFormalCostPortfolioCertificate:
        assignments = self._unique_assignments()
        source_locators = {
            self.evidence_audit.get(item.request.evidence_id).source_locator
            for item in assignments
        }
        if len(source_locators) > 1 and not self.composite_route_approved:
            raise ValueError(
                "multi-source TES evidence requires explicit composite-route approval"
            )

        certificates: list[FormalCostEvidenceCertificate] = []
        seen: set[tuple[str, str]] = set()
        for assignment in assignments:
            request = assignment.request
            key = (request.evidence_id, request.expected_capacity_denominator)
            if key in seen:
                continue
            seen.add(key)
            certificates.append(
                self.evidence_audit.get(request.evidence_id).certify_formal_baseline(
                    expected_capacity_denominator=(
                        request.expected_capacity_denominator
                    )
                )
            )
        return TESFormalCostPortfolioCertificate(
            assignments=assignments,
            evidence_certificates=tuple(certificates),
            composite_route_approved=self.composite_route_approved,
        )


def _request(evidence_id: str, denominator: str) -> TESFormalEvidenceRequest:
    return TESFormalEvidenceRequest(evidence_id, denominator)


def build_e0d15_tes_formal_cost_readiness(
    evidence_audit: CostEvidenceAudit | None = None,
    *,
    composite_route_approved: bool = False,
) -> TESFormalCostReadinessAudit:
    """Build the current strict-route audit without inventing TES price values."""

    audit = evidence_audit or build_e0d10_reference_cost_audit()
    if not isinstance(audit, CostEvidenceAudit):
        raise ValueError("evidence_audit must be a CostEvidenceAudit")

    trevisan = _request("trevisan2022_tes_components", "component_specific")
    klasing = _request("klasing2025_tes_components", "component_specific")
    guccione_2023 = _request(
        "guccione2023_electric_heater_quote",
        "kW_el",
    )
    guccione_2024 = _request(
        "guccione2024_electric_heater_quote",
        "kW_el",
    )
    requirements = (
        TESFormalCostRequirement(
            TESFormalCostAccount.SALT_INVENTORY,
            (_request("wang2025_hitec_salt", "kg_salt"),),
        ),
        TESFormalCostRequirement(
            TESFormalCostAccount.STORAGE_VESSELS,
            (trevisan, klasing),
        ),
        TESFormalCostRequirement(
            TESFormalCostAccount.SALT_CIRCULATION,
            (trevisan, klasing),
        ),
        TESFormalCostRequirement(
            TESFormalCostAccount.TRANSFORMER_AND_ELECTRICAL_CONNECTION,
            (trevisan,),
        ),
        TESFormalCostRequirement(
            TESFormalCostAccount.ELECTRIC_HEATER,
            (guccione_2023, guccione_2024, trevisan, klasing),
        ),
        TESFormalCostRequirement(
            TESFormalCostAccount.HIGH_GRADE_STEAM_CHARGE_HX,
            (),
        ),
        TESFormalCostRequirement(
            TESFormalCostAccount.MEDIUM_GRADE_STEAM_CHARGE_HX,
            (),
        ),
        TESFormalCostRequirement(
            TESFormalCostAccount.SALT_TO_STEAM_GENERATOR,
            (trevisan, klasing),
        ),
        TESFormalCostRequirement(
            TESFormalCostAccount.HEAT_DELIVERY_HX,
            (),
        ),
        TESFormalCostRequirement(
            TESFormalCostAccount.POWER_BLOCK_RETROFIT,
            (),
        ),
        TESFormalCostRequirement(
            TESFormalCostAccount.PROJECT_ADDITIONS,
            (trevisan, klasing),
        ),
        TESFormalCostRequirement(
            TESFormalCostAccount.LIFECYCLE_TERMS,
            (trevisan, klasing),
        ),
    )
    return TESFormalCostReadinessAudit(
        evidence_audit=audit,
        requirements=requirements,
        aggregate_anchor_ids=(
            "klasing2025_system_anchor",
            "li2026_tes_retrofit",
            "dlr2021_csp_tes_aggregate",
        ),
        composite_route_approved=composite_route_approved,
    )
