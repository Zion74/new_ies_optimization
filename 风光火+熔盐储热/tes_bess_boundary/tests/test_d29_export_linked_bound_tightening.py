from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_d29_loads_hash_verified_d27_reference(tmp_path: Path) -> None:
    from tes_bess_boundary.d27_certification_bundle import D27_BUNDLE_SCHEMA
    from tes_bess_boundary.d29_export_linked_bound_tightening import (
        load_d27_maximum_reference,
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
                "support_dual_is_global_l1_upper_bound",
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
                "support_dual_is_global_l1_upper_bound": "false",
            }
        )
    manifest = {
        "schema": D27_BUNDLE_SCHEMA,
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

    result = load_d27_maximum_reference(tmp_path, window_id="fixture")

    assert result.hours == 2
    assert result.strict_global_lower_bound_mwh == pytest.approx(1.0)
    assert result.strict_global_upper_bound_mwh == pytest.approx(2.0)


def _fractional_sign_fixture() -> object:
    from pyomo.environ import (
        Block,
        ConcreteModel,
        Expression,
        NonNegativeReals,
        Objective,
        RangeSet,
        UnitInterval,
        Var,
        maximize,
    )

    from tes_bess_boundary.d27_direction_generation import (
        _replace_big_m_with_disaggregated_sign_formulation,
    )

    model = ConcreteModel()
    model.redistribution_periods = RangeSet(0, 0)
    model.comparator = Block()
    model.candidate = Block()
    model.comparator.pcc_export = Var(model.redistribution_periods, bounds=(0.0, 2.0))
    model.candidate.pcc_export = Var(model.redistribution_periods, bounds=(0.0, 2.0))
    model.comparator.pcc_export[0].fix(0.1)
    model.candidate.pcc_export[0].fix(0.1)
    model.delta_pcc_export_mw = Expression(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.candidate.pcc_export[period] - block.comparator.pcc_export[period]
        ),
    )
    model.absolute_delta_pcc_export_mw = Var(
        model.redistribution_periods,
        domain=NonNegativeReals,
        bounds=(0.0, 2.0),
    )
    model.delta_nonnegative = Var(model.redistribution_periods, domain=UnitInterval)
    from pyomo.environ import Constraint

    model.absolute_delta_lower_positive = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.absolute_delta_pcc_export_mw[period] >= block.delta_pcc_export_mw[period]
        ),
    )
    model.absolute_delta_lower_negative = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.absolute_delta_pcc_export_mw[period] >= -block.delta_pcc_export_mw[period]
        ),
    )
    model.absolute_delta_upper_positive = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.absolute_delta_pcc_export_mw[period]
            <= block.delta_pcc_export_mw[period] + 4.0 * (1.0 - block.delta_nonnegative[period])
        ),
    )
    model.absolute_delta_upper_negative = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.absolute_delta_pcc_export_mw[period]
            <= -block.delta_pcc_export_mw[period] + 4.0 * block.delta_nonnegative[period]
        ),
    )
    _replace_big_m_with_disaggregated_sign_formulation(model, pcc_capacity_mw=2.0)
    model.test_objective = Objective(
        expr=model.d27_delta_positive_mw[0] + model.d27_delta_negative_mw[0],
        sense=maximize,
    )
    return model


@pytest.mark.solver
def test_d29_cuts_remove_fractional_sign_mass() -> None:
    from pyomo.environ import value

    from tes_bess_boundary.d29_export_linked_bound_tightening import (
        add_export_linked_sign_cuts,
    )
    from tes_bess_boundary.solver import create_highs_solver

    model = _fractional_sign_fixture()
    create_highs_solver().solve(model)
    assert value(model.test_objective) == pytest.approx(2.0)

    audit = add_export_linked_sign_cuts(
        model,
        pcc_capacity_mw=2.0,
        annual_weights=(1.0,),
        dt_hours=1.0,
        target_export_mwh=0.1,
    )
    create_highs_solver().solve(model)

    assert value(model.test_objective) == pytest.approx(0.2)
    assert audit.per_period_cut_count == 4
    assert audit.aggregate_cut_count == 5
    assert audit.feasible_set_changed_for_integer_solutions is False


def test_d29_cuts_reject_target_above_capacity_energy() -> None:
    from tes_bess_boundary.d29_export_linked_bound_tightening import (
        add_export_linked_sign_cuts,
    )

    model = _fractional_sign_fixture()
    with pytest.raises(ValueError, match="exceeds PCC capacity"):
        add_export_linked_sign_cuts(
            model,
            pcc_capacity_mw=2.0,
            annual_weights=(1.0,),
            dt_hours=1.0,
            target_export_mwh=2.1,
        )
