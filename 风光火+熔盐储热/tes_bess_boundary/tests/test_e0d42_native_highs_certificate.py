from __future__ import annotations

from decimal import Decimal

import pytest


def _cycle_lp(size: int = 101):
    import highspy

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    variables = highs.addVariables(size, lb=0.0, ub=10.0, obj=1.0)
    for index in range(size):
        highs.addConstr(variables[index] + variables[(index + 1) % size] >= 1.0)
    highs.ensureColwise()
    return highs.getLp()


def _optimal_objective(lp: object) -> float:
    import highspy

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    assert highs.passModel(lp) == highspy.HighsStatus.kOk
    assert highs.run() == highspy.HighsStatus.kOk
    assert highs.getModelStatus() == highspy.HighsModelStatus.kOptimal
    return float(highs.getInfo().objective_function_value)


def _one_row_lp(*, multiplier_friendly: bool = True):
    import highspy

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    variable = highs.addVariable(
        lb=0.0,
        ub=highspy.kHighsInf,
        obj=1.0 if multiplier_friendly else -1.0,
    )
    highs.addConstr(variable >= 2.0)
    highs.changeObjectiveOffset(5.0)
    highs.ensureColwise()
    return highs.getLp()


def test_lp_fingerprint_is_deterministic_and_numerically_complete() -> None:
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        audit_highs_lp,
        fingerprint_highs_lp,
    )

    first = _cycle_lp(9)
    second = _cycle_lp(9)
    assert audit_highs_lp(first)["passed"] is True
    assert fingerprint_highs_lp(first) == fingerprint_highs_lp(second)

    second.col_cost_[0] = 2.0
    assert fingerprint_highs_lp(first) != fingerprint_highs_lp(second)


def test_lp_audit_rejects_nan_and_reversed_bounds() -> None:
    from tes_bess_boundary.e0d42_native_highs_certificate import audit_highs_lp

    nan_bound = _cycle_lp(9)
    column_lower = list(nan_bound.col_lower_)
    column_lower[0] = float("nan")
    nan_bound.col_lower_ = column_lower
    with pytest.raises(ValueError, match="contains NaN"):
        audit_highs_lp(nan_bound)

    reversed_bound = _cycle_lp(9)
    row_lower = list(reversed_bound.row_lower_)
    row_upper = list(reversed_bound.row_upper_)
    row_lower[0] = 2.0
    row_upper[0] = 1.0
    reversed_bound.row_lower_ = row_lower
    reversed_bound.row_upper_ = row_upper
    with pytest.raises(ValueError, match="lower bound exceeds"):
        audit_highs_lp(reversed_bound)


def test_lagrangian_certificate_matches_known_optimum_and_offset() -> None:
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        certify_lagrangian_lower_bound,
        fingerprint_highs_lp,
    )

    lp = _one_row_lp()
    identity = fingerprint_highs_lp(lp)
    certificate = certify_lagrangian_lower_bound(
        lp,
        (1.0,),
        expected_lp_sha256=identity,
    )

    assert certificate.eligible is True
    assert Decimal(certificate.lower_bound_decimal) <= Decimal("7")
    assert Decimal(certificate.upper_bound_decimal) >= Decimal("7")
    assert certificate.projected_row_multiplier_count == 0


def test_one_sided_row_multiplier_is_projected_without_false_bound() -> None:
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        certify_lagrangian_lower_bound,
    )

    certificate = certify_lagrangian_lower_bound(
        _one_row_lp(),
        (-10.0,),
    )

    assert certificate.eligible is True
    assert certificate.projected_row_multiplier_count == 1
    assert Decimal(certificate.lower_bound_decimal) <= Decimal("5")


def test_required_infinite_column_endpoint_rejects_certificate() -> None:
    import highspy

    from tes_bess_boundary.e0d42_native_highs_certificate import (
        certify_lagrangian_lower_bound,
    )

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    highs.addVariable(
        lb=-highspy.kHighsInf,
        ub=highspy.kHighsInf,
        obj=1.0,
    )
    highs.ensureColwise()
    certificate = certify_lagrangian_lower_bound(highs.getLp(), ())

    assert certificate.eligible is False
    assert certificate.invalid_column_endpoint_count == 1
    assert certificate.lower_bound_decimal is None


def test_certificate_rejects_hash_mismatch_and_low_precision() -> None:
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        certify_lagrangian_lower_bound,
    )

    lp = _one_row_lp()
    with pytest.raises(ValueError, match="fingerprint differs"):
        certify_lagrangian_lower_bound(
            lp,
            (1.0,),
            expected_lp_sha256="0" * 64,
        )
    with pytest.raises(ValueError, match="precision"):
        certify_lagrangian_lower_bound(lp, (1.0,), precision=40)


@pytest.mark.solver
def test_dual_simplex_interrupt_yields_audited_bound_below_optimum() -> None:
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        run_iteration_limited_lp,
    )

    lp = _cycle_lp()
    optimum = Decimal(str(_optimal_objective(lp)))
    snapshot = run_iteration_limited_lp(
        lp,
        solver_name="simplex",
        interrupt_after_iterations=1,
    )

    assert snapshot.model_status == "Interrupted by user"
    assert snapshot.info.num_primal_infeasibilities > 0
    assert snapshot.certificate.eligible is True
    assert Decimal(snapshot.certificate.lower_bound_decimal) <= optimum
    assert snapshot.basis.valid is True


@pytest.mark.solver
def test_simplex_basis_checkpoint_resumes_same_lp_and_improves_bound() -> None:
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        run_iteration_limited_lp,
    )

    lp = _cycle_lp()
    first = run_iteration_limited_lp(
        lp,
        solver_name="simplex",
        interrupt_after_iterations=1,
    )
    second = run_iteration_limited_lp(
        lp,
        solver_name="simplex",
        interrupt_after_iterations=2,
        basis=first.basis,
        expected_lp_sha256=first.lp_sha256,
    )

    assert second.lp_sha256 == first.lp_sha256
    assert second.basis.valid is True
    assert Decimal(second.certificate.lower_bound_decimal) >= Decimal(
        first.certificate.lower_bound_decimal
    )


@pytest.mark.solver
def test_simplex_checkpoint_is_rejected_before_loading_into_another_lp() -> None:
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        run_iteration_limited_lp,
    )

    first = run_iteration_limited_lp(
        _cycle_lp(101),
        solver_name="simplex",
        interrupt_after_iterations=1,
    )

    with pytest.raises(ValueError, match="fingerprint differs"):
        run_iteration_limited_lp(
            _cycle_lp(103),
            solver_name="simplex",
            interrupt_after_iterations=2,
            basis=first.basis,
            expected_lp_sha256=first.lp_sha256,
        )


@pytest.mark.solver
def test_ipx_interrupt_is_certified_independently_of_primal_status() -> None:
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        run_iteration_limited_lp,
    )

    lp = _cycle_lp()
    optimum = Decimal(str(_optimal_objective(lp)))
    snapshot = run_iteration_limited_lp(
        lp,
        solver_name="ipx",
        interrupt_after_iterations=1,
    )

    assert snapshot.model_status == "Interrupted by user"
    assert snapshot.certificate.eligible is True
    assert Decimal(snapshot.certificate.lower_bound_decimal) <= optimum


@pytest.mark.solver
def test_pyomo_translation_and_explicit_presolve_preserve_optimum() -> None:
    from pyomo.environ import (
        ConcreteModel,
        Constraint,
        NonNegativeReals,
        Objective,
        Var,
        minimize,
    )

    from tes_bess_boundary.e0d42_native_highs_certificate import (
        explicit_presolve,
        translate_pyomo_model,
    )

    model = ConcreteModel()
    model.x = Var(domain=NonNegativeReals)
    model.y = Var(bounds=(0.0, 10.0))
    model.balance = Constraint(expr=model.x + model.y >= 4.0)
    model.redundant = Constraint(expr=model.x + model.y >= 1.0)
    model.cost = Objective(expr=2.0 * model.x + model.y + 3.0, sense=minimize)

    translation = translate_pyomo_model(model)
    presolved = explicit_presolve(translation.lp)

    assert translation.audit["highs_version"] == "1.15.1"
    assert translation.audit["noncontinuous_column_count"] == 0
    assert presolved.audit["source_lp_sha256"] == translation.audit["lp_sha256"]
    assert _optimal_objective(translation.lp) == pytest.approx(
        _optimal_objective(presolved.lp), abs=1e-9
    )
