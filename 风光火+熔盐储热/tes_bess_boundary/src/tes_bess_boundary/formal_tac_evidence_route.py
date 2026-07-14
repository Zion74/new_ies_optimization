"""E0-D-24 evidence-route audit for a complete formal TAC.

This module joins the twelve TES ownership accounts from E0-D-15 with the
four project-specific non-fuel operating accounts from E0-D-20.  It does not
invent prices.  Its purpose is to keep three evidence layers separate:

* Energy-or-higher peer-reviewed evidence for technology boundaries;
* official engineering reports for price/method calibration; and
* Yangling primary records for project-specific operating accounts.

Neither a high journal metric nor an official engineering estimate can bypass
the missing price basis, component boundary, topology, or project-ledger gates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from tes_bess_boundary.formal_tes_costs import (
    TESFormalCostAccount,
    TESFormalCostReadinessAudit,
    build_e0d15_tes_formal_cost_readiness,
)
from tes_bess_boundary.operating_cost_evidence import (
    OperatingCostAccount,
    OperatingCostEvidenceAudit,
    build_e0d20_operating_cost_evidence_audit,
)


E0D24_SCHEMA = "tes_bess_boundary.e0d24_formal_tac_evidence_route.v1"


class TACAccountFamily(str, Enum):
    """The two ledgers that jointly block complete system TAC."""

    TES_OWNERSHIP = "tes_ownership"
    NONFUEL_OPERATING = "nonfuel_operating"


class EvidenceRouteStatus(str, Enum):
    """Current evidence outcome for one non-optional TAC account."""

    STRICT_FORMAL_READY = "strict_formal_ready"
    DIRECT_CANDIDATE_INCOMPLETE = "direct_candidate_incomplete"
    NO_DIRECT_CANDIDATE = "no_direct_candidate"
    PROJECT_PRIMARY_REQUIRED = "project_primary_required"


class PublicEvidenceLayer(str, Enum):
    """Authority layer, deliberately independent from allowed use."""

    ENERGY_PLUS_PEER_REVIEWED = "energy_plus_peer_reviewed"
    OFFICIAL_ENGINEERING = "official_engineering"


class PublicEvidenceUse(str, Enum):
    """Permitted role of a public source in the D24 contract."""

    FORMAL_COMPONENT_CANDIDATE = "formal_component_candidate"
    AGGREGATE_TECHNOLOGY_ANCHOR = "aggregate_technology_anchor"
    COMPONENT_ENGINEERING_ANCHOR = "component_engineering_anchor"
    METHODOLOGY_ONLY = "methodology_only"


def _require_non_empty_string(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class PublicEvidenceRecord:
    """One public source with venue, price, and boundary fields kept separate."""

    source_id: str
    title: str
    source_locator: str
    layer: PublicEvidenceLayer
    allowed_use: PublicEvidenceUse
    venue: str
    publisher_metric_name: str
    publisher_metric_value: float | None
    metric_snapshot_date: str
    price_basis_explicit: bool
    capacity_denominator_explicit: bool
    technology_boundary_direct: bool
    component_account_eligible: bool
    note: str

    def __post_init__(self) -> None:
        for field_name in ("source_id", "title", "source_locator", "note"):
            _require_non_empty_string(getattr(self, field_name), field_name)
        if not isinstance(self.layer, PublicEvidenceLayer):
            raise ValueError("layer must be selected with PublicEvidenceLayer")
        if not isinstance(self.allowed_use, PublicEvidenceUse):
            raise ValueError("allowed_use must be selected with PublicEvidenceUse")
        for field_name in (
            "venue",
            "publisher_metric_name",
            "metric_snapshot_date",
        ):
            if not isinstance(getattr(self, field_name), str):
                raise ValueError(f"{field_name} must be a string")
        if self.publisher_metric_value is not None:
            value = self.publisher_metric_value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("publisher_metric_value must be numeric or None")
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(
                    "publisher_metric_value must be finite and positive"
                )
            if not self.publisher_metric_name.strip():
                raise ValueError("a publisher metric value requires a metric name")
            if not self.metric_snapshot_date.strip():
                raise ValueError("a publisher metric value requires a snapshot date")
        for field_name in (
            "price_basis_explicit",
            "capacity_denominator_explicit",
            "technology_boundary_direct",
            "component_account_eligible",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be boolean")

    def formal_component_blockers(self) -> tuple[str, ...]:
        """Return why this record cannot satisfy a strict component account."""

        blockers: list[str] = []
        if self.allowed_use is not PublicEvidenceUse.FORMAL_COMPONENT_CANDIDATE:
            blockers.append("allowed_use")
        if self.layer is not PublicEvidenceLayer.ENERGY_PLUS_PEER_REVIEWED:
            blockers.append("venue_gate")
        if not self.price_basis_explicit:
            blockers.append("price_base")
        if not self.capacity_denominator_explicit:
            blockers.append("capacity_denominator")
        if not self.technology_boundary_direct:
            blockers.append("technology_boundary")
        if not self.component_account_eligible:
            blockers.append("component_boundary")
        return tuple(blockers)


@dataclass(frozen=True)
class TACAccountEvidenceRoute:
    """Machine-readable route status for one required TAC account."""

    family: TACAccountFamily
    account: str
    status: EvidenceRouteStatus
    strict_candidate_blockers: tuple[tuple[str, tuple[str, ...]], ...]
    project_primary_required: bool
    required_next_evidence: str

    def __post_init__(self) -> None:
        if not isinstance(self.family, TACAccountFamily):
            raise ValueError("family must be selected with TACAccountFamily")
        _require_non_empty_string(self.account, "account")
        if not isinstance(self.status, EvidenceRouteStatus):
            raise ValueError("status must be selected with EvidenceRouteStatus")
        if not isinstance(self.strict_candidate_blockers, tuple):
            raise ValueError("strict_candidate_blockers must be an immutable tuple")
        for item in self.strict_candidate_blockers:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("candidate blocker records must be two-item tuples")
            evidence_id, blockers = item
            _require_non_empty_string(evidence_id, "evidence_id")
            if not isinstance(blockers, tuple) or any(
                not isinstance(blocker, str) or not blocker.strip()
                for blocker in blockers
            ):
                raise ValueError("candidate blockers must be an immutable string tuple")
        candidate_ids = tuple(item[0] for item in self.strict_candidate_blockers)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("strict candidate evidence IDs must be unique")
        if not isinstance(self.project_primary_required, bool):
            raise ValueError("project_primary_required must be boolean")
        _require_non_empty_string(
            self.required_next_evidence,
            "required_next_evidence",
        )
        if (
            self.status is EvidenceRouteStatus.PROJECT_PRIMARY_REQUIRED
            and not self.project_primary_required
        ):
            raise ValueError("project-primary status requires project primary evidence")

    @property
    def strict_candidate_ids(self) -> tuple[str, ...]:
        return tuple(item[0] for item in self.strict_candidate_blockers)

    @property
    def strict_formal_ready(self) -> bool:
        return self.status is EvidenceRouteStatus.STRICT_FORMAL_READY


@dataclass(frozen=True)
class FormalTACEvidenceRouteCertificate:
    """A narrow certificate proving only that every evidence account is ready."""

    account_routes: tuple[TACAccountEvidenceRoute, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.account_routes, tuple) or len(
            self.account_routes
        ) != len(TESFormalCostAccount) + len(OperatingCostAccount):
            raise ValueError("formal TAC certificate must cover all sixteen accounts")
        if any(not row.strict_formal_ready for row in self.account_routes):
            raise ValueError("formal TAC certificate contains blocked accounts")


@dataclass(frozen=True)
class FormalTACEvidenceRouteAudit:
    """Joined D15/D20 gate plus non-laundering audit of public sources."""

    tes_readiness: TESFormalCostReadinessAudit
    operating_readiness: OperatingCostEvidenceAudit
    account_routes: tuple[TACAccountEvidenceRoute, ...]
    public_sources: tuple[PublicEvidenceRecord, ...]
    layered_route_approved: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.tes_readiness, TESFormalCostReadinessAudit):
            raise ValueError("tes_readiness must be a TESFormalCostReadinessAudit")
        if not isinstance(self.operating_readiness, OperatingCostEvidenceAudit):
            raise ValueError("operating_readiness must be an OperatingCostEvidenceAudit")
        if not isinstance(self.account_routes, tuple) or any(
            not isinstance(row, TACAccountEvidenceRoute)
            for row in self.account_routes
        ):
            raise ValueError("account_routes must be an immutable canonical tuple")
        expected = {
            *(
                (TACAccountFamily.TES_OWNERSHIP, account.value)
                for account in TESFormalCostAccount
            ),
            *(
                (TACAccountFamily.NONFUEL_OPERATING, account.value)
                for account in OperatingCostAccount
            ),
        }
        actual = {(row.family, row.account) for row in self.account_routes}
        if actual != expected or len(self.account_routes) != len(expected):
            raise ValueError("account_routes must cover all sixteen accounts once")
        if not isinstance(self.public_sources, tuple) or any(
            not isinstance(source, PublicEvidenceRecord)
            for source in self.public_sources
        ):
            raise ValueError("public_sources must be an immutable canonical tuple")
        source_ids = tuple(source.source_id for source in self.public_sources)
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("public source IDs must be unique")
        if not isinstance(self.layered_route_approved, bool):
            raise ValueError("layered_route_approved must be boolean")

    def public_source(self, source_id: str) -> PublicEvidenceRecord:
        _require_non_empty_string(source_id, "source_id")
        try:
            return next(
                source for source in self.public_sources if source.source_id == source_id
            )
        except StopIteration as exc:
            raise KeyError(f"unknown D24 public source: {source_id}") from exc

    @property
    def strict_formal_account_count(self) -> int:
        return sum(row.strict_formal_ready for row in self.account_routes)

    @property
    def project_primary_required_count(self) -> int:
        return sum(row.project_primary_required for row in self.account_routes)

    @property
    def formal_tac_ready(self) -> bool:
        return (
            self.tes_readiness.formal_portfolio_ready
            and self.operating_readiness.formal_portfolio_ready
            and self.strict_formal_account_count == len(self.account_routes)
        )

    @property
    def e1_ready(self) -> bool:
        return self.formal_tac_ready

    def certify(self) -> FormalTACEvidenceRouteCertificate:
        if not self.formal_tac_ready:
            blocked = ", ".join(
                f"{row.family.value}:{row.account}"
                for row in self.account_routes
                if not row.strict_formal_ready
            )
            raise ValueError(f"formal TAC evidence is blocked: {blocked}")
        return FormalTACEvidenceRouteCertificate(self.account_routes)


@dataclass(frozen=True)
class E0D24Export:
    account_routes_path: Path
    public_sources_path: Path
    manifest_path: Path
    account_routes_sha256: str
    public_sources_sha256: str
    manifest_sha256: str


def _tes_route(
    readiness: TESFormalCostReadinessAudit,
    account: TESFormalCostAccount,
) -> TACAccountEvidenceRoute:
    blockers = readiness.candidate_blockers(account)
    ready = readiness.ready_candidates(account)
    if len(ready) == 1:
        status = EvidenceRouteStatus.STRICT_FORMAL_READY
        next_evidence = "No additional source field is required for this account."
    elif blockers:
        status = EvidenceRouteStatus.DIRECT_CANDIDATE_INCOMPLETE
        next_evidence = (
            "Resolve every candidate's price basis, denominator, provenance, "
            "technology boundary, and allowed-use blockers; then select one."
        )
    else:
        status = EvidenceRouteStatus.NO_DIRECT_CANDIDATE
        next_evidence = (
            "Obtain an Energy-or-higher direct component source with explicit "
            "price basis, denominator, topology boundary, and lifecycle scope."
        )
    return TACAccountEvidenceRoute(
        family=TACAccountFamily.TES_OWNERSHIP,
        account=account.value,
        status=status,
        strict_candidate_blockers=blockers,
        project_primary_required=False,
        required_next_evidence=next_evidence,
    )


_OPERATING_NEXT_EVIDENCE = {
    OperatingCostAccount.TIME_VARYING_ELECTRICITY_SETTLEMENT: (
        "Yangling 2024 contract positions, hourly settlement prices, imbalance "
        "settlement, and auxiliary-service bills."
    ),
    OperatingCostAccount.CARBON_COMPLIANCE_ALLOWANCE: (
        "Yangling 2024 verified emissions, free allocation, allowance holdings, "
        "CCER use, purchases, and actual compliance cost."
    ),
    OperatingCostAccount.CHP_VARIABLE_OM: (
        "The H-column account breakdown, fuel inclusion statement, fixed-variable "
        "split, and auditable activity drivers."
    ),
    OperatingCostAccount.TES_VARIABLE_OM: (
        "A project-specific dual-service TES O&M boundary and activity driver; "
        "public aggregate CSP O&M remains sensitivity-only."
    ),
}


def _operating_route(
    readiness: OperatingCostEvidenceAudit,
    account: OperatingCostAccount,
) -> TACAccountEvidenceRoute:
    record = readiness.record(account)
    blockers = record.formal_blockers()
    status = (
        EvidenceRouteStatus.STRICT_FORMAL_READY
        if not blockers
        else EvidenceRouteStatus.PROJECT_PRIMARY_REQUIRED
    )
    return TACAccountEvidenceRoute(
        family=TACAccountFamily.NONFUEL_OPERATING,
        account=account.value,
        status=status,
        strict_candidate_blockers=((record.evidence_id, blockers),),
        project_primary_required=bool(blockers),
        required_next_evidence=(
            "No additional project record is required for this account."
            if not blockers
            else _OPERATING_NEXT_EVIDENCE[account]
        ),
    )


def _public_sources() -> tuple[PublicEvidenceRecord, ...]:
    """Return only sources independently audited in the D24 route review."""

    return (
        PublicEvidenceRecord(
            source_id="zhang2024_energy_coal_tes_retrofit",
            title=(
                "Dynamic characteristics and economic analysis of a coal-fired "
                "power plant integrated with molten salt thermal energy storage "
                "for improving peaking capacity"
            ),
            source_locator="10.1016/j.energy.2023.130132",
            layer=PublicEvidenceLayer.ENERGY_PLUS_PEER_REVIEWED,
            allowed_use=PublicEvidenceUse.AGGREGATE_TECHNOLOGY_ANCHOR,
            venue="Energy",
            publisher_metric_name="Impact Factor",
            publisher_metric_value=9.4,
            metric_snapshot_date="2026-07-14",
            price_basis_explicit=False,
            capacity_denominator_explicit=False,
            technology_boundary_direct=False,
            component_account_eligible=False,
            note=(
                "The publisher page reports a coal-plant molten-salt retrofit and "
                "an aggregate equipment/material cost, but the accessible record "
                "does not close price year, component allocation, or the present "
                "three-temperature five-path dual-service boundary."
            ),
        ),
        PublicEvidenceRecord(
            source_id="dlr2021_two_tank_solar_salt_aggregate",
            title="Thermal energy storage cost benchmark for two-tank Solar Salt",
            source_locator="https://elib.dlr.de/141315/",
            layer=PublicEvidenceLayer.OFFICIAL_ENGINEERING,
            allowed_use=PublicEvidenceUse.AGGREGATE_TECHNOLOGY_ANCHOR,
            venue="DLR official engineering report",
            publisher_metric_name="",
            publisher_metric_value=None,
            metric_snapshot_date="",
            price_basis_explicit=True,
            capacity_denominator_explicit=True,
            technology_boundary_direct=False,
            component_account_eligible=False,
            note=(
                "The 20-22 EUR_2020/kWh_th-net two-tank Solar Salt range is a "
                "system calibration anchor, not a three-tank HITEC component set."
            ),
        ),
        PublicEvidenceRecord(
            source_id="nrel2011_tes_cost_methodology",
            title=(
                "Developing a Cost Model and Methodology to Estimate Capital "
                "Costs for Thermal Energy Storage"
            ),
            source_locator="10.2172/1031953",
            layer=PublicEvidenceLayer.OFFICIAL_ENGINEERING,
            allowed_use=PublicEvidenceUse.METHODOLOGY_ONLY,
            venue="NREL technical report",
            publisher_metric_name="",
            publisher_metric_value=None,
            metric_snapshot_date="",
            price_basis_explicit=False,
            capacity_denominator_explicit=False,
            technology_boundary_direct=False,
            component_account_eligible=False,
            note=(
                "The official report supports TES cost-model methodology for "
                "advanced power-cycle temperatures, not a formal current-topology "
                "component portfolio."
            ),
        ),
        PublicEvidenceRecord(
            source_id="nrel2013_molten_salt_component_cost_model",
            title="Molten Salt Power Tower Cost Model for SAM",
            source_locator="10.2172/1067902",
            layer=PublicEvidenceLayer.OFFICIAL_ENGINEERING,
            allowed_use=PublicEvidenceUse.COMPONENT_ENGINEERING_ANCHOR,
            venue="NREL technical report",
            publisher_metric_name="",
            publisher_metric_value=None,
            metric_snapshot_date="",
            price_basis_explicit=False,
            capacity_denominator_explicit=True,
            technology_boundary_direct=False,
            component_account_eligible=False,
            note=(
                "The component-based 100-MWe two-tank nitrate-salt CSP model "
                "supports engineering structure and scaling checks. It is not the "
                "Yangling CHP retrofit or the three-temperature HITEC topology."
            ),
        ),
        PublicEvidenceRecord(
            source_id="doe2016_molten_salt_capital_cost_estimate",
            title="Molten Salt: Concept Definition and Capital Cost Estimate",
            source_locator="10.2172/1335150",
            layer=PublicEvidenceLayer.OFFICIAL_ENGINEERING,
            allowed_use=PublicEvidenceUse.COMPONENT_ENGINEERING_ANCHOR,
            venue="DOE / Black & Veatch technical report",
            publisher_metric_name="",
            publisher_metric_value=None,
            metric_snapshot_date="",
            price_basis_explicit=False,
            capacity_denominator_explicit=False,
            technology_boundary_direct=False,
            component_account_eligible=False,
            note=(
                "The dated 10-MWe high-temperature molten-salt/sCO2 concept is an "
                "official cost-estimate reference, but its report date alone is not "
                "treated as a certified price basis for the present CHP topology."
            ),
        ),
    )


def build_e0d24_formal_tac_evidence_route_audit(
    *,
    layered_route_approved: bool = False,
) -> FormalTACEvidenceRouteAudit:
    """Join current D15/D20 gates without expanding any prior approval."""

    if not isinstance(layered_route_approved, bool):
        raise ValueError("layered_route_approved must be boolean")
    tes = build_e0d15_tes_formal_cost_readiness(
        composite_route_approved=layered_route_approved
    )
    operating = build_e0d20_operating_cost_evidence_audit()
    routes = tuple(
        _tes_route(tes, account) for account in TESFormalCostAccount
    ) + tuple(
        _operating_route(operating, account) for account in OperatingCostAccount
    )
    return FormalTACEvidenceRouteAudit(
        tes_readiness=tes,
        operating_readiness=operating,
        account_routes=routes,
        public_sources=_public_sources(),
        layered_route_approved=layered_route_approved,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(
    path: Path,
    fieldnames: tuple[str, ...],
    rows: list[dict[str, object]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_e0d24_formal_tac_evidence_route(
    audit: FormalTACEvidenceRouteAudit,
    output_dir: str | Path,
) -> E0D24Export:
    """Write deterministic account/source matrices and a source-lock manifest."""

    if not isinstance(audit, FormalTACEvidenceRouteAudit):
        raise ValueError("audit must be a FormalTACEvidenceRouteAudit")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    account_path = output / "e0d24_formal_tac_account_routes.csv"
    source_path = output / "e0d24_public_source_audit.csv"
    manifest_path = output / "manifest.json"

    account_rows: list[dict[str, object]] = []
    for row in audit.account_routes:
        blockers = ";".join(
            f"{evidence_id}:{'|'.join(items) if items else 'ready'}"
            for evidence_id, items in row.strict_candidate_blockers
        )
        account_rows.append(
            {
                "family": row.family.value,
                "account": row.account,
                "status": row.status.value,
                "strict_formal_ready": row.strict_formal_ready,
                "project_primary_required": row.project_primary_required,
                "strict_candidate_ids": "|".join(row.strict_candidate_ids),
                "strict_candidate_blockers": blockers,
                "required_next_evidence": row.required_next_evidence,
            }
        )
    _write_csv(
        account_path,
        (
            "family",
            "account",
            "status",
            "strict_formal_ready",
            "project_primary_required",
            "strict_candidate_ids",
            "strict_candidate_blockers",
            "required_next_evidence",
        ),
        account_rows,
    )

    source_rows: list[dict[str, object]] = []
    for source in audit.public_sources:
        source_rows.append(
            {
                "source_id": source.source_id,
                "title": source.title,
                "source_locator": source.source_locator,
                "layer": source.layer.value,
                "allowed_use": source.allowed_use.value,
                "venue": source.venue,
                "publisher_metric_name": source.publisher_metric_name,
                "publisher_metric_value": (
                    ""
                    if source.publisher_metric_value is None
                    else f"{source.publisher_metric_value:.6f}"
                ),
                "metric_snapshot_date": source.metric_snapshot_date,
                "price_basis_explicit": source.price_basis_explicit,
                "capacity_denominator_explicit": (
                    source.capacity_denominator_explicit
                ),
                "technology_boundary_direct": (
                    source.technology_boundary_direct
                ),
                "component_account_eligible": source.component_account_eligible,
                "formal_component_blockers": "|".join(
                    source.formal_component_blockers()
                ),
                "note": source.note,
            }
        )
    _write_csv(
        source_path,
        (
            "source_id",
            "title",
            "source_locator",
            "layer",
            "allowed_use",
            "venue",
            "publisher_metric_name",
            "publisher_metric_value",
            "metric_snapshot_date",
            "price_basis_explicit",
            "capacity_denominator_explicit",
            "technology_boundary_direct",
            "component_account_eligible",
            "formal_component_blockers",
            "note",
        ),
        source_rows,
    )

    account_sha = _sha256(account_path)
    source_sha = _sha256(source_path)
    manifest = {
        "schema": E0D24_SCHEMA,
        "account_count": len(audit.account_routes),
        "strict_formal_account_count": audit.strict_formal_account_count,
        "project_primary_required_count": audit.project_primary_required_count,
        "public_source_count": len(audit.public_sources),
        "layered_route_approved": audit.layered_route_approved,
        "formal_tac_ready": audit.formal_tac_ready,
        "e1_ready": audit.e1_ready,
        "files": {
            account_path.name: account_sha,
            source_path.name: source_sha,
        },
        "prohibitions": [
            "no_public_source_substitution_for_project_primary_accounts",
            "no_venue_laundering_of_official_engineering_values",
            "no_aggregate_anchor_allocation_to_component_accounts",
            "no_formal_tac_or_technology_winner_claim",
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return E0D24Export(
        account_routes_path=account_path,
        public_sources_path=source_path,
        manifest_path=manifest_path,
        account_routes_sha256=account_sha,
        public_sources_sha256=source_sha,
        manifest_sha256=_sha256(manifest_path),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export the E0-D-24 formal TAC evidence-route audit."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--layered-route-approved",
        action="store_true",
        help=(
            "Record an explicit future approval; this flag does not make missing "
            "evidence ready."
        ),
    )
    args = parser.parse_args(argv)
    audit = build_e0d24_formal_tac_evidence_route_audit(
        layered_route_approved=args.layered_route_approved
    )
    export = write_e0d24_formal_tac_evidence_route(audit, args.output_dir)
    print(export.manifest_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
