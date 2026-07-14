from __future__ import annotations

import pytest


def test_d28_negated_seed_is_the_opposite_orthant() -> None:
    from tes_bess_boundary.d28_multistart_direction import transform_sign_seed

    assert transform_sign_seed((1, -1, -1, 1), "negated") == (-1, 1, 1, -1)


def test_d28_cyclic_shift_is_deterministic_and_nontrivial() -> None:
    from tes_bess_boundary.d28_multistart_direction import transform_sign_seed

    base = (1, 1, -1, -1)
    assert transform_sign_seed(base, "cyclic_shift", shift_periods=1) == (
        -1,
        1,
        1,
        -1,
    )
    with pytest.raises(ValueError, match="must differ"):
        transform_sign_seed(base, "cyclic_shift", shift_periods=4)


def test_d28_alternating_seed_supports_phase_shift() -> None:
    from tes_bess_boundary.d28_multistart_direction import transform_sign_seed

    base = (1, 1, 1, 1, 1)
    assert transform_sign_seed(base, "alternating") == (1, -1, 1, -1, 1)
    assert transform_sign_seed(base, "alternating", shift_periods=1) == (
        -1,
        1,
        -1,
        1,
        -1,
    )


def test_d28_support_witness_may_be_negative_for_a_transformed_seed() -> None:
    from tes_bess_boundary.d28_multistart_direction import (
        support_value_from_deltas,
    )

    assert support_value_from_deltas(
        (2.0, -2.0),
        (-1, 1),
        (1.0, 1.0),
        dt_hours=1.0,
    ) == pytest.approx(-2.0)


def test_d28_support_value_rejects_mismatched_weights() -> None:
    from tes_bess_boundary.d28_multistart_direction import (
        support_value_from_deltas,
    )

    with pytest.raises(ValueError, match="weights"):
        support_value_from_deltas(
            (1.0, -1.0),
            (1, -1),
            (1.0,),
            dt_hours=1.0,
        )
