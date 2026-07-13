from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest


def _write_anchor_directory(directory: Path) -> Path:
    workbook = directory / "atb.xlsx"
    workbook.write_bytes(b"official workbook fixture\n")
    extraction = {
        "schema": "tes_bess_boundary.e0d11_sensitivity_cost_anchor.v1",
        "anchor_id": "nrel_atb_2022_utility_bess_4h_2021",
        "evidence_id": "nrel2022_utility_bess",
        "benchmark_year": 2021,
        "source_currency": "USD",
        "price_base_year": 2020,
        "system": {
            "rated_power_kw_dc": 60000.0,
            "usable_energy_kwh_dc": 240000.0,
            "supported_duration_hours": [2.0, 10.0],
            "analysis_life_years": 30,
        },
        "capital_cost": {
            "energy_cost_per_kwh_usable": 309.3044998122252,
            "power_cost_per_kw": 238.23917543208495,
            "reported_total_cost_per_kw_4h": 1475.4571746809856,
        },
        "fixed_om": {
            "fraction_of_capex_per_year": 0.025,
            "reported_cost_per_kw_year_4h": 36.88642936702464,
            "includes_capacity_augmentation": True,
            "augmentation_years": [10, 20],
            "augmentation_fraction_each": 0.2,
        },
        "source_cells": [
            "Utility-Scale Battery Storage!G9",
            "Utility-Scale Battery Storage!D12",
            "Utility-Scale Battery Storage!G20",
            "Utility-Scale Battery Storage!G26",
            "Utility-Scale Battery Storage!G40",
            "Utility-Scale Battery Storage!G59",
        ],
        "excluded_performance_conflicts": [
            {
                "parameter": "round_trip_efficiency",
                "workbook_value": 0.85,
                "webpage_value": 0.86,
                "decision": "excluded_from_cost_anchor",
            }
        ],
    }
    extraction_path = directory / "anchor.json"
    extraction_path.write_text(
        json.dumps(extraction, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema": "tes_bess_boundary.e0d11_sensitivity_cost_anchor_manifest.v1",
        "source_workbook": {
            "file": workbook.name,
            "sha256": hashlib.sha256(workbook.read_bytes()).hexdigest(),
            "url": "https://data.openei.org/files/5716/atb.xlsx",
        },
        "extraction": {
            "file": extraction_path.name,
            "sha256": hashlib.sha256(extraction_path.read_bytes()).hexdigest(),
        },
        "source_pages": [
            "https://atb.nrel.gov/electricity/2022/utility-scale_battery_storage"
        ],
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return directory


def test_loader_builds_a_sensitivity_only_anchor_and_reconciles_capex(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.cost_evidence import CostEvidenceUse
    from tes_bess_boundary.sensitivity_cost_anchors import (
        load_nrel_atb_2022_bess_cost_anchor,
    )

    anchor = load_nrel_atb_2022_bess_cost_anchor(_write_anchor_directory(tmp_path))

    assert anchor.evidence.allowed_use is CostEvidenceUse.OFFICIAL_ENGINEERING_ANCHOR
    assert anchor.duration_hours == pytest.approx(4.0)
    assert anchor.reconciled_total_cost_per_kw == pytest.approx(1475.4571746809856)
    assert anchor.reconciliation_error_per_kw == pytest.approx(0.0, abs=1e-10)
    assert anchor.reconciled_fixed_om_per_kw_year == pytest.approx(36.88642936702464)
    assert anchor.excluded_performance_parameters == ("round_trip_efficiency",)


def test_anchor_ledger_separates_power_and_usable_energy_denominators(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.sensitivity_cost_anchors import (
        load_nrel_atb_2022_bess_cost_anchor,
    )

    anchor = load_nrel_atb_2022_bess_cost_anchor(_write_anchor_directory(tmp_path))
    ledger = anchor.build_ledger(power_kw=1000.0, usable_energy_kwh=4000.0)

    assert ledger.power_component_cost == pytest.approx(238239.17543208494)
    assert ledger.energy_component_cost == pytest.approx(1237217.9992489007)
    assert ledger.initial_capital_cost == pytest.approx(1475457.1746809855)
    assert ledger.annual_fixed_om_cost == pytest.approx(36886.42936702464)
    assert ledger.is_reference_duration
    assert not ledger.is_reference_scale

    with pytest.raises(ValueError, match="supported duration"):
        anchor.build_ledger(power_kw=1000.0, usable_energy_kwh=11000.0)


def test_source_fom_cannot_be_combined_with_a_separate_replacement_ledger(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.sensitivity_cost_anchors import (
        load_nrel_atb_2022_bess_cost_anchor,
    )

    anchor = load_nrel_atb_2022_bess_cost_anchor(_write_anchor_directory(tmp_path))

    with pytest.raises(ValueError, match="double count"):
        anchor.build_ledger(
            power_kw=1000.0,
            usable_energy_kwh=4000.0,
            use_source_fixed_om=True,
            has_separate_replacement_ledger=True,
        )

    replacement_case = anchor.build_ledger(
        power_kw=1000.0,
        usable_energy_kwh=4000.0,
        use_source_fixed_om=False,
        has_separate_replacement_ledger=True,
    )
    assert replacement_case.annual_fixed_om_cost == 0.0
    assert replacement_case.has_separate_replacement_ledger


def test_sensitivity_ledger_price_conversion_retains_source_audit(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.economics import PriceBasisConversion
    from tes_bess_boundary.sensitivity_cost_anchors import (
        convert_sensitivity_cost_ledger,
        load_nrel_atb_2022_bess_cost_anchor,
    )

    ledger = load_nrel_atb_2022_bess_cost_anchor(
        _write_anchor_directory(tmp_path)
    ).build_ledger(power_kw=1000.0, usable_energy_kwh=4000.0)
    conversion = PriceBasisConversion(
        source_currency="USD",
        source_price_base_year=2020,
        target_currency="CNY",
        target_price_base_year=2024,
        source_price_index=100.0,
        target_price_index=120.0,
        target_currency_per_source_currency=7.0,
        price_index_series_id="fixture CPI",
        exchange_rate_series_id="fixture FX",
    )

    converted = convert_sensitivity_cost_ledger(ledger, conversion)

    assert converted.conversion_factor == pytest.approx(8.4)
    assert converted.currency == "CNY"
    assert converted.price_base_year == 2024
    assert converted.initial_capital_cost == pytest.approx(
        ledger.initial_capital_cost * 8.4
    )
    assert converted.annual_fixed_om_cost == pytest.approx(
        ledger.annual_fixed_om_cost * 8.4
    )
    assert converted.source_ledger is ledger


def test_loader_rejects_tampering_and_non_engineering_evidence(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.cost_evidence import (
        CostEvidenceAudit,
        CostEvidenceUse,
        build_e0d10_reference_cost_audit,
    )
    from tes_bess_boundary.sensitivity_cost_anchors import (
        load_nrel_atb_2022_bess_cost_anchor,
    )

    directory = _write_anchor_directory(tmp_path)
    (directory / "anchor.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="extraction SHA-256"):
        load_nrel_atb_2022_bess_cost_anchor(directory)

    directory = _write_anchor_directory(tmp_path)
    reference = build_e0d10_reference_cost_audit().get("nrel2022_utility_bess")
    wrong_use = replace(reference, allowed_use=CostEvidenceUse.FORMAL_CANDIDATE)
    with pytest.raises(ValueError, match="official engineering anchor"):
        load_nrel_atb_2022_bess_cost_anchor(
            directory,
            evidence_audit=CostEvidenceAudit((wrong_use,)),
        )
