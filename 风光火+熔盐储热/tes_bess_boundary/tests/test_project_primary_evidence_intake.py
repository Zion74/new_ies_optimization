from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_d25_request_covers_every_account_with_unique_fields() -> None:
    from tes_bess_boundary.operating_cost_evidence import OperatingCostAccount
    from tes_bess_boundary.project_primary_evidence_intake import (
        build_e0d25_requirements,
    )

    requirements = build_e0d25_requirements()
    keys = tuple((item.account, item.field_key) for item in requirements)

    assert len(requirements) == 51
    assert len(keys) == len(set(keys))
    assert {item.account for item in requirements} == set(OperatingCostAccount)
    assert all(item.required_for_formal_review for item in requirements)


def test_d25_current_coverage_is_three_missing_and_one_partial() -> None:
    from tes_bess_boundary.operating_cost_evidence import OperatingCostAccount
    from tes_bess_boundary.project_primary_evidence_intake import (
        IntakeStatus,
        build_e0d25_project_primary_evidence_intake_audit,
    )

    audit = build_e0d25_project_primary_evidence_intake_audit()

    assert audit.ready_account_count == 0
    assert audit.project_data_request_ready is True
    assert audit.project_primary_intake_ready is False
    assert audit.formal_tac_ready is False
    assert audit.e1_ready is False
    assert audit.summary(
        OperatingCostAccount.TIME_VARYING_ELECTRICITY_SETTLEMENT
    ).status is IntakeStatus.MISSING
    assert audit.summary(
        OperatingCostAccount.CARBON_COMPLIANCE_ALLOWANCE
    ).status is IntakeStatus.MISSING
    assert audit.summary(
        OperatingCostAccount.TES_VARIABLE_OM
    ).status is IntakeStatus.MISSING

    chp = audit.summary(OperatingCostAccount.CHP_VARIABLE_OM)
    assert chp.status is IntakeStatus.PARTIAL
    assert chp.available_field_count == 6
    assert chp.missing_fields == (
        "cost_category",
        "fuel_included",
        "fixed_variable_class",
        "driver_type",
        "driver_quantity",
        "driver_unit",
        "inclusion_boundary",
        "exclusion_boundary",
    )


def test_d25_intake_certificate_never_becomes_a_formal_tac_certificate() -> None:
    from tes_bess_boundary.project_primary_evidence_intake import (
        ConfidentialityClass,
        CurrentFieldCoverage,
        ExportPolicy,
        build_e0d25_project_primary_evidence_intake_audit,
    )

    current = build_e0d25_project_primary_evidence_intake_audit()
    with pytest.raises(ValueError, match="project-primary intake is incomplete"):
        current.certify_intake()

    synthetic_receipt = replace(
        current.source_receipts[0], source_document_id="synthetic_review_receipt"
    )
    complete = replace(
        current,
        current_coverage=tuple(
            CurrentFieldCoverage(
                account=item.account,
                field_key=item.field_key,
                source_document_id=synthetic_receipt.source_document_id,
                source_locator="local evidence register",
                confidentiality=ConfidentialityClass.CONFIDENTIAL_LOCAL_ONLY,
                export_policy=ExportPolicy.DO_NOT_EXPORT,
                note="Synthetic structural test only.",
            )
            for item in current.requirements
        ),
        source_receipts=(synthetic_receipt,),
    )

    certificate = complete.certify_intake()
    assert complete.project_primary_intake_ready is True
    assert certificate.account_count == 4
    assert certificate.requirement_count == 51
    assert certificate.formal_validation_required is True
    assert complete.formal_tac_ready is False
    assert complete.e1_ready is False


def test_d25_submission_template_has_blank_values_and_local_privacy_defaults(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.project_primary_evidence_intake import (
        write_e0d25_project_primary_evidence_intake,
    )

    export = write_e0d25_project_primary_evidence_intake(output_dir=tmp_path)
    with export.submission_template_path.open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 51
    assert all(row["value"] == "" for row in rows)
    assert all(row["source_document_id"] == "" for row in rows)
    assert all(row["source_locator"] == "" for row in rows)
    assert {row["confidentiality"] for row in rows} == {
        "confidential_local_only"
    }
    assert {row["export_policy"] for row in rows} == {
        "metadata_only",
        "do_not_export",
    }


def test_d25_export_is_deterministic_and_keeps_all_formal_gates_closed(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.project_primary_evidence_intake import (
        E0D25_SCHEMA,
        write_e0d25_project_primary_evidence_intake,
    )

    first = write_e0d25_project_primary_evidence_intake(
        output_dir=tmp_path / "first"
    )
    second = write_e0d25_project_primary_evidence_intake(
        output_dir=tmp_path / "second"
    )

    assert first.required_fields_sha256 == second.required_fields_sha256
    assert first.current_coverage_sha256 == second.current_coverage_sha256
    assert first.submission_template_sha256 == second.submission_template_sha256
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.required_fields_sha256 == _sha256(first.required_fields_path)
    assert first.current_coverage_sha256 == _sha256(first.current_coverage_path)
    assert first.submission_template_sha256 == _sha256(
        first.submission_template_path
    )

    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == E0D25_SCHEMA
    assert manifest["account_count"] == 4
    assert manifest["requirement_count"] == 51
    assert manifest["ready_account_count"] == 0
    assert manifest["project_data_request_ready"] is True
    assert manifest["project_primary_intake_ready"] is False
    assert manifest["formal_portfolio_ready"] is False
    assert manifest["formal_tac_ready"] is False
    assert manifest["e1_ready"] is False
    assert manifest["raw_confidential_sources_exported"] is False
    assert manifest["local_confidential_values_exported"] is False


def test_d25_canonical_export_contains_no_confidential_comparator_identity(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.project_primary_evidence_intake import (
        write_e0d25_project_primary_evidence_intake,
    )

    export = write_e0d25_project_primary_evidence_intake(output_dir=tmp_path)
    payload = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            export.required_fields_path,
            export.current_coverage_path,
            export.submission_template_path,
            export.manifest_path,
        )
    )
    forbidden_markers = (
        "保密" + "-" + "不外传",
        "王" + "滩熔盐",
        "京津冀" + "陡河",
        ".docx",
    )
    assert all(marker not in payload for marker in forbidden_markers)
