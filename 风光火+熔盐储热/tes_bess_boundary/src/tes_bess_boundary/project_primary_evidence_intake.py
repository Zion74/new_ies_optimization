"""E0-D-25 privacy-aware intake gate for project-primary TAC evidence.

E0-D-20 and E0-D-24 identify four non-fuel operating accounts that cannot be
closed with public literature.  This module turns that finding into a
deterministic data request without exporting project values or treating a
completed request as a formal TAC certificate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from tes_bess_boundary.operating_cost_evidence import (
    OperatingCostAccount,
    YANG_LING_ECONOMIC_WORKBOOK_SHA256,
)


E0D25_SCHEMA = "tes_bess_boundary.e0d25_project_primary_evidence_intake.v1"


class ConfidentialityClass(str, Enum):
    """Minimum handling class for a received project record."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL_LOCAL_ONLY = "confidential_local_only"


class ExportPolicy(str, Enum):
    """Whether metadata, but never the submitted value, may be exported."""

    METADATA_ONLY = "metadata_only"
    DO_NOT_EXPORT = "do_not_export"


class IntakeStatus(str, Enum):
    """Field-level completeness of one project-primary account."""

    MISSING = "missing"
    PARTIAL = "partial"
    READY_FOR_FORMAL_REVIEW = "ready_for_formal_review"


def _require_non_empty_string(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class EvidenceFieldRequirement:
    """One field required before an account can enter formal evidence review."""

    account: OperatingCostAccount
    field_key: str
    description: str
    accepted_unit: str
    granularity: str
    validation_rule: str
    confidentiality: ConfidentialityClass = (
        ConfidentialityClass.CONFIDENTIAL_LOCAL_ONLY
    )
    export_policy: ExportPolicy = ExportPolicy.METADATA_ONLY
    required_for_formal_review: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.account, OperatingCostAccount):
            raise ValueError("account must be selected with OperatingCostAccount")
        for field_name in (
            "field_key",
            "description",
            "accepted_unit",
            "granularity",
            "validation_rule",
        ):
            _require_non_empty_string(getattr(self, field_name), field_name)
        if not isinstance(self.confidentiality, ConfidentialityClass):
            raise ValueError("confidentiality must be a ConfidentialityClass")
        if not isinstance(self.export_policy, ExportPolicy):
            raise ValueError("export_policy must be an ExportPolicy")
        if not isinstance(self.required_for_formal_review, bool):
            raise ValueError("required_for_formal_review must be boolean")


@dataclass(frozen=True)
class CurrentFieldCoverage:
    """Metadata-only proof that one required field exists in a reviewed source."""

    account: OperatingCostAccount
    field_key: str
    source_document_id: str
    source_locator: str
    confidentiality: ConfidentialityClass
    export_policy: ExportPolicy
    note: str

    def __post_init__(self) -> None:
        if not isinstance(self.account, OperatingCostAccount):
            raise ValueError("account must be selected with OperatingCostAccount")
        for field_name in (
            "field_key",
            "source_document_id",
            "source_locator",
            "note",
        ):
            _require_non_empty_string(getattr(self, field_name), field_name)
        if not isinstance(self.confidentiality, ConfidentialityClass):
            raise ValueError("confidentiality must be a ConfidentialityClass")
        if not isinstance(self.export_policy, ExportPolicy):
            raise ValueError("export_policy must be an ExportPolicy")


@dataclass(frozen=True)
class SourceReceipt:
    """Opaque, metadata-only receipt for a source already used by E0-D-20."""

    source_document_id: str
    sha256: str
    reviewed_locators: tuple[str, ...]
    confidentiality: ConfidentialityClass
    export_policy: ExportPolicy

    def __post_init__(self) -> None:
        _require_non_empty_string(self.source_document_id, "source_document_id")
        if (
            not isinstance(self.sha256, str)
            or len(self.sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.sha256)
        ):
            raise ValueError("sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.reviewed_locators, tuple) or not self.reviewed_locators:
            raise ValueError("reviewed_locators must be a non-empty tuple")
        for locator in self.reviewed_locators:
            _require_non_empty_string(locator, "reviewed_locator")
        if not isinstance(self.confidentiality, ConfidentialityClass):
            raise ValueError("confidentiality must be a ConfidentialityClass")
        if not isinstance(self.export_policy, ExportPolicy):
            raise ValueError("export_policy must be an ExportPolicy")


@dataclass(frozen=True)
class AccountIntakeSummary:
    account: OperatingCostAccount
    required_field_count: int
    available_field_count: int
    missing_fields: tuple[str, ...]
    status: IntakeStatus

    @property
    def missing_field_count(self) -> int:
        return len(self.missing_fields)


@dataclass(frozen=True)
class ProjectPrimaryEvidenceIntakeCertificate:
    """Completeness certificate; formal account validation is still required."""

    account_count: int
    requirement_count: int
    formal_validation_required: bool = True


@dataclass(frozen=True)
class ProjectPrimaryEvidenceIntakeAudit:
    """Current metadata-only coverage of the four required project accounts."""

    requirements: tuple[EvidenceFieldRequirement, ...]
    current_coverage: tuple[CurrentFieldCoverage, ...]
    source_receipts: tuple[SourceReceipt, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.requirements, tuple) or any(
            not isinstance(item, EvidenceFieldRequirement)
            for item in self.requirements
        ):
            raise ValueError("requirements must be an immutable canonical tuple")
        requirement_keys = tuple(
            (item.account, item.field_key) for item in self.requirements
        )
        if len(requirement_keys) != len(set(requirement_keys)):
            raise ValueError("requirement account/field pairs must be unique")
        if {item.account for item in self.requirements} != set(
            OperatingCostAccount
        ):
            raise ValueError("requirements must cover every operating-cost account")

        if not isinstance(self.current_coverage, tuple) or any(
            not isinstance(item, CurrentFieldCoverage)
            for item in self.current_coverage
        ):
            raise ValueError("current_coverage must be an immutable canonical tuple")
        coverage_keys = tuple(
            (item.account, item.field_key) for item in self.current_coverage
        )
        if len(coverage_keys) != len(set(coverage_keys)):
            raise ValueError("coverage account/field pairs must be unique")
        unknown = set(coverage_keys) - set(requirement_keys)
        if unknown:
            raise ValueError(f"coverage contains undeclared fields: {sorted(unknown)}")

        if not isinstance(self.source_receipts, tuple) or any(
            not isinstance(item, SourceReceipt) for item in self.source_receipts
        ):
            raise ValueError("source_receipts must be an immutable canonical tuple")
        receipt_ids = tuple(item.source_document_id for item in self.source_receipts)
        if len(receipt_ids) != len(set(receipt_ids)):
            raise ValueError("source receipt ids must be unique")
        covered_receipt_ids = {
            item.source_document_id for item in self.current_coverage
        }
        if not covered_receipt_ids.issubset(set(receipt_ids)):
            raise ValueError("every covered field must reference a source receipt")

    def requirements_for(
        self, account: OperatingCostAccount
    ) -> tuple[EvidenceFieldRequirement, ...]:
        if not isinstance(account, OperatingCostAccount):
            raise ValueError("account must be selected with OperatingCostAccount")
        return tuple(item for item in self.requirements if item.account is account)

    def summary(self, account: OperatingCostAccount) -> AccountIntakeSummary:
        requirements = self.requirements_for(account)
        available = {
            item.field_key
            for item in self.current_coverage
            if item.account is account
        }
        missing = tuple(
            item.field_key
            for item in requirements
            if item.required_for_formal_review and item.field_key not in available
        )
        required_count = sum(
            item.required_for_formal_review for item in requirements
        )
        available_count = required_count - len(missing)
        if available_count == 0:
            status = IntakeStatus.MISSING
        elif missing:
            status = IntakeStatus.PARTIAL
        else:
            status = IntakeStatus.READY_FOR_FORMAL_REVIEW
        return AccountIntakeSummary(
            account=account,
            required_field_count=required_count,
            available_field_count=available_count,
            missing_fields=missing,
            status=status,
        )

    @property
    def ready_account_count(self) -> int:
        return sum(
            self.summary(account).status is IntakeStatus.READY_FOR_FORMAL_REVIEW
            for account in OperatingCostAccount
        )

    @property
    def project_data_request_ready(self) -> bool:
        return bool(self.requirements)

    @property
    def project_primary_intake_ready(self) -> bool:
        return self.ready_account_count == len(OperatingCostAccount)

    @property
    def formal_tac_ready(self) -> bool:
        # Intake completeness cannot replace D20/D24 boundary validation.
        return False

    @property
    def e1_ready(self) -> bool:
        return False

    def certify_intake(self) -> ProjectPrimaryEvidenceIntakeCertificate:
        if not self.project_primary_intake_ready:
            detail = "; ".join(
                f"{account.value}={','.join(self.summary(account).missing_fields)}"
                for account in OperatingCostAccount
                if self.summary(account).missing_fields
            )
            raise ValueError(f"project-primary intake is incomplete: {detail}")
        return ProjectPrimaryEvidenceIntakeCertificate(
            account_count=len(OperatingCostAccount),
            requirement_count=sum(
                item.required_for_formal_review for item in self.requirements
            ),
        )


@dataclass(frozen=True)
class E0D25Export:
    required_fields_path: Path
    current_coverage_path: Path
    submission_template_path: Path
    manifest_path: Path
    required_fields_sha256: str
    current_coverage_sha256: str
    submission_template_sha256: str
    manifest_sha256: str


def _requirement(
    account: OperatingCostAccount,
    field_key: str,
    description: str,
    accepted_unit: str,
    granularity: str,
    validation_rule: str,
    *,
    export_policy: ExportPolicy = ExportPolicy.METADATA_ONLY,
) -> EvidenceFieldRequirement:
    return EvidenceFieldRequirement(
        account=account,
        field_key=field_key,
        description=description,
        accepted_unit=accepted_unit,
        granularity=granularity,
        validation_rule=validation_rule,
        export_policy=export_policy,
    )


def build_e0d25_requirements() -> tuple[EvidenceFieldRequirement, ...]:
    """Return the frozen four-account project data request."""

    settlement = OperatingCostAccount.TIME_VARYING_ELECTRICITY_SETTLEMENT
    carbon = OperatingCostAccount.CARBON_COMPLIANCE_ALLOWANCE
    chp = OperatingCostAccount.CHP_VARIABLE_OM
    tes = OperatingCostAccount.TES_VARIABLE_OM
    return (
        _requirement(settlement, "project_legal_entity", "Settlement legal entity", "text", "project", "Must identify the Yangling settlement entity"),
        _requirement(settlement, "market_participant_id", "Market participant identifier", "text", "project", "Must match the settlement statement"),
        _requirement(settlement, "settlement_period", "Covered settlement period", "YYYY-MM-DD/YYYY-MM-DD", "statement", "Must overlap the modeled operating year"),
        _requirement(settlement, "timestamp", "Settlement interval timestamp", "ISO-8601", "settlement interval", "Must be unique within one market participant"),
        _requirement(settlement, "contract_position_mwh", "Contracted electricity position", "MWh", "settlement interval", "Must be finite and non-negative"),
        _requirement(settlement, "market_export_mwh", "Metered or settled electricity export", "MWh", "settlement interval", "Must be finite and non-negative"),
        _requirement(settlement, "settlement_price_cny_per_mwh", "Applied settlement price", "CNY/MWh", "settlement interval", "Must be finite and traceable to the statement"),
        _requirement(settlement, "imbalance_volume_mwh", "Imbalance settlement volume", "MWh", "settlement interval", "Signed convention must be documented"),
        _requirement(settlement, "imbalance_charge_cny", "Imbalance charge or credit", "CNY", "settlement interval", "Signed convention must be documented"),
        _requirement(settlement, "ancillary_service_charge_cny", "Ancillary-service charge or credit", "CNY", "settlement interval", "Included services must be enumerated"),
        _requirement(settlement, "source_document_id", "Opaque settlement document identifier", "text", "source document", "Must resolve in the local evidence register"),
        _requirement(settlement, "source_locator", "Local statement locator", "text", "source document", "Must resolve locally and must not be publicly exported", export_policy=ExportPolicy.DO_NOT_EXPORT),
        _requirement(carbon, "regulated_entity", "Regulated entity name and identifier", "text", "compliance entity", "Must match the official ETS entity"),
        _requirement(carbon, "compliance_period", "ETS compliance period", "year or date range", "compliance period", "Must identify the covered compliance cycle"),
        _requirement(carbon, "verified_emissions_tco2", "Verified covered emissions", "tCO2", "compliance period", "Must be finite and non-negative"),
        _requirement(carbon, "free_allowance_tco2", "Free allowance allocation", "tCO2", "compliance period", "Must be finite and non-negative"),
        _requirement(carbon, "opening_allowance_tco2", "Opening allowance holding", "tCO2", "compliance period", "Must be finite and non-negative"),
        _requirement(carbon, "closing_allowance_tco2", "Closing allowance holding", "tCO2", "compliance period", "Must be finite and non-negative"),
        _requirement(carbon, "ccer_surrendered_tco2", "CCER surrendered for compliance", "tCO2", "compliance period", "Must be finite and non-negative"),
        _requirement(carbon, "purchased_allowance_tco2", "Purchased allowance quantity", "tCO2", "transaction or compliance period", "Must be finite and non-negative"),
        _requirement(carbon, "allowance_purchase_cost_cny", "Total allowance acquisition cost", "CNY", "transaction or compliance period", "Must be finite and non-negative"),
        _requirement(carbon, "source_document_id", "Opaque compliance-ledger identifier", "text", "source document", "Must resolve in the local evidence register"),
        _requirement(carbon, "source_locator", "Local compliance-ledger locator", "text", "source document", "Must resolve locally and must not be publicly exported", export_policy=ExportPolicy.DO_NOT_EXPORT),
        _requirement(chp, "unit_id", "CHP unit identifier", "text", "unit", "Must distinguish unit 1 and unit 2"),
        _requirement(chp, "reporting_period", "Cost reporting period", "year or date range", "unit-period", "Must overlap the modeled operating year"),
        _requirement(chp, "raw_cost_label", "Verbatim cost-account label", "text", "cost account", "Must retain the source accounting label"),
        _requirement(chp, "annual_amount_cny", "Reported annual account amount", "CNY/year", "unit-period-account", "Must be finite and non-negative"),
        _requirement(chp, "cost_category", "Audited cost category", "text", "cost account", "Must distinguish fuel, fixed O&M, variable O&M, and other"),
        _requirement(chp, "fuel_included", "Whether the account includes fuel", "boolean", "cost account", "Must be explicitly confirmed from the ledger definition"),
        _requirement(chp, "fixed_variable_class", "Fixed or variable classification", "fixed|variable|mixed", "cost account", "Mixed accounts require an auditable split"),
        _requirement(chp, "driver_type", "Incremental cost driver", "text", "cost account", "Must identify MWh, starts, hours, or another physical driver"),
        _requirement(chp, "driver_quantity", "Observed driver quantity", "numeric", "unit-period-account", "Must be finite and non-negative"),
        _requirement(chp, "driver_unit", "Driver unit", "text", "cost account", "Must be dimensionally consistent with the amount"),
        _requirement(chp, "inclusion_boundary", "Included subaccounts", "text", "cost account", "Must enumerate included cost items"),
        _requirement(chp, "exclusion_boundary", "Excluded subaccounts", "text", "cost account", "Must exclude fuel and ownership costs counted elsewhere"),
        _requirement(chp, "source_document_id", "Opaque CHP ledger identifier", "text", "source document", "Must resolve in the local evidence register"),
        _requirement(chp, "source_locator", "Local CHP ledger locator", "text", "source document", "Must resolve locally and must not be publicly exported", export_policy=ExportPolicy.DO_NOT_EXPORT),
        _requirement(tes, "reference_project", "TES project or quotation identifier", "text", "project", "Must identify the Yangling design or a separately labeled sensitivity source"),
        _requirement(tes, "reporting_period", "O&M or quotation period", "year or date range", "project-period", "Must state the operating or price basis period"),
        _requirement(tes, "technology_topology", "TES technology and interface topology", "text", "project", "Must map to the three-temperature, five-path, dual-service boundary"),
        _requirement(tes, "price_base_date", "Price base date", "YYYY-MM", "quotation", "Must be explicit for escalation and currency handling"),
        _requirement(tes, "cost_category", "TES operating-cost category", "text", "cost account", "Must distinguish fixed O&M, variable O&M, electricity, and replacement"),
        _requirement(tes, "annual_amount_cny", "Reported annual TES account amount", "CNY/year", "project-period-account", "Must be finite and non-negative"),
        _requirement(tes, "fixed_variable_class", "Fixed or variable classification", "fixed|variable|mixed", "cost account", "Mixed accounts require an auditable split"),
        _requirement(tes, "driver_type", "Incremental TES cost driver", "text", "cost account", "Must identify throughput, starts, hours, inventory, or another driver"),
        _requirement(tes, "driver_quantity", "Observed or quoted driver quantity", "numeric", "project-period-account", "Must be finite and non-negative"),
        _requirement(tes, "driver_unit", "Driver unit", "text", "cost account", "Must be dimensionally consistent with the amount"),
        _requirement(tes, "inclusion_boundary", "Included TES subaccounts", "text", "cost account", "Must enumerate included equipment and services"),
        _requirement(tes, "exclusion_boundary", "Excluded TES subaccounts", "text", "cost account", "Must identify costs counted in ownership, fuel, or electricity accounts"),
        _requirement(tes, "source_document_id", "Opaque TES evidence identifier", "text", "source document", "Must resolve in the local evidence register"),
        _requirement(tes, "source_locator", "Local TES evidence locator", "text", "source document", "Must resolve locally and must not be publicly exported", export_policy=ExportPolicy.DO_NOT_EXPORT),
    )


def build_e0d25_project_primary_evidence_intake_audit() -> (
    ProjectPrimaryEvidenceIntakeAudit
):
    """Build current coverage without importing any confidential comparator."""

    document_id = "yangling_2024_economic_workbook"
    chp = OperatingCostAccount.CHP_VARIABLE_OM
    coverage = tuple(
        CurrentFieldCoverage(
            account=chp,
            field_key=field_key,
            source_document_id=document_id,
            source_locator=locator,
            confidentiality=ConfidentialityClass.INTERNAL,
            export_policy=ExportPolicy.METADATA_ONLY,
            note=note,
        )
        for field_key, locator, note in (
            ("unit_id", "煤电机组经济性指标!A18:A19", "Two unit rows are identified."),
            ("reporting_period", "workbook evidence register", "The D20 source lock is the 2024 reporting set."),
            ("raw_cost_label", "煤电机组经济性指标!H3", "The original annual O&M label is retained."),
            ("annual_amount_cny", "煤电机组经济性指标!H18:H19", "Values exist but are never exported by D25."),
            ("source_document_id", "source receipt", "An opaque source id is registered."),
            ("source_locator", "煤电机组经济性指标!H18:H19", "The reviewed cells are locally resolvable."),
        )
    )
    receipt = SourceReceipt(
        source_document_id=document_id,
        sha256=YANG_LING_ECONOMIC_WORKBOOK_SHA256,
        reviewed_locators=(
            "煤电机组经济性指标!A18:A19",
            "煤电机组经济性指标!H3",
            "煤电机组经济性指标!H18:H19",
        ),
        confidentiality=ConfidentialityClass.INTERNAL,
        export_policy=ExportPolicy.METADATA_ONLY,
    )
    return ProjectPrimaryEvidenceIntakeAudit(
        requirements=build_e0d25_requirements(),
        current_coverage=coverage,
        source_receipts=(receipt,),
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


def write_e0d25_project_primary_evidence_intake(
    output_dir: str | Path,
    audit: ProjectPrimaryEvidenceIntakeAudit | None = None,
) -> E0D25Export:
    """Write deterministic request, coverage, blank template, and manifest files."""

    if audit is None:
        audit = build_e0d25_project_primary_evidence_intake_audit()
    if not isinstance(audit, ProjectPrimaryEvidenceIntakeAudit):
        raise ValueError("audit must be a ProjectPrimaryEvidenceIntakeAudit")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    required_fields_path = output / "e0d25_required_fields.csv"
    current_coverage_path = output / "e0d25_current_coverage.csv"
    submission_template_path = output / "e0d25_submission_template.csv"
    manifest_path = output / "manifest.json"

    requirement_rows = [
        {
            "account": item.account.value,
            "field_key": item.field_key,
            "description": item.description,
            "accepted_unit": item.accepted_unit,
            "granularity": item.granularity,
            "validation_rule": item.validation_rule,
            "confidentiality": item.confidentiality.value,
            "export_policy": item.export_policy.value,
            "required_for_formal_review": item.required_for_formal_review,
        }
        for item in audit.requirements
    ]
    _write_csv(
        required_fields_path,
        (
            "account",
            "field_key",
            "description",
            "accepted_unit",
            "granularity",
            "validation_rule",
            "confidentiality",
            "export_policy",
            "required_for_formal_review",
        ),
        requirement_rows,
    )

    coverage_rows = []
    for account in OperatingCostAccount:
        summary = audit.summary(account)
        coverage_rows.append(
            {
                "account": account.value,
                "required_field_count": summary.required_field_count,
                "available_field_count": summary.available_field_count,
                "missing_field_count": summary.missing_field_count,
                "intake_status": summary.status.value,
                "ready_for_formal_review": (
                    summary.status is IntakeStatus.READY_FOR_FORMAL_REVIEW
                ),
                "missing_fields": "|".join(summary.missing_fields),
            }
        )
    _write_csv(
        current_coverage_path,
        (
            "account",
            "required_field_count",
            "available_field_count",
            "missing_field_count",
            "intake_status",
            "ready_for_formal_review",
            "missing_fields",
        ),
        coverage_rows,
    )

    template_rows = [
        {
            "account": item.account.value,
            "field_key": item.field_key,
            "value": "",
            "unit": item.accepted_unit,
            "period_start": "",
            "period_end": "",
            "source_document_id": "",
            "source_locator": "",
            "confidentiality": item.confidentiality.value,
            "export_policy": item.export_policy.value,
            "reviewer_note": "",
        }
        for item in audit.requirements
    ]
    _write_csv(
        submission_template_path,
        (
            "account",
            "field_key",
            "value",
            "unit",
            "period_start",
            "period_end",
            "source_document_id",
            "source_locator",
            "confidentiality",
            "export_policy",
            "reviewer_note",
        ),
        template_rows,
    )

    files = {
        required_fields_path.name: _sha256(required_fields_path),
        current_coverage_path.name: _sha256(current_coverage_path),
        submission_template_path.name: _sha256(submission_template_path),
    }
    manifest = {
        "schema": E0D25_SCHEMA,
        "account_count": len(OperatingCostAccount),
        "requirement_count": len(audit.requirements),
        "ready_account_count": audit.ready_account_count,
        "project_data_request_ready": audit.project_data_request_ready,
        "project_primary_intake_ready": audit.project_primary_intake_ready,
        "formal_portfolio_ready": False,
        "formal_tac_ready": audit.formal_tac_ready,
        "e1_ready": audit.e1_ready,
        "raw_confidential_sources_exported": False,
        "local_confidential_values_exported": False,
        "source_receipts": [
            {
                "source_document_id": receipt.source_document_id,
                "sha256": receipt.sha256,
                "reviewed_locators": list(receipt.reviewed_locators),
                "confidentiality": receipt.confidentiality.value,
                "export_policy": receipt.export_policy.value,
            }
            for receipt in audit.source_receipts
        ],
        "files": files,
        "prohibitions": [
            "no_guessing_missing_project_values",
            "no_public_or_comparable_substitution_for_project_primary_records",
            "no_raw_confidential_source_export",
            "no_submitted_value_export",
            "no_intake_completeness_as_formal_tac_certificate",
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return E0D25Export(
        required_fields_path=required_fields_path,
        current_coverage_path=current_coverage_path,
        submission_template_path=submission_template_path,
        manifest_path=manifest_path,
        required_fields_sha256=files[required_fields_path.name],
        current_coverage_sha256=files[current_coverage_path.name],
        submission_template_sha256=files[submission_template_path.name],
        manifest_sha256=_sha256(manifest_path),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export the E0-D-25 project-primary evidence intake gate."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    export = write_e0d25_project_primary_evidence_intake(
        output_dir=args.output_dir
    )
    print(export.manifest_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
