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
