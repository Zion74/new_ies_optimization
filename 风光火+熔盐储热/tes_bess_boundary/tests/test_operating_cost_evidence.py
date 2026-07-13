from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from openpyxl import load_workbook


DATA_ROOT = Path(__file__).resolve().parents[2]


def _workbook_path() -> Path:
    return (
        DATA_ROOT
        / "杨凌机组数据"
        / "杨凌机组数据"
        / "副本附表-存量机组基本信息表采集表（关中地区火电厂填写）.xlsx"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.mark.data_integration
def test_yangling_annual_om_reconciliation_is_locked_to_primary_cells() -> None:
    from tes_bess_boundary.operating_cost_evidence import (
        YANG_LING_ECONOMIC_WORKBOOK_SHA256,
        build_yangling_2024_annual_om_reconciliation,
    )

    path = _workbook_path()
    assert _sha256(path) == YANG_LING_ECONOMIC_WORKBOOK_SHA256
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook["煤电机组经济性指标"]
    reconciliation = build_yangling_2024_annual_om_reconciliation()

    for row, observation in zip((18, 19), reconciliation.observations, strict=True):
        assert sheet[f"H{row}"].value == pytest.approx(
            observation.annual_om_10k_cny
        )
        assert sheet[f"J{row}"].value == pytest.approx(
            observation.coal_price_cny_per_tce
        )
        assert sheet[f"M{row}"].value == pytest.approx(
            observation.annual_generation_10k_kwh
        )
    workbook.close()


def test_annual_om_label_is_not_reclassified_as_formal_vom() -> None:
    from tes_bess_boundary.operating_cost_evidence import (
        build_yangling_2024_annual_om_reconciliation,
    )

    reconciliation = build_yangling_2024_annual_om_reconciliation()

    assert reconciliation.is_generation_proportional is True
    assert reconciliation.has_common_coal_equivalent_rate is True
    assert reconciliation.common_cost_cny_per_mwh == pytest.approx(
        308.417118779524
    )
    assert reconciliation.common_coal_equivalent_g_per_kwh == pytest.approx(
        385.107408010793
    )
    assert reconciliation.formal_vom_blockers == (
        "cost_boundary",
        "fuel_overlap_risk",
        "variable_driver",
    )


def test_e0d20_all_four_non_fuel_accounts_remain_blocked() -> None:
    from tes_bess_boundary.operating_cost_evidence import (
        EvidenceDisposition,
        OperatingCostAccount,
        build_e0d20_operating_cost_evidence_audit,
    )

    audit = build_e0d20_operating_cost_evidence_audit()

    assert audit.formal_portfolio_ready is False
    assert audit.blocked_accounts == tuple(OperatingCostAccount)
    assert audit.record(
        OperatingCostAccount.TIME_VARYING_ELECTRICITY_SETTLEMENT
    ).formal_blockers() == (
        "allowed_use",
        "project_scope",
        "numerical_input",
        "variable_driver",
    )
    assert audit.record(
        OperatingCostAccount.CARBON_COMPLIANCE_ALLOWANCE
    ).formal_blockers() == (
        "allowed_use",
        "numerical_input",
        "variable_driver",
    )
    assert audit.record(OperatingCostAccount.CHP_VARIABLE_OM).formal_blockers() == (
        "allowed_use",
        "cost_boundary",
        "variable_driver",
    )
    tes = audit.record(OperatingCostAccount.TES_VARIABLE_OM)
    assert tes.disposition is EvidenceDisposition.SENSITIVITY_ONLY
    assert tes.formal_blockers() == (
        "allowed_use",
        "project_scope",
        "cost_boundary",
        "variable_driver",
        "technology_boundary",
    )
    with pytest.raises(ValueError, match="blocked operating-cost accounts"):
        audit.certify()


def test_operating_cost_certificate_requires_all_accounts_to_be_formal() -> None:
    from tes_bess_boundary.operating_cost_evidence import (
        EvidenceDisposition,
        OperatingCostEvidenceAudit,
        build_e0d20_operating_cost_evidence_audit,
    )

    current = build_e0d20_operating_cost_evidence_audit()
    records = tuple(
        replace(
            item,
            disposition=EvidenceDisposition.FORMAL_CANDIDATE,
            project_specific=True,
            numerical_input_available=True,
            cost_boundary_distinct=True,
            variable_driver_identified=True,
            technology_boundary_direct=True,
        )
        for item in current.records
    )
    ready = OperatingCostEvidenceAudit(
        records=records,
        annual_om_reconciliation=current.annual_om_reconciliation,
    )

    assert ready.formal_portfolio_ready is True
    assert ready.certify().records == records


def test_flat_settlement_cancels_only_under_equal_annual_service() -> None:
    from tes_bess_boundary.operating_cost_evidence import flat_settlement_delta_cny

    assert (
        flat_settlement_delta_cny(
            common_price_cny_per_mwh=354.5,
            comparator_export_mwh=4_269_882.495252,
            candidate_export_mwh=4_269_882.495252,
        )
        == 0.0
    )
    assert flat_settlement_delta_cny(
        common_price_cny_per_mwh=354.5,
        comparator_export_mwh=10.0,
        candidate_export_mwh=9.0,
    ) == pytest.approx(-354.5)


def test_e0d20_export_is_deterministic_and_self_auditing(tmp_path: Path) -> None:
    from tes_bess_boundary.operating_cost_evidence import (
        E0D20_SCHEMA,
        write_e0d20_operating_cost_evidence,
    )

    first = write_e0d20_operating_cost_evidence(tmp_path / "first")
    second = write_e0d20_operating_cost_evidence(tmp_path / "second")

    assert first.csv_path.read_bytes() == second.csv_path.read_bytes()
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()
    assert b"\r\n" not in first.manifest_path.read_bytes()
    assert first.csv_sha256 == _sha256(first.csv_path)
    assert first.manifest_sha256 == _sha256(first.manifest_path)

    with first.csv_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 6
    assert [row["record_type"] for row in rows].count(
        "chp_annual_observation"
    ) == 2

    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == E0D20_SCHEMA
    assert manifest["readiness"]["formal_portfolio_ready"] is False
    assert manifest["annual_om_reconciliation"][
        "is_generation_proportional"
    ] is True
