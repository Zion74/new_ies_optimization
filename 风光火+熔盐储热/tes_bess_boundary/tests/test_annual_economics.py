from __future__ import annotations

import pytest


pytestmark = [pytest.mark.solver, pytest.mark.integration]


def _synthetic_chp_spec(
    name: str,
    vertices: tuple[tuple[float, float], ...] = (
        (10.0, 0.0),
        (11.0, 0.0),
        (10.0, 1.0),
    ),
) -> object:
    from tes_bess_boundary.components.chp import (
        CHPCommitmentSpec,
        CHPFeasibleRegion,
        CHPFuelPoint,
        CHPUnitSpec,
        CHPVertex,
        HeatBasis,
        LowLoadFuelRule,
    )

    powers = tuple(power for power, _heat in vertices)
    return CHPCommitmentSpec(
        unit=CHPUnitSpec(
            name=name,
            feasible_region=CHPFeasibleRegion(
                tuple(CHPVertex(power, heat) for power, heat in vertices)
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.0,
        ),
        fuel_points=(
            CHPFuelPoint(min(powers), 300.0),
            CHPFuelPoint(max(powers), 300.0),
        ),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
    )


def test_annual_horizon_closes_scored_periods_to_8784_hours() -> None:
    from tes_bess_boundary.economics import AnnualHorizonSpec

    representative_day = AnnualHorizonSpec(period_weights=(366.0,) * 24)

    assert representative_day.weighted_hours(dt_hours=1.0) == pytest.approx(8784.0)
    representative_day.validate_time_grid(period_count=24, dt_hours=1.0)

    wrong_year = AnnualHorizonSpec(period_weights=(365.0,) * 24)
    with pytest.raises(ValueError, match="8784"):
        wrong_year.validate_time_grid(period_count=24, dt_hours=1.0)


def test_annual_objective_weights_each_operating_period_once() -> None:
    from tes_bess_boundary.economics import AnnualEconomicsSpec, AnnualHorizonSpec
    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
        solve_e0c,
    )

    unit = _synthetic_chp_spec("annual_weighting_fixture")
    case = E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(0.0, 0.0),
            wind_available_mw=(5.0, 5.0),
            pv_available_mw=(0.0, 0.0),
            dt_hours=0.5,
        ),
        chp_units=(unit,),
        chp_initial_online=(0,),
        chp_terminal_online=(0,),
        pcc_export_capacity_mw=0.0,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=0.0,
            curtailment_penalty_cny_per_mwh=2.0,
        ),
        economics=AnnualEconomicsSpec(
            horizon=AnnualHorizonSpec(period_weights=(8784.0, 8784.0))
        ),
    )

    result = solve_e0c(case)

    # Independent literal: 2 periods × 5 MW × 0.5 h × 8784 × 2 CNY/MWh.
    assert result.objective_value == pytest.approx(87_840.0)
    assert result.objective_basis == "annual_validation_cost_cny_per_year"
    assert result.annual_economics is not None
    assert result.annual_economics.weighted_hours == pytest.approx(8_784.0)
    assert result.annual_economics.weighted_curtailment_mwh == pytest.approx(43_920.0)
    # Solver audit fields retain their E0-C dispatch-horizon meaning.
    assert result.curtailment_mwh == pytest.approx(5.0)


def test_nonuniform_period_weights_apply_to_each_fuel_period_and_dt_once() -> None:
    from tes_bess_boundary.economics import AnnualEconomicsSpec, AnnualHorizonSpec
    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
        solve_e0c,
    )

    case = E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(1.0, 2.0, 3.0, 4.0),
            wind_available_mw=(0.0,) * 4,
            pv_available_mw=(0.0,) * 4,
            dt_hours=0.5,
        ),
        chp_units=(
            _synthetic_chp_spec(
                "nonuniform_fuel_fixture",
                vertices=((10.0, 0.0), (20.0, 0.0), (20.0, 10.0)),
            ),
        ),
        chp_initial_online=(1,),
        chp_terminal_online=(1,),
        pcc_export_capacity_mw=100.0,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=2.0,
            curtailment_penalty_cny_per_mwh=0.0,
        ),
        economics=AnnualEconomicsSpec(
            horizon=AnnualHorizonSpec(period_weights=(1000.0, 2000.0, 3000.0, 11_568.0))
        ),
    )

    result = solve_e0c(case)

    assert result.annual_economics is not None
    # Literal: 0.5 × (1000×3.3 + 2000×3.6 + 3000×3.9 + 11568×4.2).
    assert result.annual_economics.weighted_fuel_tce == pytest.approx(35_392.8)
    assert result.annual_economics.operating_cost_cny == pytest.approx(70_785.6)
    assert result.objective_value == pytest.approx(70_785.6)
    assert result.fuel_tce == pytest.approx(7.5)


def test_nonuniform_period_weights_apply_to_each_curtailment_period_once() -> None:
    from tes_bess_boundary.economics import AnnualEconomicsSpec, AnnualHorizonSpec
    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
        solve_e0c,
    )

    case = E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(0.0,) * 4,
            wind_available_mw=(1.0, 2.0, 3.0, 4.0),
            pv_available_mw=(0.0,) * 4,
            dt_hours=0.5,
        ),
        chp_units=(_synthetic_chp_spec("nonuniform_curtailment_fixture"),),
        chp_initial_online=(0,),
        chp_terminal_online=(0,),
        pcc_export_capacity_mw=0.0,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=0.0,
            curtailment_penalty_cny_per_mwh=3.0,
        ),
        economics=AnnualEconomicsSpec(
            horizon=AnnualHorizonSpec(period_weights=(1000.0, 2000.0, 3000.0, 11_568.0))
        ),
    )

    result = solve_e0c(case)

    assert result.annual_economics is not None
    # Literal: 0.5 × (1000×1 + 2000×2 + 3000×3 + 11568×4).
    assert result.annual_economics.weighted_curtailment_mwh == pytest.approx(30_136.0)
    assert result.annual_economics.operating_cost_cny == pytest.approx(90_408.0)
    assert result.curtailment_mwh == pytest.approx(5.0)


def test_annual_pcc_export_service_fixes_the_common_delivered_energy() -> None:
    from tes_bess_boundary.economics import AnnualEconomicsSpec, AnnualHorizonSpec
    from tes_bess_boundary.model import (
        AnnualPCCExportServiceSpec,
        Architecture,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
        solve_e0c,
    )

    target_export_mwh = 21_960.0
    case = E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(0.0, 0.0),
            wind_available_mw=(5.0, 5.0),
            pv_available_mw=(0.0, 0.0),
        ),
        chp_units=(_synthetic_chp_spec("annual_pcc_service_fixture"),),
        chp_initial_online=(0,),
        chp_terminal_online=(0,),
        pcc_export_capacity_mw=10.0,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=0.0,
            curtailment_penalty_cny_per_mwh=1.0,
        ),
        economics=AnnualEconomicsSpec(
            horizon=AnnualHorizonSpec(period_weights=(4_392.0, 4_392.0))
        ),
        pcc_export_service=AnnualPCCExportServiceSpec(
            service_id="same_flat_price_pcc_delivery",
            target_export_mwh=target_export_mwh,
        ),
    )

    result = solve_e0c(case)
    warmed_result = solve_e0c(
        case,
        pcc_service_feasibility_warm_start=True,
    )

    assert result.annual_economics is not None
    annual = result.annual_economics
    assert annual.weighted_pcc_export_mwh == pytest.approx(target_export_mwh)
    assert annual.weighted_curtailment_mwh == pytest.approx(21_960.0)
    assert annual.pcc_export_service_id == "same_flat_price_pcc_delivery"
    assert annual.pcc_export_target_mwh == pytest.approx(target_export_mwh)
    assert warmed_result.annual_economics is not None
    assert warmed_result.annual_economics.weighted_pcc_export_mwh == pytest.approx(
        target_export_mwh
    )
    assert warmed_result.pcc_service_feasibility_warm_start is True
    assert warmed_result.pcc_service_feasibility_deviation_mw == pytest.approx(
        0.0,
        abs=1e-12,
    )
    assert warmed_result.pcc_service_feasibility_runtime_seconds is not None
    assert warmed_result.pcc_service_feasibility_runtime_seconds >= 0.0


def test_annual_pcc_export_service_requires_an_annual_case() -> None:
    from tes_bess_boundary.model import (
        AnnualPCCExportServiceSpec,
        Architecture,
        E0CCase,
        E0CTimeSeries,
    )

    service = AnnualPCCExportServiceSpec(
        service_id="annual_only",
        target_export_mwh=1.0,
    )
    with pytest.raises(ValueError, match="annual PCC export service requires annual economics"):
        E0CCase(
            architecture=Architecture.NO_STORAGE,
            timeseries=E0CTimeSeries(
                heat_demand_mw=(0.0,),
                wind_available_mw=(0.0,),
                pv_available_mw=(0.0,),
            ),
            chp_units=(_synthetic_chp_spec("annual_pcc_service_guard"),),
            chp_initial_online=(0,),
            chp_terminal_online=(0,),
            pcc_export_capacity_mw=1.0,
            pcc_export_service=service,
        )

    with pytest.raises(ValueError, match="target export"):
        AnnualPCCExportServiceSpec(
            service_id="invalid_target",
            target_export_mwh=-1.0,
        )


def _bess_annual_case(wind_available_mw: tuple[float, ...]) -> object:
    from tes_bess_boundary.components.bess import BESSPhysics
    from tes_bess_boundary.economics import (
        AnnualEconomicsSpec,
        AnnualHorizonSpec,
        BESSCellDegradationSpec,
        FixedCapacityNonCellCost,
        InstalledAssetQuantity,
        LifecycleAssetClass,
        LifecycleCostSpec,
        ProjectFinance,
        build_lifecycle_cost_portfolio,
        calibrate_bess_cell_cost,
    )
    from tes_bess_boundary.model import (
        Architecture,
        BESSFixedSpec,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
    )

    finance = ProjectFinance(project_years=20, real_discount_rate=0.10)
    cell_spec = LifecycleCostSpec(
        asset_id="synthetic_cell",
        capacity_unit="MWh_internal",
        currency="CNY",
        price_base_year=2024,
        initial_cost_per_unit=100.0,
        service_life_years=10.0,
        asset_class=LifecycleAssetClass.BESS_CELL,
    )
    cell_cost = calibrate_bess_cell_cost(
        BESSCellDegradationSpec(
            cell_lifecycle=cell_spec,
            cycle_life_ac_efc=1000.0,
            reference_annual_ac_efc=100.0,
            ac_deliverable_fraction=0.8,
        ),
        finance,
    )
    non_cell_portfolio = build_lifecycle_cost_portfolio(
        (
            LifecycleCostSpec(
                asset_id="synthetic_bess_fom",
                capacity_unit="system",
                currency="CNY",
                price_base_year=2024,
                initial_cost_per_unit=0.0,
                service_life_years=20.0,
                fixed_om_per_unit_year=200.0,
                asset_class=LifecycleAssetClass.BESS_NON_CELL,
            ),
        ),
        finance,
        bess_cell_cost=cell_cost,
    )
    fixed_non_cell_cost = FixedCapacityNonCellCost(
        portfolio=non_cell_portfolio,
        quantities=(InstalledAssetQuantity("synthetic_bess_fom", 1.0),),
    )
    chp = _synthetic_chp_spec("bess_annual_fixture")
    return E0CCase(
        architecture=Architecture.BESS,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(0.0,) * 4,
            wind_available_mw=wind_available_mw,
            pv_available_mw=(0.0,) * 4,
            dt_hours=0.5,
        ),
        chp_units=(chp,),
        chp_initial_online=(0,),
        chp_terminal_online=(0,),
        pcc_export_capacity_mw=5.0,
        bess=BESSFixedSpec(
            physics=BESSPhysics(
                energy_capacity_mwh=220.0,
                charge_power_mw=6.25,
                discharge_power_mw=5.0,
                soc_min=0.0,
                soc_max=1.0,
                charge_efficiency=1.0,
                discharge_efficiency=0.8,
            ),
            initial_energy_mwh=0.0,
            cyclic=True,
        ),
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=0.0,
            curtailment_penalty_cny_per_mwh=1.0,
        ),
        economics=AnnualEconomicsSpec(
            horizon=AnnualHorizonSpec(period_weights=(4392.0,) * 4),
            non_cell_cost=fixed_non_cell_cost,
            bess_cell_cost=cell_cost,
        ),
    )


def test_bess_annual_cost_uses_canonical_fixed_eac_and_ac_discharge_once() -> None:
    from pyomo.environ import value

    from tes_bess_boundary.model import build_e0c_model, solve_e0c
    from tes_bess_boundary.solver import create_highs_solver

    case = _bess_annual_case((10.0, 10.0, 0.0, 0.0))
    model = build_e0c_model(case)
    result = create_highs_solver().solve(model)

    assert str(result.solver.termination_condition).lower() == "optimal"
    assert value(model.annual_bess_ac_discharge_throughput_mwh) == pytest.approx(
        17_568.0
    )
    assert value(model.annual_non_cell_fixed_eac_cny) == pytest.approx(200.0)
    assert value(model.annual_bess_calendar_cost_cny) == pytest.approx(
        3_580.39868741525
    )
    assert value(model.annual_bess_cycle_cost_cny) == pytest.approx(2_219.10380663265)
    assert value(model.annual_total_cost_cny) == pytest.approx(5_999.50249404791)

    public_result = solve_e0c(case)
    assert public_result.annual_economics is not None
    assert public_result.annual_economics.bess_ac_discharge_throughput_mwh == (
        pytest.approx(17_568.0)
    )
    assert public_result.annual_economics.non_cell_fixed_cost_cny == pytest.approx(
        200.0
    )
    assert public_result.annual_economics.bess_calendar_cost_cny == pytest.approx(
        3_580.39868741525
    )
    assert public_result.annual_economics.bess_cycle_cost_cny == pytest.approx(
        2_219.10380663265
    )
    assert public_result.objective_value == pytest.approx(5_999.50249404791)


def test_bess_annual_efc_limit_binds_on_the_same_ac_basis() -> None:
    from pyomo.environ import value

    from tes_bess_boundary.model import build_e0c_model
    from tes_bess_boundary.solver import create_highs_solver

    model = build_e0c_model(_bess_annual_case((11.25, 11.25, 0.0, 0.0)))
    result = create_highs_solver().solve(model)

    assert str(result.solver.termination_condition).lower() == "optimal"
    assert value(model.annual_bess_ac_throughput_limit_mwh) == pytest.approx(17_600.0)
    assert value(model.annual_bess_ac_discharge_throughput_mwh) == pytest.approx(
        17_600.0
    )
    assert value(model.annual_curtailment_mwh) == pytest.approx(5_450.0)
    assert value(model.annual_bess_cycle_cost_cny) == pytest.approx(2_223.14589006914)
    assert value(model.annual_total_cost_cny) == pytest.approx(11_453.5445774844)


def test_bess_variable_om_is_separate_and_charged_once_on_ac_discharge() -> None:
    from dataclasses import replace

    from pyomo.environ import value

    from tes_bess_boundary.economics import BESSVariableOMSpec
    from tes_bess_boundary.model import build_e0c_model, solve_e0c
    from tes_bess_boundary.solver import create_highs_solver

    base_case = _bess_annual_case((10.0, 10.0, 0.0, 0.0))
    assert base_case.economics is not None
    case = replace(
        base_case,
        economics=replace(
            base_case.economics,
            bess_variable_om=BESSVariableOMSpec(
                currency="CNY",
                price_base_year=2024,
                cost_per_ac_discharge_mwh=0.25,
            ),
        ),
    )
    model = build_e0c_model(case)
    result = create_highs_solver().solve(model)

    assert str(result.solver.termination_condition).lower() == "optimal"
    assert value(model.annual_bess_ac_discharge_throughput_mwh) == pytest.approx(
        17_568.0
    )
    assert value(model.annual_bess_cycle_cost_cny) == pytest.approx(2_219.10380663265)
    assert value(model.annual_bess_variable_om_cost_cny) == pytest.approx(4_392.0)
    assert value(model.annual_total_cost_cny) == pytest.approx(10_391.50249404791)

    public_result = solve_e0c(case)
    assert public_result.annual_economics is not None
    assert public_result.annual_economics.bess_variable_om_cost_cny == pytest.approx(
        4_392.0
    )
    assert public_result.objective_value == pytest.approx(10_391.50249404791)


def test_none_economics_preserves_the_exact_e0c_public_boundary() -> None:
    from dataclasses import asdict

    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        build_e0c_model,
        solve_e0c,
    )

    chp = _synthetic_chp_spec("legacy_boundary_fixture")
    common = dict(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(0.0,),
            wind_available_mw=(5.0,),
            pv_available_mw=(7.0,),
        ),
        chp_units=(chp,),
        chp_initial_online=(0,),
        pcc_export_capacity_mw=8.0,
    )
    omitted_case = E0CCase(**common)
    explicit_none_case = E0CCase(economics=None, **common)

    legacy_model = build_e0c_model(omitted_case)
    assert not any(name.startswith("annual_") for name in legacy_model.component_map())

    omitted = solve_e0c(omitted_case)
    explicit_none = solve_e0c(explicit_none_case)

    assert omitted.objective_value == pytest.approx(4.0)
    assert omitted.objective_basis == "dispatch_validation_cost"
    assert omitted.annual_economics is None
    assert omitted.fuel_tce == pytest.approx(0.0)
    assert omitted.curtailment_mwh == pytest.approx(4.0)
    assert omitted.pcc_export_mwh == pytest.approx(8.0)
    omitted_audit = asdict(omitted)
    explicit_none_audit = asdict(explicit_none)
    omitted_audit.pop("runtime_seconds")
    explicit_none_audit.pop("runtime_seconds")
    assert explicit_none_audit == omitted_audit


def test_annual_horizon_is_immutable_and_strictly_scores_every_period() -> None:
    from tes_bess_boundary.economics import AnnualHorizonSpec

    with pytest.raises(ValueError, match="immutable tuple"):
        AnnualHorizonSpec(period_weights=[8784.0])  # type: ignore[arg-type]
    for invalid_weights in (
        (-1.0, 8785.0),
        (float("nan"), 8784.0),
        (float("inf"), 8784.0),
        (0.0, 8784.0),
        (0.0, 0.0),
        (True, 8783.0),
    ):
        with pytest.raises(ValueError, match="period_weights"):
            AnnualHorizonSpec(period_weights=invalid_weights)
    with pytest.raises(ValueError, match="expected_annual_hours"):
        AnnualHorizonSpec(period_weights=(1.0,), expected_annual_hours=0.0)
    with pytest.raises(ValueError, match="8784"):
        AnnualHorizonSpec(period_weights=(8760.0,), expected_annual_hours=8760.0)
    horizon = AnnualHorizonSpec(period_weights=(366.0,) * 24)
    with pytest.raises(ValueError, match="one value per dispatch period"):
        horizon.validate_time_grid(period_count=23, dt_hours=1.0)
    with pytest.raises(ValueError, match="8784"):
        AnnualHorizonSpec(
            period_weights=(366.0,) * 23 + (365.999,),
        ).validate_time_grid(period_count=24, dt_hours=1.0)


def test_annual_economics_requires_constant_2024_cny_inputs() -> None:
    from tes_bess_boundary.economics import (
        AnnualEconomicsSpec,
        AnnualHorizonSpec,
        FixedCapacityNonCellCost,
        InstalledAssetQuantity,
        LifecycleAssetClass,
        LifecycleCostSpec,
        ProjectFinance,
        build_lifecycle_cost_portfolio,
    )

    portfolio = build_lifecycle_cost_portfolio(
        (
            LifecycleCostSpec(
                asset_id="tes_2025_cost",
                capacity_unit="MWh_th",
                currency="CNY",
                price_base_year=2025,
                initial_cost_per_unit=100.0,
                service_life_years=20.0,
                asset_class=LifecycleAssetClass.TES_COMPONENT,
            ),
        ),
        ProjectFinance(project_years=20, real_discount_rate=0.05),
    )
    binding = FixedCapacityNonCellCost(
        portfolio=portfolio,
        quantities=(InstalledAssetQuantity("tes_2025_cost", 1.0),),
    )

    with pytest.raises(ValueError, match="constant 2024 CNY"):
        AnnualEconomicsSpec(
            horizon=AnnualHorizonSpec(period_weights=(8784.0,)),
            non_cell_cost=binding,
        )


def test_annual_bess_contract_rejects_missing_or_mismatched_cell_economics() -> None:
    from dataclasses import replace

    from tes_bess_boundary.economics import AnnualEconomicsSpec
    from tes_bess_boundary.model import Architecture

    case = _bess_annual_case((10.0, 10.0, 0.0, 0.0))
    assert case.bess is not None
    assert case.economics is not None

    with pytest.raises(ValueError, match="requires one canonical BESS cell cost"):
        replace(
            case,
            economics=AnnualEconomicsSpec(horizon=case.economics.horizon),
        )

    mismatched_physics = replace(case.bess.physics, discharge_efficiency=0.9)
    with pytest.raises(ValueError, match="AC deliverable fraction"):
        replace(case, bess=replace(case.bess, physics=mismatched_physics))

    with pytest.raises(ValueError, match="cyclic BESS boundary"):
        replace(case, bess=replace(case.bess, cyclic=False))

    with pytest.raises(ValueError, match="closed CHP status boundary"):
        replace(case, chp_terminal_online=None)

    with pytest.raises(ValueError, match="cycle-event cost proxy"):
        replace(
            case,
            chp_terminal_online=(0,),
            objective=replace(case.objective, cycle_event_cost_proxy_cny=1.0),
        )

    no_storage = replace(
        case,
        architecture=Architecture.NO_STORAGE,
        bess=None,
        economics=None,
    )
    with pytest.raises(ValueError, match="disabled BESS cell cost"):
        replace(no_storage, economics=case.economics)


def test_bess_ac_fraction_includes_both_efficiency_and_soc_window_once() -> None:
    from dataclasses import replace

    from pyomo.environ import value

    from tes_bess_boundary.economics import (
        BESSCellCostCalibration,
        calibrate_bess_cell_cost,
    )
    from tes_bess_boundary.model import build_e0c_model

    base = _bess_annual_case((10.0, 10.0, 0.0, 0.0))
    assert base.bess is not None
    assert base.economics is not None
    original = base.economics.bess_cell_cost
    assert isinstance(original, BESSCellCostCalibration)
    seventy_two_percent = calibrate_bess_cell_cost(
        replace(original.degradation, ac_deliverable_fraction=0.72),
        original.finance,
    )
    narrowed_physics = replace(
        base.bess.physics,
        soc_min=0.1,
        soc_max=0.9,
        discharge_efficiency=0.9,
    )
    narrowed_case = replace(
        base,
        bess=replace(
            base.bess,
            physics=narrowed_physics,
            initial_energy_mwh=22.0,
        ),
        economics=replace(base.economics, bess_cell_cost=seventy_two_percent),
    )

    model = build_e0c_model(narrowed_case)

    # Literal: 100 EFC/a × 0.9 ηd × (0.9-0.1) SOC × 220 MWh.
    assert value(model.annual_bess_ac_throughput_limit_mwh) == pytest.approx(15_840.0)
    with pytest.raises(ValueError, match="AC deliverable fraction"):
        replace(
            narrowed_case,
            bess=replace(
                narrowed_case.bess,
                physics=replace(narrowed_physics, soc_max=1.0),
            ),
        )


def test_nonuniform_period_weights_apply_to_each_ac_discharge_period_once() -> None:
    from dataclasses import replace

    from tes_bess_boundary.economics import (
        AnnualHorizonSpec,
        BESSCellCostCalibration,
        calibrate_bess_cell_cost,
    )
    from tes_bess_boundary.model import E0CTimeSeries, solve_e0c

    base = _bess_annual_case((10.0, 8.0, 0.0, 0.0))
    assert base.bess is not None
    assert base.economics is not None
    original = base.economics.bess_cell_cost
    assert isinstance(original, BESSCellCostCalibration)
    unit_ac_fraction = calibrate_bess_cell_cost(
        replace(original.degradation, ac_deliverable_fraction=1.0),
        original.finance,
    )
    case = replace(
        base,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(0.0,) * 4,
            wind_available_mw=(10.0, 8.0, 0.0, 0.0),
            pv_available_mw=(0.0,) * 4,
            dt_hours=1.0,
        ),
        bess=replace(
            base.bess,
            physics=replace(
                base.bess.physics,
                charge_power_mw=5.0,
                discharge_power_mw=5.0,
                discharge_efficiency=1.0,
            ),
        ),
        objective=replace(
            base.objective,
            curtailment_penalty_cny_per_mwh=10.0,
        ),
        economics=replace(
            base.economics,
            horizon=AnnualHorizonSpec(period_weights=(3000.0, 2784.0, 1000.0, 2000.0)),
            bess_cell_cost=unit_ac_fraction,
        ),
    )

    result = solve_e0c(case)

    assert result.annual_economics is not None
    # Physical discharge is 5 MWh then 3 MWh; annual AC basis is 1000×5+2000×3.
    assert result.annual_economics.bess_ac_discharge_throughput_mwh == (
        pytest.approx(11_000.0)
    )
    assert result.annual_economics.bess_ac_discharge_limit_mwh == pytest.approx(
        22_000.0
    )
    assert result.annual_economics.weighted_curtailment_mwh == pytest.approx(0.0)


def test_annual_non_cell_binding_blocks_cell_double_count_and_architecture_leakage() -> (
    None
):
    from dataclasses import replace

    from tes_bess_boundary.economics import (
        AnnualEconomicsSpec,
        BESSCellCostCalibration,
        FixedCapacityNonCellCost,
        InstalledAssetQuantity,
        LifecycleAssetClass,
        LifecycleCostSpec,
        build_lifecycle_cost_portfolio,
    )

    case = _bess_annual_case((10.0, 10.0, 0.0, 0.0))
    assert case.economics is not None
    cell = case.economics.bess_cell_cost
    assert isinstance(cell, BESSCellCostCalibration)
    duplicate_id_portfolio = build_lifecycle_cost_portfolio(
        (
            LifecycleCostSpec(
                asset_id=cell.cell_asset_id,
                capacity_unit="system",
                currency="CNY",
                price_base_year=2024,
                initial_cost_per_unit=1.0,
                service_life_years=20.0,
                asset_class=LifecycleAssetClass.BESS_NON_CELL,
            ),
        ),
        cell.finance,
    )
    duplicate_binding = FixedCapacityNonCellCost(
        portfolio=duplicate_id_portfolio,
        quantities=(InstalledAssetQuantity(cell.cell_asset_id, 1.0),),
    )
    with pytest.raises(ValueError, match="double count"):
        AnnualEconomicsSpec(
            horizon=case.economics.horizon,
            non_cell_cost=duplicate_binding,
            bess_cell_cost=cell,
        )

    tes_portfolio = build_lifecycle_cost_portfolio(
        (
            LifecycleCostSpec(
                asset_id="synthetic_tes_heater",
                capacity_unit="MW",
                currency="CNY",
                price_base_year=2024,
                initial_cost_per_unit=1.0,
                service_life_years=20.0,
                asset_class=LifecycleAssetClass.TES_COMPONENT,
            ),
        ),
        cell.finance,
        bess_cell_cost=cell,
    )
    tes_binding = FixedCapacityNonCellCost(
        portfolio=tes_portfolio,
        quantities=(InstalledAssetQuantity("synthetic_tes_heater", 1.0),),
    )
    with pytest.raises(ValueError, match="asset classes"):
        replace(
            case,
            economics=AnnualEconomicsSpec(
                horizon=case.economics.horizon,
                non_cell_cost=tes_binding,
                bess_cell_cost=cell,
            ),
        )


def test_fixed_life_sensitivity_keeps_the_same_annual_efc_feasible_set() -> None:
    from dataclasses import replace

    from pyomo.environ import value

    from tes_bess_boundary.economics import (
        AnnualEconomicsSpec,
        BESSCellCostCalibration,
        fixed_life_bess_cell_cost_from_calibration,
    )
    from tes_bess_boundary.model import build_e0c_model
    from tes_bess_boundary.solver import create_highs_solver

    case = _bess_annual_case((11.25, 11.25, 0.0, 0.0))
    assert case.economics is not None
    calibration = case.economics.bess_cell_cost
    assert isinstance(calibration, BESSCellCostCalibration)
    fixed_life = fixed_life_bess_cell_cost_from_calibration(calibration)
    fixed_life_economics = AnnualEconomicsSpec(
        horizon=case.economics.horizon,
        non_cell_cost=case.economics.non_cell_cost,
        bess_cell_cost=fixed_life,
    )

    model = build_e0c_model(replace(case, economics=fixed_life_economics))
    result = create_highs_solver().solve(model)

    assert str(result.solver.termination_condition).lower() == "optimal"
    assert value(model.annual_bess_ac_discharge_throughput_mwh) == pytest.approx(
        17_600.0
    )
    assert value(model.annual_bess_cycle_cost_cny) == pytest.approx(0.0)
    assert value(model.annual_total_cost_cny) == pytest.approx(9_230.39868741525)


def test_tes_electric_output_requires_explicit_generation_cost_classification() -> None:
    from dataclasses import replace

    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
    )
    from tes_bess_boundary.economics import (
        AnnualEconomicsSpec,
        FixedCapacityNonCellCost,
        InstalledAssetQuantity,
        LifecycleAssetClass,
        LifecycleCostSpec,
        build_lifecycle_cost_portfolio,
    )
    from tes_bess_boundary.model import Architecture, TESFixedSpec, TESPortCaps

    base = _bess_annual_case((10.0, 10.0, 0.0, 0.0))
    assert base.economics is not None
    tes = TESFixedSpec(
        physics=MoltenSaltPhysics(
            salt_mass_t=100.0,
            ht_tank_capacity_t=100.0,
            mt_tank_capacity_t=100.0,
            lt_tank_capacity_t=100.0,
            specific_heat_mwh_per_tonne_k=1.0,
            temperature_ht=3.0,
            temperature_mt=2.0,
            temperature_lt=1.0,
            electric_heater_efficiency=1.0,
            steam_to_ht_efficiency=1.0,
            steam_to_mt_efficiency=1.0,
            power_block_efficiency=1.0,
            heat_exchanger_efficiency=1.0,
        ),
        initial_inventory=SaltInventory(0.0, 0.0, 100.0),
        port_caps=TESPortCaps(10.0, 10.0, 10.0, 10.0, 10.0),
        cyclic=True,
    )
    unclassified = build_lifecycle_cost_portfolio(
        (
            LifecycleCostSpec(
                asset_id="unclassified_tes_cost",
                capacity_unit="system",
                currency="CNY",
                price_base_year=2024,
                initial_cost_per_unit=1.0,
                service_life_years=20.0,
                asset_class=LifecycleAssetClass.TES_COMPONENT,
            ),
        ),
        base.economics.non_cell_cost.portfolio.finance,
    )
    economics = AnnualEconomicsSpec(
        horizon=base.economics.horizon,
        non_cell_cost=FixedCapacityNonCellCost(
            portfolio=unclassified,
            quantities=(InstalledAssetQuantity("unclassified_tes_cost", 1.0),),
        ),
    )

    with pytest.raises(
        ValueError,
        match="TES electric output requires explicit generation cost classification",
    ):
        replace(
            base,
            architecture=Architecture.TES,
            bess=None,
            tes=tes,
            economics=economics,
        )

    classified = build_lifecycle_cost_portfolio(
        (
            LifecycleCostSpec(
                asset_id="zero_quantity_generator",
                capacity_unit="system",
                currency="CNY",
                price_base_year=2024,
                initial_cost_per_unit=0.0,
                service_life_years=20.0,
                asset_class=LifecycleAssetClass.SALT_TO_STEAM_GENERATOR,
            ),
            LifecycleCostSpec(
                asset_id="reuse_marker",
                capacity_unit="system",
                currency="CNY",
                price_base_year=2024,
                initial_cost_per_unit=0.0,
                service_life_years=20.0,
                asset_class=LifecycleAssetClass.EXISTING_TURBINE_REUSE,
            ),
        ),
        base.economics.non_cell_cost.portfolio.finance,
    )
    zero_quantity_economics = AnnualEconomicsSpec(
        horizon=base.economics.horizon,
        non_cell_cost=FixedCapacityNonCellCost(
            portfolio=classified,
            quantities=(
                InstalledAssetQuantity("zero_quantity_generator", 0.0),
                InstalledAssetQuantity("reuse_marker", 1.0),
            ),
        ),
    )
    with pytest.raises(ValueError, match="strictly positive installed quantities"):
        replace(
            base,
            architecture=Architecture.TES,
            bess=None,
            tes=tes,
            economics=zero_quantity_economics,
        )

    heat_only = replace(
        base,
        architecture=Architecture.TES,
        bess=None,
        tes=replace(
            tes,
            port_caps=replace(tes.port_caps, electric_output_mw=0.0),
        ),
        economics=economics,
    )
    assert heat_only.tes is not None


def test_tes_and_hybrid_annual_portfolios_remain_linear_and_count_once() -> None:
    from dataclasses import replace

    from pyomo.core import Constraint, Objective
    from pyomo.environ import value
    from pyomo.repn.standard_repn import generate_standard_repn

    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
    )
    from tes_bess_boundary.economics import (
        AnnualEconomicsSpec,
        BESSCellCostCalibration,
        FixedCapacityNonCellCost,
        InstalledAssetQuantity,
        LifecycleAssetClass,
        LifecycleCostSpec,
        build_lifecycle_cost_portfolio,
    )
    from tes_bess_boundary.model import (
        Architecture,
        TESFixedSpec,
        TESPortCaps,
        build_e0c_model,
    )

    base = _bess_annual_case((10.0, 10.0, 0.0, 0.0))
    assert base.economics is not None
    cell = base.economics.bess_cell_cost
    assert isinstance(cell, BESSCellCostCalibration)
    tes = TESFixedSpec(
        physics=MoltenSaltPhysics(
            salt_mass_t=100.0,
            ht_tank_capacity_t=100.0,
            mt_tank_capacity_t=100.0,
            lt_tank_capacity_t=100.0,
            specific_heat_mwh_per_tonne_k=1.0,
            temperature_ht=3.0,
            temperature_mt=2.0,
            temperature_lt=1.0,
            electric_heater_efficiency=1.0,
            steam_to_ht_efficiency=1.0,
            steam_to_mt_efficiency=1.0,
            power_block_efficiency=1.0,
            heat_exchanger_efficiency=1.0,
        ),
        initial_inventory=SaltInventory(0.0, 0.0, 100.0),
        port_caps=TESPortCaps(10.0, 10.0, 10.0, 10.0, 10.0),
        cyclic=True,
    )
    portfolio = build_lifecycle_cost_portfolio(
        (
            LifecycleCostSpec(
                asset_id="hybrid_bess_fom",
                capacity_unit="system",
                currency="CNY",
                price_base_year=2024,
                initial_cost_per_unit=0.0,
                service_life_years=20.0,
                fixed_om_per_unit_year=200.0,
                asset_class=LifecycleAssetClass.BESS_NON_CELL,
            ),
            LifecycleCostSpec(
                asset_id="hybrid_tes_fom",
                capacity_unit="system",
                currency="CNY",
                price_base_year=2024,
                initial_cost_per_unit=0.0,
                service_life_years=20.0,
                fixed_om_per_unit_year=300.0,
                asset_class=LifecycleAssetClass.TES_COMPONENT,
            ),
            LifecycleCostSpec(
                asset_id="hybrid_salt_to_steam_generator",
                capacity_unit="system",
                currency="CNY",
                price_base_year=2024,
                initial_cost_per_unit=0.0,
                service_life_years=20.0,
                asset_class=LifecycleAssetClass.SALT_TO_STEAM_GENERATOR,
            ),
            LifecycleCostSpec(
                asset_id="hybrid_existing_turbine_reuse",
                capacity_unit="system",
                currency="CNY",
                price_base_year=2024,
                initial_cost_per_unit=0.0,
                service_life_years=20.0,
                asset_class=LifecycleAssetClass.EXISTING_TURBINE_REUSE,
            ),
        ),
        cell.finance,
        bess_cell_cost=cell,
    )
    hybrid_binding = FixedCapacityNonCellCost(
        portfolio=portfolio,
        quantities=(
            InstalledAssetQuantity("hybrid_tes_fom", 1.0),
            InstalledAssetQuantity("hybrid_bess_fom", 1.0),
            InstalledAssetQuantity("hybrid_salt_to_steam_generator", 1.0),
            InstalledAssetQuantity("hybrid_existing_turbine_reuse", 1.0),
        ),
    )
    hybrid = replace(
        base,
        architecture=Architecture.HYBRID,
        tes=tes,
        economics=AnnualEconomicsSpec(
            horizon=base.economics.horizon,
            non_cell_cost=hybrid_binding,
            bess_cell_cost=cell,
        ),
    )
    tes_specs = tuple(
        ledger.spec
        for ledger in portfolio.ledgers
        if ledger.spec.asset_class is not LifecycleAssetClass.BESS_NON_CELL
    )
    tes_portfolio = build_lifecycle_cost_portfolio(tes_specs, cell.finance)
    tes_only = replace(
        base,
        architecture=Architecture.TES,
        bess=None,
        tes=tes,
        economics=AnnualEconomicsSpec(
            horizon=base.economics.horizon,
            non_cell_cost=FixedCapacityNonCellCost(
                portfolio=tes_portfolio,
                quantities=(
                    InstalledAssetQuantity("hybrid_tes_fom", 1.0),
                    InstalledAssetQuantity("hybrid_salt_to_steam_generator", 1.0),
                    InstalledAssetQuantity("hybrid_existing_turbine_reuse", 1.0),
                ),
            ),
        ),
    )

    tes_model = build_e0c_model(tes_only)
    hybrid_model = build_e0c_model(hybrid)

    assert value(tes_model.annual_non_cell_fixed_eac_cny) == pytest.approx(300.0)
    assert value(hybrid_model.annual_non_cell_fixed_eac_cny) == pytest.approx(500.0)
    for model in (tes_model, hybrid_model):
        for constraint in model.component_data_objects(Constraint, active=True):
            assert generate_standard_repn(constraint.body).is_linear()
        for objective in model.component_data_objects(Objective, active=True):
            assert generate_standard_repn(objective.expr).is_linear()
