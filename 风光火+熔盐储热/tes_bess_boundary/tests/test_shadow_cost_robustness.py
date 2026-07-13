from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest


DATA_ROOT = Path(__file__).resolve().parents[2]
D19_DIR = DATA_ROOT / "数据采集" / "e0d19_same_pcc_service"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_e0d21_source_is_locked_to_canonical_d19_interval() -> None:
    from tes_bess_boundary.shadow_cost_robustness import (
        E0D19_CSV_SHA256,
        E0D19_MANIFEST_SHA256,
        load_e0d21_source,
    )

    source = load_e0d21_source(D19_DIR)

    assert _sha256(D19_DIR / "e0d19_same_pcc_service.csv") == E0D19_CSV_SHA256
    assert _sha256(D19_DIR / "manifest.json") == E0D19_MANIFEST_SHA256
    assert tuple(item.window_id for item in source.records) == (
        "winter_day_20240101",
        "winter_fortnight_20240101",
    )
    exact, bounded = source.records
    assert exact.fuel_headroom_cny.lower == pytest.approx(12_893_119.760087)
    assert exact.fuel_headroom_cny.upper == pytest.approx(12_893_119.760087)
    assert bounded.fuel_headroom_cny.lower == pytest.approx(15_031_096.496283)
    assert bounded.fuel_headroom_cny.upper == pytest.approx(16_330_188.392595)
    assert source.formal_tac_ready is False


def test_shadow_scenario_requires_all_four_accounts_without_duplication() -> None:
    from tes_bess_boundary.operating_cost_evidence import OperatingCostAccount
    from tes_bess_boundary.shadow_cost_robustness import (
        ShadowCostContribution,
        ShadowCostScenario,
    )

    contributions = tuple(
        ShadowCostContribution(
            account=account,
            headroom_effect_lower_cny=0.0,
            headroom_effect_upper_cny=0.0,
            source_identity="author_normalized_stress",
            note="zero placeholder keeps the four-account boundary explicit",
        )
        for account in OperatingCostAccount
    )
    scenario = ShadowCostScenario(
        scenario_id="zero_shadow",
        contributions=contributions,
    )

    assert scenario.total_headroom_effect_cny.lower == 0.0
    assert scenario.total_headroom_effect_cny.upper == 0.0
    assert scenario.allowed_use == "sensitivity_only"
    assert scenario.formal_tac_eligible is False

    with pytest.raises(ValueError, match="exactly once"):
        ShadowCostScenario(
            scenario_id="duplicate_account",
            contributions=contributions[:-1] + (contributions[0],),
        )


def test_exact_window_single_account_adverse_threshold_touches_zero() -> None:
    from tes_bess_boundary.operating_cost_evidence import OperatingCostAccount
    from tes_bess_boundary.shadow_cost_robustness import (
        RobustnessStatus,
        apply_shadow_cost_scenario,
        build_single_account_adverse_scenario,
        load_e0d21_source,
    )

    record = load_e0d21_source(D19_DIR).records[0]
    threshold = record.fuel_headroom_cny.lower
    scenario = build_single_account_adverse_scenario(
        scenario_id="settlement_erases_exact_headroom",
        account=OperatingCostAccount.TIME_VARYING_ELECTRICITY_SETTLEMENT,
        adverse_cost_cny=threshold,
    )
    result = apply_shadow_cost_scenario(record, scenario)

    assert result.adjusted_headroom_cny.lower == pytest.approx(0.0, abs=1e-8)
    assert result.adjusted_headroom_cny.upper == pytest.approx(0.0, abs=1e-8)
    assert result.status is RobustnessStatus.EXACT_BREAK_EVEN
    assert result.formal_tac is False


def test_bounded_window_retains_three_robustness_regions() -> None:
    from tes_bess_boundary.shadow_cost_robustness import (
        RobustnessStatus,
        apply_unallocated_adverse_stress,
        load_e0d21_source,
    )

    record = load_e0d21_source(D19_DIR).records[1]
    lower = record.fuel_headroom_cny.lower
    upper = record.fuel_headroom_cny.upper

    assert apply_unallocated_adverse_stress(
        record, adverse_cost_cny=0.5 * lower
    ).status is RobustnessStatus.ROBUSTLY_POSITIVE
    assert apply_unallocated_adverse_stress(
        record, adverse_cost_cny=lower
    ).status is RobustnessStatus.INDETERMINATE_INCLUDING_BREAK_EVEN
    assert apply_unallocated_adverse_stress(
        record, adverse_cost_cny=(lower + upper) / 2.0
    ).status is RobustnessStatus.INDETERMINATE_INCLUDING_BREAK_EVEN
    assert apply_unallocated_adverse_stress(
        record, adverse_cost_cny=upper
    ).status is RobustnessStatus.INDETERMINATE_INCLUDING_BREAK_EVEN
    assert apply_unallocated_adverse_stress(
        record, adverse_cost_cny=1.25 * upper
    ).status is RobustnessStatus.ROBUSTLY_NEGATIVE


def test_favorable_and_adverse_account_intervals_propagate_conservatively() -> None:
    from tes_bess_boundary.operating_cost_evidence import OperatingCostAccount
    from tes_bess_boundary.shadow_cost_robustness import (
        RobustnessStatus,
        ShadowCostContribution,
        ShadowCostScenario,
        apply_shadow_cost_scenario,
        load_e0d21_source,
    )

    record = load_e0d21_source(D19_DIR).records[0]
    values = {
        OperatingCostAccount.TIME_VARYING_ELECTRICITY_SETTLEMENT: (-2.0, 1.0),
        OperatingCostAccount.CARBON_COMPLIANCE_ALLOWANCE: (3.0, 4.0),
        OperatingCostAccount.CHP_VARIABLE_OM: (5.0, 6.0),
        OperatingCostAccount.TES_VARIABLE_OM: (-8.0, -7.0),
    }
    scenario = ShadowCostScenario(
        scenario_id="mixed_interval",
        contributions=tuple(
            ShadowCostContribution(
                account=account,
                headroom_effect_lower_cny=values[account][0],
                headroom_effect_upper_cny=values[account][1],
                source_identity="synthetic_gold_standard",
                note="signed interval arithmetic test",
            )
            for account in OperatingCostAccount
        ),
    )
    result = apply_shadow_cost_scenario(record, scenario)

    assert scenario.total_headroom_effect_cny.lower == pytest.approx(-2.0)
    assert scenario.total_headroom_effect_cny.upper == pytest.approx(4.0)
    assert result.adjusted_headroom_cny.lower == pytest.approx(
        record.fuel_headroom_cny.lower - 2.0
    )
    assert result.adjusted_headroom_cny.upper == pytest.approx(
        record.fuel_headroom_cny.upper + 4.0
    )
    assert result.status is RobustnessStatus.ROBUSTLY_POSITIVE


def test_e0d21_export_is_deterministic_lf_only_and_not_formal_tac(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.shadow_cost_robustness import (
        E0D21_SCHEMA,
        write_e0d21_shadow_cost_robustness,
    )

    first = write_e0d21_shadow_cost_robustness(
        D19_DIR,
        tmp_path / "first",
    )
    second = write_e0d21_shadow_cost_robustness(
        D19_DIR,
        tmp_path / "second",
    )

    assert first.thresholds_path.read_bytes() == second.thresholds_path.read_bytes()
    assert first.stress_path.read_bytes() == second.stress_path.read_bytes()
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()
    for path in (
        first.thresholds_path,
        first.stress_path,
        first.manifest_path,
    ):
        assert b"\r\n" not in path.read_bytes()
        assert first.canonical_sha256[path.name] == _sha256(path)

    with first.thresholds_path.open(encoding="utf-8", newline="") as stream:
        thresholds = list(csv.DictReader(stream))
    with first.stress_path.open(encoding="utf-8", newline="") as stream:
        stresses = list(csv.DictReader(stream))
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))

    assert len(thresholds) == 10
    assert len(stresses) == 10
    assert manifest["schema"] == E0D21_SCHEMA
    assert manifest["scientific_boundary"]["formal_tac"] is False
    assert manifest["scientific_boundary"]["d20_formal_portfolio_ready"] is False
    assert manifest["scientific_boundary"]["account_values_are_estimates"] is False
