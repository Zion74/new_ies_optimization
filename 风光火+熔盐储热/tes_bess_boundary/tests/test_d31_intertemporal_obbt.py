from __future__ import annotations

from pathlib import Path

import pytest


def _synthetic_case() -> object:
    from tes_bess_boundary.components.chp import (
        CHPCommitmentSpec,
        CHPFeasibleRegion,
        CHPFuelPoint,
        CHPUnitSpec,
        CHPVertex,
        HeatBasis,
        LowLoadFuelRule,
    )
    from tes_bess_boundary.economics import AnnualEconomicsSpec, AnnualHorizonSpec
    from tes_bess_boundary.model import (
        AnnualCurtailmentServiceSpec,
        AnnualPCCExportServiceSpec,
        Architecture,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
    )

    chp = CHPCommitmentSpec(
        unit=CHPUnitSpec(
            name="d31_fixture",
            feasible_region=CHPFeasibleRegion(
                (
                    CHPVertex(10.0, 0.0),
                    CHPVertex(11.0, 0.0),
                    CHPVertex(10.0, 1.0),
                )
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.0,
        ),
        fuel_points=(CHPFuelPoint(10.0, 300.0), CHPFuelPoint(11.0, 300.0)),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
    )
    return E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(0.0, 0.0),
            wind_available_mw=(2.0, 2.0),
            pv_available_mw=(0.0, 0.0),
            dt_hours=1.0,
        ),
        chp_units=(chp,),
        chp_initial_online=(0,),
        chp_terminal_online=(0,),
        pcc_export_capacity_mw=2.0,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=0.0,
            curtailment_penalty_cny_per_mwh=0.0,
        ),
        economics=AnnualEconomicsSpec(
            horizon=AnnualHorizonSpec(period_weights=(4_392.0, 4_392.0))
        ),
        curtailment_service=AnnualCurtailmentServiceSpec(
            service_id="d31_curtailment",
            maximum_curtailment_mwh=8_784.0,
        ),
        pcc_export_service=AnnualPCCExportServiceSpec(
            service_id="d31_pcc",
            target_export_mwh=8_784.0,
        ),
    )


def _admissibility() -> object:
    from tes_bess_boundary.alternative_dispatch_envelope import DispatchAdmissibility

    return DispatchAdmissibility(
        primary_cost_upper_bound_cny=1e-6,
        curtailment_upper_bound_mwh=8_784.0,
    )


def test_d31_loads_locked_d30_reference() -> None:
    from tes_bess_boundary.d31_intertemporal_obbt import load_d30_obbt_reference

    source = (
        Path(__file__).resolve().parents[2]
        / "数据采集"
        / "e0d30_physics_service_bound_tightening"
    )
    reference = load_d30_obbt_reference(
        source,
        window_id="winter_day_20240101",
    )

    assert reference.hours == 24
    assert reference.strict_global_lower_bound_mwh == pytest.approx(26010.174929016)
    assert reference.strict_global_upper_bound_mwh == pytest.approx(26010.174929016)
    assert len(reference.comparator_lower_mw) == 24
    assert len(reference.candidate_upper_mw) == 24


def test_d31_relaxation_retains_intertemporal_and_admissibility_rows() -> None:
    from pyomo.environ import Var

    from tes_bess_boundary.d31_intertemporal_obbt import (
        build_intertemporal_obbt_relaxation,
    )

    model, integer_count = build_intertemporal_obbt_relaxation(
        _synthetic_case(),
        _admissibility(),
        d30_lower_mw=(0.0, 0.0),
        d30_upper_mw=(2.0, 2.0),
    )

    assert integer_count > 0
    assert hasattr(model, "d31_primary_cost_cap")
    assert hasattr(model, "d31_curtailment_cap")
    assert hasattr(model, "d31_service_curtailment_cap")
    assert hasattr(model.chp[0], "commitment_transition")
    assert not any(
        variable.is_binary() or variable.is_integer()
        for variable in model.component_data_objects(Var, active=True, descend_into=True)
    )


@pytest.mark.solver
def test_d31_two_period_obbt_is_exact_and_keeps_integer_witnesses() -> None:
    import highspy

    from tes_bess_boundary.d31_intertemporal_obbt import (
        _initialize_obbt_worker,
        _solve_obbt_period,
    )

    try:
        _initialize_obbt_worker(
            _synthetic_case(),
            _admissibility(),
            (0.0, 0.0),
            (2.0, 2.0),
        )
        result = _solve_obbt_period(0)
    finally:
        highspy.Highs.resetGlobalScheduler(True)

    assert result.minimum_mw == pytest.approx(0.0, abs=1e-8)
    assert result.maximum_mw == pytest.approx(2.0, abs=1e-8)
    assert result.relaxed_integer_variable_count > 0


def test_d31_protected_bounds_only_tighten_d30() -> None:
    from tes_bess_boundary.d31_intertemporal_obbt import (
        PeriodOBBTResult,
        _merge_architecture_bounds,
    )

    bounds = _merge_architecture_bounds(
        "fixture",
        (
            PeriodOBBTResult(0, 1.0, 4.0, 0.1, 0.1, 3),
            PeriodOBBTResult(1, 2.0, 5.0, 0.1, 0.1, 3),
        ),
        d30_lower_mw=(0.0, 1.0),
        d30_upper_mw=(6.0, 6.0),
        worker_count=1,
    )

    assert bounds.lower_mw == pytest.approx((0.9999, 1.9999))
    assert bounds.upper_mw == pytest.approx((4.0001, 5.0001))
    assert bounds.lp_solve_count == 4
    assert bounds.optimal_lp_solve_count == 4


def test_d31_worker_allocation_biases_the_harder_tes_relaxation() -> None:
    from tes_bess_boundary.d31_intertemporal_obbt import _worker_allocation

    comparator, candidate = _worker_allocation(28, 336)

    assert (comparator, candidate) == (4, 24)
