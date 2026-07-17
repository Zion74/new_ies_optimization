from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_d30_loads_hash_verified_d29_reference(tmp_path: Path) -> None:
    from tes_bess_boundary.d29_certification_bundle import D29_BUNDLE_SCHEMA
    from tes_bess_boundary.d30_physics_service_bound_tightening import (
        load_d29_maximum_reference,
    )

    csv_path = tmp_path / "certificate.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "window_id",
                "hours",
                "strict_global_lower_bound_mwh",
                "strict_global_upper_bound_mwh",
                "global_dual_is_valid_l1_upper_bound",
            ),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "window_id": "fixture",
                "hours": 2,
                "strict_global_lower_bound_mwh": "1.0",
                "strict_global_upper_bound_mwh": "2.0",
                "global_dual_is_valid_l1_upper_bound": "true",
            }
        )
    manifest = {
        "schema": D29_BUNDLE_SCHEMA,
        "output": {
            "csv": csv_path.name,
            "csv_sha256": _sha256(csv_path),
        },
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    result = load_d29_maximum_reference(tmp_path, window_id="fixture")

    assert result.hours == 2
    assert result.strict_global_lower_bound_mwh == pytest.approx(1.0)
    assert result.strict_global_upper_bound_mwh == pytest.approx(2.0)


def test_d30_service_propagation_tightens_box_bounds() -> None:
    from tes_bess_boundary.d30_physics_service_bound_tightening import (
        tighten_bounds_with_annual_service,
    )

    lower, upper = tighten_bounds_with_annual_service(
        (0.0, 2.0),
        (4.0, 6.0),
        annual_weights=(1.0, 1.0),
        dt_hours=1.0,
        target_export_mwh=5.0,
        safety_margin_mw=0.0,
    )

    assert lower == pytest.approx((0.0, 2.0))
    assert upper == pytest.approx((3.0, 5.0))


def test_d30_service_safety_margin_never_widens_static_envelope() -> None:
    from tes_bess_boundary.d30_physics_service_bound_tightening import (
        tighten_bounds_with_annual_service,
    )

    lower, upper = tighten_bounds_with_annual_service(
        (1.0, 1.0),
        (4.0, 4.0),
        annual_weights=(1.0, 1.0),
        dt_hours=1.0,
        target_export_mwh=5.0,
        safety_margin_mw=0.1,
    )

    assert lower == pytest.approx((1.0, 1.0))
    assert upper == pytest.approx((4.0, 4.0))


def test_d30_tes_auxiliary_upper_dominates_model_expression() -> None:
    from pyomo.environ import value

    from tes_bess_boundary.d30_physics_service_bound_tightening import (
        _tes_auxiliary_upper_bounds,
    )
    from tes_bess_boundary.e0d17_exploration import build_e0d17_tes_spec
    from tes_bess_boundary.model import Architecture, E0CCase, E0CTimeSeries, build_e0c_model
    from tes_bess_boundary.components.chp import LowLoadFuelRule, yangling_chp_specs

    tes = build_e0d17_tes_spec()
    ambient = (-10.0, 20.0)
    upper = _tes_auxiliary_upper_bounds(
        tes,
        dt_hours=1.0,
        ambient_temperature_c=ambient,
    )
    case = E0CCase(
        architecture=Architecture.TES,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(100.0, 100.0),
            wind_available_mw=(0.0, 0.0),
            pv_available_mw=(0.0, 0.0),
            ambient_temperature_c=ambient,
        ),
        chp_units=yangling_chp_specs(
            low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE
        ),
        chp_initial_online=(1, 1),
        chp_terminal_online=(1, 1),
        pcc_export_capacity_mw=700.0,
        tes=tes,
    )
    model = build_e0c_model(case)
    for period in model.periods:
        for state in model.tes.states:
            model.tes.ht_mass[state].set_value(tes.physics.ht_tank_capacity_t)
            model.tes.mt_mass[state].set_value(tes.physics.mt_tank_capacity_t)
        for name in (
            "electric_lt_to_ht",
            "steam_lt_to_ht",
            "steam_lt_to_mt",
            "power_ht_to_mt",
            "heat_mt_to_lt",
        ):
            variable = getattr(model.tes, name)[period]
            variable.set_value(variable.ub)
        assert value(model.tes.auxiliary_power[period]) <= upper[int(period)] + 1e-9


@pytest.mark.solver
def test_d30_static_no_storage_bounds_contain_a_feasible_dispatch() -> None:
    from tes_bess_boundary.components.chp import LowLoadFuelRule, yangling_chp_specs
    from tes_bess_boundary.d30_physics_service_bound_tightening import (
        solve_static_pcc_bounds,
    )
    from tes_bess_boundary.model import Architecture, E0CCase, E0CTimeSeries

    case = E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(100.0, 200.0),
            wind_available_mw=(10.0, 20.0),
            pv_available_mw=(5.0, 10.0),
        ),
        chp_units=yangling_chp_specs(
            low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE
        ),
        chp_initial_online=(1, 1),
        chp_terminal_online=(1, 1),
        pcc_export_capacity_mw=700.0,
    )

    bounds = solve_static_pcc_bounds(case, threads=1)

    assert bounds.periods == 2
    assert all(lower < upper for lower, upper in zip(bounds.lower_mw, bounds.upper_mw))
    assert all(0.0 <= lower <= upper <= 700.0 for lower, upper in zip(bounds.lower_mw, bounds.upper_mw))


def _d30_sign_fixture() -> object:
    from pyomo.environ import (
        Binary,
        Block,
        ConcreteModel,
        Expression,
        NonNegativeReals,
        RangeSet,
        Var,
    )

    model = ConcreteModel()
    model.redistribution_periods = RangeSet(0, 0)
    model.comparator = Block()
    model.candidate = Block()
    model.comparator.pcc_export = Var(model.redistribution_periods, bounds=(0.0, 10.0))
    model.candidate.pcc_export = Var(model.redistribution_periods, bounds=(0.0, 10.0))
    model.delta_pcc_export_mw = Expression(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.candidate.pcc_export[period] - block.comparator.pcc_export[period]
        ),
    )
    model.absolute_delta_pcc_export_mw = Var(
        model.redistribution_periods, domain=NonNegativeReals, bounds=(0.0, 10.0)
    )
    model.d27_delta_positive_mw = Var(
        model.redistribution_periods, domain=NonNegativeReals, bounds=(0.0, 10.0)
    )
    model.d27_delta_negative_mw = Var(
        model.redistribution_periods, domain=NonNegativeReals, bounds=(0.0, 10.0)
    )
    model.delta_nonnegative = Var(model.redistribution_periods, domain=Binary)
    return model


def test_d30_sign_cuts_use_interval_widths_without_fixing_binaries() -> None:
    from tes_bess_boundary.d30_physics_service_bound_tightening import (
        add_physics_service_sign_cuts,
    )

    model = _d30_sign_fixture()
    add_physics_service_sign_cuts(
        model,
        comparator_lower_mw=(3.0,),
        comparator_upper_mw=(9.0,),
        candidate_lower_mw=(1.0,),
        candidate_upper_mw=(8.0,),
    )

    assert model.comparator.pcc_export[0].lb == pytest.approx(3.0)
    assert model.comparator.pcc_export[0].ub == pytest.approx(9.0)
    assert model.candidate.pcc_export[0].lb == pytest.approx(1.0)
    assert model.candidate.pcc_export[0].ub == pytest.approx(8.0)
    assert model.d27_delta_positive_mw[0].ub == pytest.approx(5.0)
    assert model.d27_delta_negative_mw[0].ub == pytest.approx(8.0)
    assert not model.delta_nonnegative[0].fixed
