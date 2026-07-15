from __future__ import annotations

from pathlib import Path

import pytest


def _canonical_periods_csv() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "数据采集"
        / "e0d36_representative_weeks"
        / "e0d36_representative_periods.csv"
    )


def _price_basis_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "数据采集" / "e0d4_price_basis_2024"


def _formal_heat_csv() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "数据采集"
        / "e0b_formal_2024"
        / "e0b_heat_hourly_2024.csv"
    )


def test_preregistered_state_values_and_service_reuse_are_frozen() -> None:
    from tes_bess_boundary.e0d38_prevalidation import (
        HIGH_HEAT_SCALE,
        R1_HIGH_HEAT_SCALE,
        state_spec,
    )

    baseline = state_spec("baseline")
    high = state_spec("high_heat_tight_pcc")
    high_r1 = state_spec("high_heat_tight_pcc_r1")
    long_duration = state_spec("long_duration_24h")

    assert baseline.heat_scale == 1.0
    assert baseline.pcc_export_capacity_mw == 700.0
    assert high.heat_scale == HIGH_HEAT_SCALE
    assert high.pcc_export_capacity_mw == 490.0
    assert high_r1.heat_scale == R1_HIGH_HEAT_SCALE
    assert high_r1.pcc_export_capacity_mw == 490.0
    assert high_r1.physical_service_key != high.physical_service_key
    assert long_duration.storage_duration_hours == 24.0
    assert long_duration.physical_service_key == baseline.physical_service_key


def test_high_heat_representative_input_changes_only_heat() -> None:
    from tes_bess_boundary.e0d38_prevalidation import (
        HIGH_HEAT_SCALE,
        load_representative_input,
        state_spec,
    )

    baseline = load_representative_input(
        _canonical_periods_csv(),
        state_spec("baseline"),
    )
    high = load_representative_input(
        _canonical_periods_csv(),
        state_spec("high_heat_tight_pcc"),
    )

    assert baseline.timeseries.period_count == 1_080
    assert baseline.horizon.weighted_hours(dt_hours=1.0) == 8_784.0
    assert high.timeseries.heat_demand_mw[0] == pytest.approx(
        HIGH_HEAT_SCALE * baseline.timeseries.heat_demand_mw[0]
    )
    assert high.timeseries.wind_available_mw == baseline.timeseries.wind_available_mw
    assert high.timeseries.pv_available_mw == baseline.timeseries.pv_available_mw
    assert high.renewable_available_mwh == baseline.renewable_available_mwh


def test_long_duration_state_sets_both_storage_service_durations_to_24h() -> None:
    from tes_bess_boundary.e0d38_prevalidation import (
        planning_inputs_for_state,
        state_spec,
    )

    bess, _bess_economics, tes, _loss, costs = planning_inputs_for_state(
        _price_basis_dir(),
        state_spec("long_duration_24h"),
    )

    assert bess.minimum_discharge_duration_hours == 24.0
    assert bess.maximum_discharge_duration_hours == 24.0
    assert tes.minimum_service_duration_hours == 24.0
    assert tes.maximum_service_duration_hours == 24.0
    assert costs.formal_project_eligible is False


def test_full_year_input_is_one_8784h_cyclic_block(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime, timedelta

    from tes_bess_boundary.e0d17_exploration import E0D17InputRow
    from tes_bess_boundary.e0d38_prevalidation import (
        load_full_year_input,
        state_spec,
    )

    start = datetime(2024, 1, 1)
    rows = tuple(
        E0D17InputRow(
            timestamp=start + timedelta(hours=hour),
            heat_demand_mw=100.0,
            wind_cf=0.5,
            pv_cf=0.25,
            ambient_temperature_c=20.0,
        )
        for hour in range(8_784)
    )
    monkeypatch.setattr(
        "tes_bess_boundary.e0d38_prevalidation.load_e0d17_inputs",
        lambda _heat, _vre: rows,
    )

    loaded = load_full_year_input("unused-heat", "unused-vre", state_spec("baseline"))

    assert loaded.timeseries.period_count == 8_784
    assert len(loaded.horizon.dispatch_blocks) == 1
    assert loaded.horizon.dispatch_blocks[0].periods == tuple(range(8_784))
    assert loaded.horizon.weighted_hours(dt_hours=1.0) == 8_784.0
    assert loaded.renewable_available_mwh == pytest.approx(
        8_784 * (1_050.0 * 0.5 + 200.0 * 0.25)
    )


def test_same_absolute_actual_service_is_used_on_representative_horizon() -> None:
    from tes_bess_boundary.e0d38_prevalidation import _service_specs, state_spec

    service = {
        "epsilon_curtailment_ceiling_mwh": 123_456.0,
        "pcc_export_target_mwh": 3_210_000.0,
    }

    curtailment, pcc = _service_specs(service, state_spec("baseline"))

    assert curtailment.maximum_curtailment_mwh == 123_456.0
    assert pcc.target_export_mwh == 3_210_000.0


def test_representative_hybrid_case_builds_on_d37_blocks_without_solving() -> None:
    from tes_bess_boundary.e0d17_exploration import COAL_PRICE_CNY_PER_TCE
    from tes_bess_boundary.e0d38_prevalidation import (
        build_d38_case,
        load_representative_input,
        planning_inputs_for_state,
        state_spec,
    )
    from tes_bess_boundary.model import Architecture, ValidationObjectiveSpec
    from tes_bess_boundary.planning_model import build_endogenous_capacity_model

    state = state_spec("baseline")
    horizon_input = load_representative_input(_canonical_periods_csv(), state)
    case = build_d38_case(
        state=state,
        architecture=Architecture.HYBRID,
        horizon_input=horizon_input,
        planning_inputs=planning_inputs_for_state(_price_basis_dir(), state),
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=COAL_PRICE_CNY_PER_TCE,
            curtailment_penalty_cny_per_mwh=0.0,
        ),
        curtailment_service=None,
        pcc_export_service=None,
    )

    model = build_endogenous_capacity_model(case)

    assert len(case.horizon.dispatch_blocks) == 7
    assert len(model.bess.energy_capacity_mwh) == 1
    assert len(model.tes.salt_mass_t) == 1
    assert not hasattr(model.bess, "initial_energy")
    assert not hasattr(model.tes, "initial_ht")


@pytest.mark.solver
def test_high_heat_static_pcc_diagnostic_identifies_frozen_week04_failure() -> None:
    from argparse import Namespace

    from tes_bess_boundary.e0d38_static_feasibility import run_diagnostic

    diagnostic = run_diagnostic(
        Namespace(
            state="high_heat_tight_pcc",
            heat_path=_formal_heat_csv(),
            periods_path=_canonical_periods_csv(),
            tolerance_mw=1e-7,
        )
    )

    assert diagnostic["static_limit"]["maximum_static_useful_heat_mw"] == pytest.approx(
        766.0767880248932
    )
    assert diagnostic["violating_hour_count"] == 36
    assert diagnostic["violating_week_numbers"] == [4]
    assert diagnostic["all_violating_hours_covered_by_d36"] is True


@pytest.mark.solver
def test_r1_high_heat_state_passes_static_pcc_necessary_condition() -> None:
    from argparse import Namespace

    from tes_bess_boundary.e0d38_static_feasibility import run_diagnostic

    diagnostic = run_diagnostic(
        Namespace(
            state="high_heat_tight_pcc_r1",
            heat_path=_formal_heat_csv(),
            periods_path=_canonical_periods_csv(),
            tolerance_mw=1e-7,
        )
    )

    assert diagnostic["violating_hour_count"] == 0
    assert diagnostic["maximum_scaled_heat_demand_mw"] == pytest.approx(
        724.03367951984
    )
    assert diagnostic["static_limit"]["maximum_static_useful_heat_mw"] == pytest.approx(
        766.0767880248932
    )
