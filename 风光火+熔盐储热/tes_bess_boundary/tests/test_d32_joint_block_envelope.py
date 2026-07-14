from __future__ import annotations

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
            name="d32_fixture",
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
            service_id="d32_curtailment",
            maximum_curtailment_mwh=8_784.0,
        ),
        pcc_export_service=AnnualPCCExportServiceSpec(
            service_id="d32_pcc",
            target_export_mwh=8_784.0,
        ),
    )


def _admissibility() -> object:
    from tes_bess_boundary.alternative_dispatch_envelope import DispatchAdmissibility

    return DispatchAdmissibility(
        primary_cost_upper_bound_cny=1e-6,
        curtailment_upper_bound_mwh=8_784.0,
    )


def test_d32_preregistered_partition_is_contiguous() -> None:
    from tes_bess_boundary.d32_joint_block_envelope import partition_horizon

    blocks = partition_horizon(50, 24)

    assert [(item.start_period, item.stop_period) for item in blocks] == [
        (0, 24),
        (24, 48),
        (48, 50),
    ]


def test_d32_relaxes_primary_integers_but_keeps_only_block_signs() -> None:
    from pyomo.environ import Var

    from tes_bess_boundary.d32_joint_block_envelope import (
        BlockDefinition,
        build_joint_block_relaxation,
    )

    case = _synthetic_case()
    model, relaxed_count, sign_count = build_joint_block_relaxation(
        case,
        case,
        comparator_admissibility=_admissibility(),
        candidate_admissibility=_admissibility(),
        comparator_lower_mw=(0.0, 0.0),
        comparator_upper_mw=(2.0, 2.0),
        candidate_lower_mw=(0.0, 0.0),
        candidate_upper_mw=(2.0, 2.0),
        block=BlockDefinition(0, 0, 1),
    )

    assert relaxed_count > 0
    assert sign_count == 1
    assert hasattr(model.comparator.chp[0], "commitment_transition")
    assert hasattr(model.comparator, "annual_pcc_export_service")
    assert not any(
        variable.is_binary() or variable.is_integer()
        for architecture in (model.comparator, model.candidate)
        for variable in architecture.component_data_objects(
            Var, active=True, descend_into=True
        )
    )
    assert model.delta_nonnegative[0].is_binary()
    assert model.delta_nonnegative[1].fixed
    assert not model.d27_delta_decomposition[1].active


def test_d32_block_cut_uses_certified_protected_dual() -> None:
    from pyomo.environ import value

    from tes_bess_boundary.alternative_dispatch_envelope import (
        RedistributionDirection,
        build_joint_redistribution_model,
    )
    from tes_bess_boundary.d27_direction_generation import (
        _replace_big_m_with_disaggregated_sign_formulation,
    )
    from tes_bess_boundary.d32_joint_block_envelope import (
        add_joint_block_envelope_cuts,
    )

    case = _synthetic_case()
    model = build_joint_redistribution_model(
        case,
        case,
        comparator_admissibility=_admissibility(),
        candidate_admissibility=_admissibility(),
        direction=RedistributionDirection.MAXIMUM,
    )
    _replace_big_m_with_disaggregated_sign_formulation(
        model, pcc_capacity_mw=2.0
    )
    screen = {
        "block_results": [
            {
                "start_period": 0,
                "stop_period": 1,
                "protected_dual_bound_mwh": 4_392.001,
            },
            {
                "start_period": 1,
                "stop_period": 2,
                "protected_dual_bound_mwh": 4_392.001,
            },
        ]
    }

    count = add_joint_block_envelope_cuts(
        model,
        screen=screen,
        annual_weights=(4_392.0, 4_392.0),
        dt_hours=1.0,
    )

    assert count == 2
    assert len(model.d32_block_l1_upper) == 2
    model.absolute_delta_pcc_export_mw[0].set_value(2.0)
    assert value(model.d32_block_l1_upper[1].body) == pytest.approx(4_392.0)
    assert value(model.d32_block_l1_upper[1].upper) == pytest.approx(4_392.001)


@pytest.mark.solver
def test_d32_two_period_block_dual_is_exact() -> None:
    from tes_bess_boundary.d32_joint_block_envelope import (
        BlockDefinition,
        solve_joint_block_envelope,
    )

    case = _synthetic_case()
    result = solve_joint_block_envelope(
        case,
        case,
        comparator_admissibility=_admissibility(),
        candidate_admissibility=_admissibility(),
        comparator_lower_mw=(0.0, 0.0),
        comparator_upper_mw=(2.0, 2.0),
        candidate_lower_mw=(0.0, 0.0),
        candidate_upper_mw=(2.0, 2.0),
        block=BlockDefinition(0, 0, 1),
        time_limit_seconds=30.0,
        threads=1,
    )

    assert result.termination == "optimal"
    assert result.primal_bound_mwh == pytest.approx(4_392.0, abs=1e-6)
    assert result.dual_bound_mwh == pytest.approx(4_392.0, abs=1e-6)
    assert result.protected_dual_bound_mwh == pytest.approx(4_392.001, abs=1e-6)
    assert result.active_sign_binary_count == 1
