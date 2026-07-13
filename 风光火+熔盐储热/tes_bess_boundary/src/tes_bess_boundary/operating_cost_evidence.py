"""E0-D-20 evidence gate for non-fuel operating-cost accounts.

The same-PCC comparison closes a fuel-only value boundary, but a formal TAC
still needs project-specific electricity settlement, ETS compliance, CHP VOM,
and TES VOM.  This module keeps those accounts blocked until their numerical
drivers and non-overlapping cost boundaries are auditable.
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


YANG_LING_ECONOMIC_WORKBOOK_SHA256 = (
    "72d71cfeed7d8c3f3d564e00ca8bfdd47ee48228bf58ab3de5c9605added8fcf"
)
E0D20_SCHEMA = "tes_bess_boundary.e0d20_operating_cost_evidence.v1"


class OperatingCostAccount(str, Enum):
    """Non-fuel accounts required before the same-service result is TAC."""

    TIME_VARYING_ELECTRICITY_SETTLEMENT = (
        "time_varying_electricity_settlement"
    )
    CARBON_COMPLIANCE_ALLOWANCE = "carbon_compliance_allowance"
    CHP_VARIABLE_OM = "chp_variable_om"
    TES_VARIABLE_OM = "tes_variable_om"


class EvidenceAuthority(str, Enum):
    """Authority of the source, independent from its boundary fit."""

    PROJECT_PRIMARY_RECORD = "project_primary_record"
    OFFICIAL_REGULATORY = "official_regulatory"
    CORE_PEER_REVIEWED = "core_peer_reviewed"
    AUTHOR_SCENARIO = "author_scenario"


class EvidenceDisposition(str, Enum):
    """Permitted use of a record in the current research contract."""

    FORMAL_CANDIDATE = "formal_candidate"
    SENSITIVITY_ONLY = "sensitivity_only"
    BLOCKED = "blocked"


def _require_non_empty_string(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_positive_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)) or float(value) <= 0:
        raise ValueError(f"{field_name} must be finite and positive")


@dataclass(frozen=True)
class AnnualOperatingCostObservation:
    """One source-locked row from the Yangling annual economic table."""

    unit_id: str
    source_cell: str
    reported_label: str
    annual_om_10k_cny: float
    annual_generation_10k_kwh: float
    coal_price_cny_per_tce: float

    def __post_init__(self) -> None:
        for field_name in ("unit_id", "source_cell", "reported_label"):
            _require_non_empty_string(getattr(self, field_name), field_name)
        for field_name in (
            "annual_om_10k_cny",
            "annual_generation_10k_kwh",
            "coal_price_cny_per_tce",
        ):
            _require_positive_number(getattr(self, field_name), field_name)

    @property
    def annual_cost_cny(self) -> float:
        return self.annual_om_10k_cny * 10_000.0

    @property
    def annual_generation_mwh(self) -> float:
        return self.annual_generation_10k_kwh * 10.0

    @property
    def reported_cost_cny_per_mwh(self) -> float:
        return self.annual_cost_cny / self.annual_generation_mwh

    @property
    def coal_equivalent_g_per_kwh(self) -> float:
        return (
            self.reported_cost_cny_per_mwh
            / self.coal_price_cny_per_tce
            * 1_000.0
        )


@dataclass(frozen=True)
class AnnualOMReconciliation:
    """Audit whether the annual O&M label is distinct from the fuel ledger."""

    observations: tuple[AnnualOperatingCostObservation, ...]
    source_sha256: str = YANG_LING_ECONOMIC_WORKBOOK_SHA256
    relative_tolerance: float = 1e-12

    def __post_init__(self) -> None:
        if not isinstance(self.observations, tuple) or len(self.observations) < 2:
            raise ValueError("observations must contain at least two immutable rows")
        if any(
            not isinstance(item, AnnualOperatingCostObservation)
            for item in self.observations
        ):
            raise ValueError("observations must be canonical annual-cost rows")
        unit_ids = tuple(item.unit_id for item in self.observations)
        if len(set(unit_ids)) != len(unit_ids):
            raise ValueError("annual-cost unit_id values must be unique")
        if (
            not isinstance(self.source_sha256, str)
            or len(self.source_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.source_sha256)
        ):
            raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
        _require_positive_number(self.relative_tolerance, "relative_tolerance")

    @property
    def is_generation_proportional(self) -> bool:
        reference = self.observations[0].reported_cost_cny_per_mwh
        return all(
            math.isclose(
                item.reported_cost_cny_per_mwh,
                reference,
                rel_tol=self.relative_tolerance,
                abs_tol=0.0,
            )
            for item in self.observations[1:]
        )

    @property
    def has_common_coal_equivalent_rate(self) -> bool:
        reference = self.observations[0].coal_equivalent_g_per_kwh
        return all(
            math.isclose(
                item.coal_equivalent_g_per_kwh,
                reference,
                rel_tol=self.relative_tolerance,
                abs_tol=0.0,
            )
            for item in self.observations[1:]
        )

    @property
    def common_cost_cny_per_mwh(self) -> float | None:
        if not self.is_generation_proportional:
            return None
        return self.observations[0].reported_cost_cny_per_mwh

    @property
    def common_coal_equivalent_g_per_kwh(self) -> float | None:
        if not self.has_common_coal_equivalent_rate:
            return None
        return self.observations[0].coal_equivalent_g_per_kwh

    @property
    def formal_vom_blockers(self) -> tuple[str, ...]:
        blockers = ["cost_boundary", "variable_driver"]
        if self.is_generation_proportional and self.has_common_coal_equivalent_rate:
            blockers.insert(1, "fuel_overlap_risk")
        return tuple(blockers)


@dataclass(frozen=True)
class OperatingCostEvidenceRecord:
    """One audited candidate for a required non-fuel operating-cost account."""

    account: OperatingCostAccount
    evidence_id: str
    source_locator: str
    authority: EvidenceAuthority
    disposition: EvidenceDisposition
    project_specific: bool
    numerical_input_available: bool
    cost_boundary_distinct: bool
    variable_driver_identified: bool
    technology_boundary_direct: bool
    note: str

    def __post_init__(self) -> None:
        if not isinstance(self.account, OperatingCostAccount):
            raise ValueError("account must be selected with OperatingCostAccount")
        for field_name in ("evidence_id", "source_locator", "note"):
            _require_non_empty_string(getattr(self, field_name), field_name)
        if not isinstance(self.authority, EvidenceAuthority):
            raise ValueError("authority must be selected with EvidenceAuthority")
        if not isinstance(self.disposition, EvidenceDisposition):
            raise ValueError(
                "disposition must be selected with EvidenceDisposition"
            )
        for field_name in (
            "project_specific",
            "numerical_input_available",
            "cost_boundary_distinct",
            "variable_driver_identified",
            "technology_boundary_direct",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be boolean")

    def formal_blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.disposition is not EvidenceDisposition.FORMAL_CANDIDATE:
            blockers.append("allowed_use")
        if not self.project_specific:
            blockers.append("project_scope")
        if not self.numerical_input_available:
            blockers.append("numerical_input")
        if not self.cost_boundary_distinct:
            blockers.append("cost_boundary")
        if not self.variable_driver_identified:
            blockers.append("variable_driver")
        if not self.technology_boundary_direct:
            blockers.append("technology_boundary")
        return tuple(blockers)


@dataclass(frozen=True)
class OperatingCostPortfolioCertificate:
    """Certificate issued only when all four required accounts are formal."""

    records: tuple[OperatingCostEvidenceRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or any(
            not isinstance(item, OperatingCostEvidenceRecord)
            for item in self.records
        ):
            raise ValueError("records must be an immutable canonical tuple")
        accounts = tuple(item.account for item in self.records)
        if len(accounts) != len(OperatingCostAccount) or set(accounts) != set(
            OperatingCostAccount
        ):
            raise ValueError("certificate must cover every operating-cost account")
        blocked = {
            item.account.value: item.formal_blockers()
            for item in self.records
            if item.formal_blockers()
        }
        if blocked:
            raise ValueError("operating-cost certificate contains blocked accounts")


@dataclass(frozen=True)
class OperatingCostEvidenceAudit:
    """Strict E0-D-20 readiness gate for the four non-fuel accounts."""

    records: tuple[OperatingCostEvidenceRecord, ...]
    annual_om_reconciliation: AnnualOMReconciliation

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or any(
            not isinstance(item, OperatingCostEvidenceRecord)
            for item in self.records
        ):
            raise ValueError("records must be an immutable canonical tuple")
        accounts = tuple(item.account for item in self.records)
        if len(accounts) != len(OperatingCostAccount) or set(accounts) != set(
            OperatingCostAccount
        ):
            raise ValueError("audit must cover every operating-cost account once")
        if not isinstance(self.annual_om_reconciliation, AnnualOMReconciliation):
            raise ValueError("annual_om_reconciliation must be canonical")

    def record(self, account: OperatingCostAccount) -> OperatingCostEvidenceRecord:
        if not isinstance(account, OperatingCostAccount):
            raise ValueError("account must be selected with OperatingCostAccount")
        return next(item for item in self.records if item.account is account)

    @property
    def blocked_accounts(self) -> tuple[OperatingCostAccount, ...]:
        return tuple(item.account for item in self.records if item.formal_blockers())

    @property
    def formal_portfolio_ready(self) -> bool:
        return not self.blocked_accounts

    def certify(self) -> OperatingCostPortfolioCertificate:
        if self.blocked_accounts:
            details = "; ".join(
                f"{item.account.value}={','.join(item.formal_blockers())}"
                for item in self.records
                if item.formal_blockers()
            )
            raise ValueError(f"blocked operating-cost accounts: {details}")
        return OperatingCostPortfolioCertificate(self.records)


@dataclass(frozen=True)
class E0D20Export:
    csv_path: Path
    manifest_path: Path
    csv_sha256: str
    manifest_sha256: str


def build_yangling_2024_annual_om_reconciliation() -> AnnualOMReconciliation:
    """Return the exact H/J/M source rows without treating H as usable VOM."""

    return AnnualOMReconciliation(
        observations=(
            AnnualOperatingCostObservation(
                unit_id="#1",
                source_cell="煤电机组经济性指标!H18/J18/M18",
                reported_label="运维成本（万元/年）",
                annual_om_10k_cny=49_711.5347728162,
                annual_generation_10k_kwh=161_182.8,
                coal_price_cny_per_tce=800.86,
            ),
            AnnualOperatingCostObservation(
                unit_id="#2",
                source_cell="煤电机组经济性指标!H19/J19/M19",
                reported_label="运维成本（万元/年）",
                annual_om_10k_cny=44_489.7862181839,
                annual_generation_10k_kwh=144_252.0,
                coal_price_cny_per_tce=800.86,
            ),
        )
    )


def build_e0d20_operating_cost_evidence_audit() -> OperatingCostEvidenceAudit:
    """Build the current blocked portfolio from primary and high-tier sources."""

    reconciliation = build_yangling_2024_annual_om_reconciliation()
    return OperatingCostEvidenceAudit(
        records=(
            OperatingCostEvidenceRecord(
                account=(
                    OperatingCostAccount.TIME_VARYING_ELECTRICITY_SETTLEMENT
                ),
                evidence_id="shaanxi2024_market_mechanism_without_yangling_curve",
                source_locator=(
                    "https://xbj.nea.gov.cn/dtyw/hyxx/202404/"
                    "t20240417_260851.html"
                ),
                authority=EvidenceAuthority.OFFICIAL_REGULATORY,
                disposition=EvidenceDisposition.BLOCKED,
                project_specific=False,
                numerical_input_available=False,
                cost_boundary_distinct=True,
                variable_driver_identified=False,
                technology_boundary_direct=True,
                note=(
                    "The official source confirms hourly energy-block trading, "
                    "but supplies neither Yangling contract positions nor its "
                    "hourly settlement prices. The local TOU columns remain an "
                    "author scenario only."
                ),
            ),
            OperatingCostEvidenceRecord(
                account=OperatingCostAccount.CARBON_COMPLIANCE_ALLOWANCE,
                evidence_id="yangling_ets_entity_status_without_2024_allowance_ledger",
                source_locator=(
                    "https://sthjt.shaanxi.gov.cn/sy/gs/202301/"
                    "t20230106_3022939.html"
                ),
                authority=EvidenceAuthority.OFFICIAL_REGULATORY,
                disposition=EvidenceDisposition.BLOCKED,
                project_specific=True,
                numerical_input_available=False,
                cost_boundary_distinct=True,
                variable_driver_identified=False,
                technology_boundary_direct=True,
                note=(
                    "The official list identifies Yangling as an ETS entity, "
                    "but does not disclose its 2024 verified allocation gap, "
                    "holdings, CCER use, or acquisition cost."
                ),
            ),
            OperatingCostEvidenceRecord(
                account=OperatingCostAccount.CHP_VARIABLE_OM,
                evidence_id="yangling2024_annual_om_label_fuel_overlap_risk",
                source_locator=(
                    "副本附表-存量机组基本信息表采集表（关中地区火电厂填写）.xlsx#"
                    "煤电机组经济性指标!H18:H19"
                ),
                authority=EvidenceAuthority.PROJECT_PRIMARY_RECORD,
                disposition=EvidenceDisposition.BLOCKED,
                project_specific=True,
                numerical_input_available=True,
                cost_boundary_distinct=False,
                variable_driver_identified=False,
                technology_boundary_direct=True,
                note=(
                    "The two annual values are exactly generation-proportional "
                    "and imply one common coal-equivalent rate. Without a cost "
                    "breakdown, treating H18:H19 as incremental VOM risks "
                    "double-counting the existing fuel ledger."
                ),
            ),
            OperatingCostEvidenceRecord(
                account=OperatingCostAccount.TES_VARIABLE_OM,
                evidence_id="klasing2025_aggregate_tes_om_sensitivity",
                source_locator="10.1016/j.apenergy.2024.124524",
                authority=EvidenceAuthority.CORE_PEER_REVIEWED,
                disposition=EvidenceDisposition.SENSITIVITY_ONLY,
                project_specific=False,
                numerical_input_available=True,
                cost_boundary_distinct=False,
                variable_driver_identified=False,
                technology_boundary_direct=False,
                note=(
                    "Applied Energy clears the venue gate, but the aggregate "
                    "CSP-derived O&M boundary does not map to the present "
                    "three-temperature, five-path, dual-service CHP-TES."
                ),
            ),
        ),
        annual_om_reconciliation=reconciliation,
    )


def flat_settlement_delta_cny(
    *,
    common_price_cny_per_mwh: float,
    comparator_export_mwh: float,
    candidate_export_mwh: float,
) -> float:
    """Return the settlement difference; equal annual service cancels exactly."""

    _require_positive_number(common_price_cny_per_mwh, "common_price_cny_per_mwh")
    for value, field_name in (
        (comparator_export_mwh, "comparator_export_mwh"),
        (candidate_export_mwh, "candidate_export_mwh"),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field_name} must be numeric")
        if not math.isfinite(float(value)) or float(value) < 0:
            raise ValueError(f"{field_name} must be finite and non-negative")
    return common_price_cny_per_mwh * (
        candidate_export_mwh - comparator_export_mwh
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_rows(audit: OperatingCostEvidenceAudit) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in audit.records:
        rows.append(
            {
                "record_type": "account_evidence",
                "account": record.account.value,
                "evidence_id": record.evidence_id,
                "unit_id": "",
                "source_locator": record.source_locator,
                "source_sha256": "",
                "source_cell": "",
                "authority": record.authority.value,
                "disposition": record.disposition.value,
                "project_specific": record.project_specific,
                "numerical_input_available": record.numerical_input_available,
                "cost_boundary_distinct": record.cost_boundary_distinct,
                "variable_driver_identified": record.variable_driver_identified,
                "technology_boundary_direct": record.technology_boundary_direct,
                "annual_om_10k_cny": "",
                "annual_generation_10k_kwh": "",
                "coal_price_cny_per_tce": "",
                "derived_cost_cny_per_mwh": "",
                "derived_coal_equivalent_g_per_kwh": "",
                "formal_blockers": "|".join(record.formal_blockers()),
                "note": record.note,
            }
        )
    for observation in audit.annual_om_reconciliation.observations:
        rows.append(
            {
                "record_type": "chp_annual_observation",
                "account": OperatingCostAccount.CHP_VARIABLE_OM.value,
                "evidence_id": "yangling2024_annual_om_source_row",
                "unit_id": observation.unit_id,
                "source_locator": "yangling_economic_workbook",
                "source_sha256": audit.annual_om_reconciliation.source_sha256,
                "source_cell": observation.source_cell,
                "authority": EvidenceAuthority.PROJECT_PRIMARY_RECORD.value,
                "disposition": EvidenceDisposition.BLOCKED.value,
                "project_specific": True,
                "numerical_input_available": True,
                "cost_boundary_distinct": False,
                "variable_driver_identified": False,
                "technology_boundary_direct": True,
                "annual_om_10k_cny": f"{observation.annual_om_10k_cny:.12f}",
                "annual_generation_10k_kwh": (
                    f"{observation.annual_generation_10k_kwh:.12f}"
                ),
                "coal_price_cny_per_tce": (
                    f"{observation.coal_price_cny_per_tce:.12f}"
                ),
                "derived_cost_cny_per_mwh": (
                    f"{observation.reported_cost_cny_per_mwh:.12f}"
                ),
                "derived_coal_equivalent_g_per_kwh": (
                    f"{observation.coal_equivalent_g_per_kwh:.12f}"
                ),
                "formal_blockers": "|".join(
                    audit.annual_om_reconciliation.formal_vom_blockers
                ),
                "note": (
                    "Source label retained verbatim; derived quantities are an "
                    "overlap diagnostic, not a reclassification as measured fuel."
                ),
            }
        )
    return rows


def write_e0d20_operating_cost_evidence(output_dir: str | Path) -> E0D20Export:
    """Write deterministic CSV and manifest evidence artifacts."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    audit = build_e0d20_operating_cost_evidence_audit()
    rows = _csv_rows(audit)
    csv_path = destination / "e0d20_operating_cost_evidence.csv"
    manifest_path = destination / "manifest.json"
    fieldnames = tuple(rows[0])
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    csv_sha256 = _sha256(csv_path)
    reconciliation = audit.annual_om_reconciliation
    manifest = {
        "schema": E0D20_SCHEMA,
        "canonical_files": {
            csv_path.name: {"sha256": csv_sha256, "rows": len(rows)}
        },
        "source_files": {
            "yangling_economic_workbook": {
                "sha256": reconciliation.source_sha256,
                "cells": [
                    item.source_cell for item in reconciliation.observations
                ],
            }
        },
        "readiness": {
            "formal_portfolio_ready": audit.formal_portfolio_ready,
            "blocked_accounts": [item.value for item in audit.blocked_accounts],
            "flat_settlement_rule": (
                "common flat price times equal annual PCC export cancels exactly"
            ),
        },
        "annual_om_reconciliation": {
            "is_generation_proportional": reconciliation.is_generation_proportional,
            "has_common_coal_equivalent_rate": (
                reconciliation.has_common_coal_equivalent_rate
            ),
            "common_cost_cny_per_mwh": reconciliation.common_cost_cny_per_mwh,
            "common_coal_equivalent_g_per_kwh": (
                reconciliation.common_coal_equivalent_g_per_kwh
            ),
            "formal_vom_blockers": list(reconciliation.formal_vom_blockers),
        },
        "claim_boundary": (
            "Evidence audit only: no project TAC, ETS compliance cost, hourly "
            "settlement revenue, CHP VOM, or TES VOM is certified."
        ),
    }
    with manifest_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )
    return E0D20Export(
        csv_path=csv_path,
        manifest_path=manifest_path,
        csv_sha256=csv_sha256,
        manifest_sha256=_sha256(manifest_path),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write the E0-D-20 operating-cost evidence audit."
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    export = write_e0d20_operating_cost_evidence(args.output)
    print(f"CSV {export.csv_path} {export.csv_sha256}")
    print(f"MANIFEST {export.manifest_path} {export.manifest_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
