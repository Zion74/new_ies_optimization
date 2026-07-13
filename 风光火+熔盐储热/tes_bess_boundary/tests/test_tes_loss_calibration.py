from __future__ import annotations

from dataclasses import fields

import pytest


def test_trevisan_anchor_reproduces_disclosed_aggregate_quantities() -> None:
    from tes_bess_boundary.tes_loss_calibration import (
        build_trevisan_2022_aggregate_anchor,
    )

    anchor = build_trevisan_2022_aggregate_anchor()

    assert anchor.source_doi == "10.1016/j.enconman.2022.116362"
    assert anchor.gross_capacity_normalized_loss_fraction_per_hour == pytest.approx(
        797.0 / 45.0 / 8760.0
    )
    assert anchor.net_annual_thermal_loss_mwh == pytest.approx(797.0 * 0.266)
    assert anchor.net_capacity_normalized_loss_fraction_per_hour == pytest.approx(
        797.0 * 0.266 / 45.0 / 8760.0
    )
    assert anchor.pump_electricity_target_mwh == pytest.approx(21_110.0 * 0.005)


def test_klasing_anchor_is_a_daily_full_charge_system_level_quantity() -> None:
    from tes_bess_boundary.tes_loss_calibration import (
        build_klasing_2025_daily_retention_anchor,
    )

    anchor = build_klasing_2025_daily_retention_anchor()

    assert anchor.source_doi == "10.1016/j.apenergy.2024.124524"
    assert anchor.full_charge_retention == pytest.approx(0.99)
    assert anchor.hold_hours == 24
    assert anchor.equivalent_uniform_hourly_loss_fraction == pytest.approx(
        1.0 - 0.99 ** (1.0 / 24.0)
    )


def test_e0d9b_loss_scenarios_are_ordered_author_calibrations() -> None:
    from tes_bess_boundary.tes_loss_calibration import (
        E0D9BLossLevel,
        build_e0d9b_loss_scenarios,
    )

    scenarios = build_e0d9b_loss_scenarios()

    assert tuple(scenario.level for scenario in scenarios) == (
        E0D9BLossLevel.LOW,
        E0D9BLossLevel.BASE,
        E0D9BLossLevel.HIGH,
    )
    low, base, high = scenarios
    assert low.target_full_charge_retention > base.target_full_charge_retention
    assert base.target_full_charge_retention > high.target_full_charge_retention
    assert low.target_full_charge_retention == pytest.approx(0.99)
    assert base.loss_compensation_fraction == pytest.approx(0.734)
    assert high.loss_compensation_fraction == pytest.approx(0.0)
    assert all(
        scenario.parameter_source_id.startswith("author:") for scenario in scenarios
    )
    assert all(
        source.startswith("doi:10.1016/")
        for scenario in scenarios
        for source in scenario.evidence_source_ids
    )


@pytest.mark.parametrize(
    "scenario_id",
    ("low_grade_25", "balanced_50", "low_grade_75"),
)
def test_each_mt_candidate_is_calibrated_to_the_same_aggregate_retention(
    scenario_id: str,
) -> None:
    from tes_bess_boundary.tes_loss_calibration import (
        build_e0d9b_loss_scenarios,
        calibrate_loss_for_mt,
        full_charge_retention,
    )
    from tes_bess_boundary.tes_temperature_scenarios import (
        build_e0d8_hitec_normalized_mt_scenarios,
    )

    mt_point = build_e0d8_hitec_normalized_mt_scenarios().point(scenario_id)

    for scenario in build_e0d9b_loss_scenarios():
        calibration = calibrate_loss_for_mt(scenario, mt_point)
        assert full_charge_retention(
            mt_point,
            net_hourly_downgrade_fraction=(
                calibration.raw_hourly_downgrade_fraction
                * (1.0 - scenario.loss_compensation_fraction)
            ),
            hold_hours=scenario.hold_hours,
        ) == pytest.approx(scenario.target_full_charge_retention, abs=1e-12)


def test_balanced_mt_calibration_has_stable_numeric_gold_values() -> None:
    from tes_bess_boundary.tes_loss_calibration import (
        E0D9BLossLevel,
        build_e0d9b_loss_scenarios,
        calibrate_loss_for_mt,
    )
    from tes_bess_boundary.tes_temperature_scenarios import (
        build_e0d8_hitec_normalized_mt_scenarios,
    )

    point = build_e0d8_hitec_normalized_mt_scenarios().point("balanced_50")
    scenarios = {item.level: item for item in build_e0d9b_loss_scenarios()}

    low = calibrate_loss_for_mt(scenarios[E0D9BLossLevel.LOW], point)
    base = calibrate_loss_for_mt(scenarios[E0D9BLossLevel.BASE], point)
    high = calibrate_loss_for_mt(scenarios[E0D9BLossLevel.HIGH], point)

    assert low.net_hourly_downgrade_fraction == pytest.approx(
        0.0008333817208416305
    )
    assert base.net_hourly_downgrade_fraction == pytest.approx(
        0.001075710087939552
    )
    assert high.net_hourly_downgrade_fraction == pytest.approx(
        0.004048998475807808
    )
    assert low.raw_hourly_downgrade_fraction == pytest.approx(
        low.net_hourly_downgrade_fraction / 0.266
    )
    assert base.raw_hourly_downgrade_fraction == pytest.approx(
        base.net_hourly_downgrade_fraction / 0.266
    )
    assert high.raw_hourly_downgrade_fraction == pytest.approx(
        high.net_hourly_downgrade_fraction
    )


def test_pump_anchor_converts_aggregate_energy_only_after_throughput_is_known() -> None:
    from tes_bess_boundary.tes_loss_calibration import (
        build_trevisan_2022_aggregate_anchor,
    )

    anchor = build_trevisan_2022_aggregate_anchor()
    pump = anchor.aggregate_implied_uniform_pump_spec(
        total_salt_throughput_t=50_000.0
    )

    assert tuple(getattr(pump, field.name) for field in fields(pump)) == (
        pytest.approx((2.111,) * 5)
    )
    assert pump.electric_power_mw(
        electric_lt_to_ht_tph=10_000.0,
        steam_lt_to_ht_tph=10_000.0,
        steam_lt_to_mt_tph=10_000.0,
        power_ht_to_mt_tph=10_000.0,
        heat_mt_to_lt_tph=10_000.0,
    ) == pytest.approx(105.55)


@pytest.mark.parametrize("throughput", (0.0, -1.0, float("nan"), float("inf")))
def test_pump_anchor_rejects_invalid_throughput(throughput: float) -> None:
    from tes_bess_boundary.tes_loss_calibration import (
        build_trevisan_2022_aggregate_anchor,
    )

    with pytest.raises(ValueError, match="throughput"):
        build_trevisan_2022_aggregate_anchor().aggregate_implied_uniform_pump_spec(
            total_salt_throughput_t=throughput
        )


@pytest.mark.solver
@pytest.mark.parametrize(
    "scenario_id",
    ("low_grade_25", "balanced_50", "low_grade_75"),
)
def test_pyomo_inventory_matches_calibrated_24h_retention(scenario_id: str) -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, value

    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
        add_molten_salt_dispatch,
    )
    from tes_bess_boundary.tes_loss_auxiliary import (
        LossCompensationMode,
        TESLossAuxiliarySpec,
        TESParameterIdentity,
        TESPumpAuxiliarySpec,
    )
    from tes_bess_boundary.solver import create_highs_solver
    from tes_bess_boundary.tes_loss_calibration import (
        E0D9BLossLevel,
        build_e0d9b_loss_scenarios,
        calibrate_loss_for_mt,
    )
    from tes_bess_boundary.tes_temperature_scenarios import (
        build_e0d8_hitec_normalized_mt_scenarios,
    )

    mt_point = build_e0d8_hitec_normalized_mt_scenarios().point(scenario_id)
    scenario = next(
        item
        for item in build_e0d9b_loss_scenarios()
        if item.level is E0D9BLossLevel.BASE
    )
    calibration = calibrate_loss_for_mt(scenario, mt_point)
    physics = MoltenSaltPhysics(
        salt_mass_t=100.0,
        ht_tank_capacity_t=100.0,
        mt_tank_capacity_t=100.0,
        lt_tank_capacity_t=100.0,
        specific_heat_mwh_per_tonne_k=0.0004,
        temperature_ht=mt_point.temperature_ht_c,
        temperature_mt=mt_point.temperature_mt_c,
        temperature_lt=mt_point.temperature_lt_c,
        electric_heater_efficiency=0.99,
        steam_to_ht_efficiency=0.98,
        steam_to_mt_efficiency=0.98,
        power_block_efficiency=0.40,
        heat_exchanger_efficiency=0.95,
    )
    spec = TESLossAuxiliarySpec(
        ht_standing_loss_fraction_per_hour=(
            calibration.raw_hourly_downgrade_fraction
        ),
        mt_standing_loss_fraction_per_hour=(
            calibration.raw_hourly_downgrade_fraction
        ),
        ht_loss_compensation_fraction=scenario.loss_compensation_fraction,
        mt_loss_compensation_fraction=scenario.loss_compensation_fraction,
        tracing_heater_efficiency=1.0,
        pump=TESPumpAuxiliarySpec(0.0, 0.0, 0.0, 0.0, 0.0),
        compensation_mode=LossCompensationMode.FIXED_FRACTION,
        parameter_identity=TESParameterIdentity.AUTHOR_SENSITIVITY,
        parameter_source_id=(
            "author:e0-d-9b-pyomo-loss-cross-check-pump-unresolved-v1"
        ),
        evidence_source_ids=scenario.evidence_source_ids,
        reference_ambient_temperature_c=25.0,
    )

    model = ConcreteModel()
    model.periods = RangeSet(0, 23)
    model.tes = Block()
    add_molten_salt_dispatch(
        model.tes,
        model.periods,
        physics,
        initial_inventory=SaltInventory(100.0, 0.0, 0.0),
        loss_auxiliary=spec,
    )
    for name in (
        "electric_lt_to_ht",
        "steam_lt_to_ht",
        "steam_lt_to_mt",
        "power_ht_to_mt",
        "heat_mt_to_lt",
    ):
        flow = getattr(model.tes, name)
        for period in model.periods:
            flow[period].fix(0.0)
    model.objective = Objective(expr=0.0)

    result = create_highs_solver().solve(model)

    assert str(result.solver.termination_condition).lower() == "optimal"
    initial_energy = physics.total_stored_energy_mwh(
        SaltInventory(100.0, 0.0, 0.0)
    )
    final_inventory = SaltInventory(
        value(model.tes.ht_mass[24]),
        value(model.tes.mt_mass[24]),
        value(model.tes.lt_mass[24]),
    )
    assert physics.total_stored_energy_mwh(final_inventory) / initial_energy == (
        pytest.approx(scenario.target_full_charge_retention, abs=1e-10)
    )
