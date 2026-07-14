from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import shutil

import pytest


pytestmark = [pytest.mark.solver, pytest.mark.integration]


def _synthetic_chp_spec() -> object:
    from tes_bess_boundary.components.chp import (
        CHPCommitmentSpec,
        CHPFeasibleRegion,
        CHPFuelPoint,
        CHPUnitSpec,
        CHPVertex,
        HeatBasis,
        LowLoadFuelRule,
    )

    return CHPCommitmentSpec(
        unit=CHPUnitSpec(
            name="alternative_dispatch_fixture",
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


def _alternate_dispatch_case() -> object:
    from tes_bess_boundary.economics import AnnualEconomicsSpec, AnnualHorizonSpec
    from tes_bess_boundary.model import (
        AnnualCurtailmentServiceSpec,
        AnnualPCCExportServiceSpec,
        Architecture,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
    )

    return E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(0.0, 0.0),
            wind_available_mw=(2.0, 2.0),
            pv_available_mw=(0.0, 0.0),
            dt_hours=1.0,
        ),
        chp_units=(_synthetic_chp_spec(),),
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
            service_id="alternate_dispatch_curtailment",
            maximum_curtailment_mwh=8_784.0,
        ),
        pcc_export_service=AnnualPCCExportServiceSpec(
            service_id="alternate_dispatch_pcc",
            target_export_mwh=8_784.0,
        ),
    )


def test_joint_model_finds_exact_minimum_and_maximum_redistribution() -> None:
    from pyomo.environ import value

    from tes_bess_boundary.alternative_dispatch_envelope import (
        DispatchAdmissibility,
        RedistributionDirection,
        _seed_joint_model,
        build_joint_redistribution_model,
        solve_joint_redistribution,
    )
    from tes_bess_boundary.model import build_e0c_model
    from tes_bess_boundary.solver import create_highs_solver

    case = _alternate_dispatch_case()
    admissibility = DispatchAdmissibility(
        primary_cost_upper_bound_cny=1e-6,
        curtailment_upper_bound_mwh=8_784.0,
    )

    minimum = build_joint_redistribution_model(
        case,
        case,
        comparator_admissibility=admissibility,
        candidate_admissibility=admissibility,
        direction=RedistributionDirection.MINIMUM,
    )
    minimum_result = create_highs_solver().solve(minimum)
    assert str(minimum_result.solver.termination_condition).lower() == "optimal"
    assert value(minimum.redistribution_objective) == pytest.approx(0.0)

    maximum = build_joint_redistribution_model(
        case,
        case,
        comparator_admissibility=admissibility,
        candidate_admissibility=admissibility,
        direction=RedistributionDirection.MAXIMUM,
    )
    selected = build_e0c_model(case)
    create_highs_solver().solve(selected)
    _seed_joint_model(maximum, selected, selected)
    maximum_result = solve_joint_redistribution(
        maximum,
        direction=RedistributionDirection.MAXIMUM,
        mip_rel_gap=0.0,
        time_limit_seconds=60.0,
        threads=1,
        warm_start=True,
    )
    assert maximum_result.termination == "optimal"
    assert maximum_result.primal_bound_mwh == pytest.approx(8_784.0)
    assert maximum_result.dual_bound_mwh == pytest.approx(8_784.0)
    assert maximum_result.relative_gap == pytest.approx(0.0)
    assert maximum_result.comparator_pcc_export_mwh == pytest.approx(8_784.0)
    assert maximum_result.candidate_pcc_export_mwh == pytest.approx(8_784.0)
    assert value(maximum.redistribution_objective) == pytest.approx(8_784.0)
    assert value(maximum.comparator.annual_pcc_export_mwh) == pytest.approx(8_784.0)
    assert value(maximum.candidate.annual_pcc_export_mwh) == pytest.approx(8_784.0)
    assert value(maximum.comparator.annual_total_cost_cny) <= 1e-6
    assert value(maximum.candidate.annual_total_cost_cny) <= 1e-6


def test_legacy_bounds_are_interpreted_by_objective_direction() -> None:
    from tes_bess_boundary.alternative_dispatch_envelope import (
        RedistributionDirection,
        legacy_primal_dual_bounds,
    )

    results = SimpleNamespace(
        problem=SimpleNamespace(lower_bound=90.0, upper_bound=110.0)
    )

    minimum = legacy_primal_dual_bounds(
        results, RedistributionDirection.MINIMUM
    )
    maximum = legacy_primal_dual_bounds(
        results, RedistributionDirection.MAXIMUM
    )

    assert minimum == pytest.approx((110.0, 90.0))
    assert maximum == pytest.approx((90.0, 110.0))


@pytest.mark.parametrize(
    ("cost_cap", "curtailment_cap", "message"),
    [
        (float("nan"), 1.0, "primary cost"),
        (-1.0, 1.0, "primary cost"),
        (1.0, float("inf"), "curtailment"),
        (1.0, -1.0, "curtailment"),
    ],
)
def test_dispatch_admissibility_rejects_invalid_caps(
    cost_cap: float, curtailment_cap: float, message: str
) -> None:
    from tes_bess_boundary.alternative_dispatch_envelope import (
        DispatchAdmissibility,
    )

    with pytest.raises(ValueError, match=message):
        DispatchAdmissibility(
            primary_cost_upper_bound_cny=cost_cap,
            curtailment_upper_bound_mwh=curtailment_cap,
        )


def _canonical_source_dirs() -> tuple[Path, Path]:
    data_dir = Path(__file__).resolve().parents[2] / "数据采集"
    return (
        data_dir / "e0d19_same_pcc_service",
        data_dir / "e0d22_pcc_settlement_exposure",
    )


def test_d23_source_lock_loads_d19_caps_and_d22_selected_exposure() -> None:
    from tes_bess_boundary.alternative_dispatch_envelope import (
        load_e0d23_source_rows,
    )

    d19_dir, d22_dir = _canonical_source_dirs()
    d19_rows, d22_rows = load_e0d23_source_rows(d19_dir, d22_dir)

    assert set(d19_rows) == {
        "winter_day_20240101",
        "winter_fortnight_20240101",
    }
    assert set(d22_rows) == set(d19_rows)
    assert float(d19_rows["winter_day_20240101"]["pcc_export_target_mwh"]) == (
        pytest.approx(4_656_918.486026)
    )
    assert float(d22_rows["winter_day_20240101"]["redistributed_export_mwh"]) == (
        pytest.approx(26_010.174917694)
    )


def test_d23_source_lock_rejects_tampered_d22_exposure(tmp_path: Path) -> None:
    from tes_bess_boundary.alternative_dispatch_envelope import (
        load_e0d23_source_rows,
    )

    canonical_d19, canonical_d22 = _canonical_source_dirs()
    copied_d19 = tmp_path / "d19"
    copied_d22 = tmp_path / "d22"
    shutil.copytree(canonical_d19, copied_d19)
    shutil.copytree(canonical_d22, copied_d22)
    exposure = copied_d22 / "e0d22_settlement_exposure.csv"
    exposure.write_text(
        exposure.read_text(encoding="utf-8").replace(
            "26010.174917694", "26010.174917695", 1
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="D22 exposure hash"):
        load_e0d23_source_rows(copied_d19, copied_d22)


@pytest.mark.parametrize(
    ("direction_name", "expected_mwh"),
    [("minimum", 0.0), ("maximum", 8_784.0)],
)
def test_d26_strict_probe_recomputes_the_pcc_l1_certificate(
    direction_name: str, expected_mwh: float
) -> None:
    from tes_bess_boundary.alternative_dispatch_envelope import (
        DispatchAdmissibility,
        RedistributionDirection,
        build_joint_redistribution_model,
    )
    from tes_bess_boundary.d26_numerical_certification import (
        STRICT_FEASIBILITY_TOLERANCE,
        IntegerScope,
        _strict_solve,
    )
    from tes_bess_boundary.e0d17_exploration import DEFAULT_WINDOWS

    case = _alternate_dispatch_case()
    cap = DispatchAdmissibility(
        primary_cost_upper_bound_cny=1e-6,
        curtailment_upper_bound_mwh=8_784.0,
    )
    direction = RedistributionDirection(direction_name)
    model = build_joint_redistribution_model(
        case,
        case,
        comparator_admissibility=cap,
        candidate_admissibility=cap,
        direction=direction,
    )

    result = _strict_solve(
        model,
        comparator_case=case,
        candidate_case=case,
        comparator_cap=cap,
        candidate_cap=cap,
        pcc_service=case.pcc_export_service,
        window=DEFAULT_WINDOWS[0],
        scope=IntegerScope.REOPENED,
        direction=direction,
        fixed_primary_integer_count=0,
        warm_start_runtime_seconds=0.0,
        time_limit_seconds=60.0,
        threads=2,
        tee=False,
    )

    assert result.termination == "optimal"
    assert result.strict_feasibility_tolerance == pytest.approx(1e-9)
    assert result.strict_feasibility_tolerance == STRICT_FEASIBILITY_TOLERANCE
    assert result.normalized_admissibility_constraints is True
    assert result.fixed_primary_integrality_removed is False
    assert result.conditional_face_warm_start_mwh is None
    assert result.conditional_face_warm_start_runtime_seconds == pytest.approx(0.0)
    assert result.conditional_face_warm_start_termination is None
    assert result.conditional_face_fixed_primary_integer_count == 0
    assert (
        result.maximum_positive_normalized_constraint_residual
        <= STRICT_FEASIBILITY_TOLERANCE
    )
    assert result.auxiliary_objective_mwh == pytest.approx(expected_mwh)
    assert result.recomputed_redistribution_mwh == pytest.approx(expected_mwh)
    assert result.auxiliary_objective_mismatch_mwh == pytest.approx(0.0)
    assert result.bound_certificate_complete is True
    assert result.primal_bound_mwh == pytest.approx(expected_mwh)
    assert result.dual_bound_mwh == pytest.approx(expected_mwh)
    assert result.relative_gap == pytest.approx(0.0)
    assert result.comparator_pcc_service_residual_mwh == pytest.approx(0.0)
    assert result.candidate_pcc_service_residual_mwh == pytest.approx(0.0)
    assert result.common_pcc_difference_mwh == pytest.approx(0.0)
    assert result.actual_price_path_assigned is False
    assert result.formal_tac is False
    assert result.e1_ready is False


def test_d26_fixed_integer_face_removes_redundant_integrality() -> None:
    from pyomo.environ import Binary, ConcreteModel, Integers, Var, value

    from tes_bess_boundary.d26_numerical_certification import (
        _fix_integer_pattern,
    )

    source = ConcreteModel()
    source.commitment = Var((0, 1), domain=Binary)
    source.start_count = Var(domain=Integers, bounds=(0, 4))
    source.commitment[0].set_value(1)
    source.commitment[1].set_value(0)
    source.start_count.set_value(2)
    target = source.clone()

    fixed = _fix_integer_pattern(target, source)

    assert fixed == 3
    for variable in (
        target.commitment[0],
        target.commitment[1],
        target.start_count,
    ):
        assert variable.fixed
        assert not variable.is_binary()
        assert not variable.is_integer()
    assert value(target.commitment[0]) == pytest.approx(1.0)
    assert value(target.commitment[1]) == pytest.approx(0.0)
    assert value(target.start_count) == pytest.approx(2.0)


def test_d26_conditional_face_copy_uses_block_relative_names() -> None:
    from pyomo.environ import Block, ConcreteModel, Var, value

    from tes_bess_boundary.d26_numerical_certification import (
        _copy_joint_block_values,
    )

    source_model = ConcreteModel()
    source_model.comparator = Block()
    source_model.comparator.dispatch = Var((0, 1))
    source_model.comparator.dispatch[0].set_value(3.5)
    source_model.comparator.dispatch[1].set_value(7.0)
    target_model = ConcreteModel()
    target_model.comparator = Block()
    target_model.comparator.dispatch = Var((0, 1), initialize=0.0)

    copied = _copy_joint_block_values(
        source_model.comparator, target_model.comparator
    )

    assert copied == 2
    assert value(target_model.comparator.dispatch[0]) == pytest.approx(3.5)
    assert value(target_model.comparator.dispatch[1]) == pytest.approx(7.0)
