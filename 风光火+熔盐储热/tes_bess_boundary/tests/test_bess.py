from __future__ import annotations

import pytest

from tes_bess_boundary.components.bess import BESSPhysics


@pytest.fixture
def bess() -> BESSPhysics:
    return BESSPhysics(
        energy_capacity_mwh=100.0,
        charge_power_mw=20.0,
        discharge_power_mw=20.0,
        soc_min=0.10,
        soc_max=0.90,
        charge_efficiency=0.95,
        discharge_efficiency=0.90,
        hourly_loss=0.0,
    )


def test_ac_deliverable_energy_uses_discharge_efficiency(bess: BESSPhysics) -> None:
    assert bess.internal_usable_energy_mwh == pytest.approx(80.0)
    assert bess.ac_deliverable_energy_mwh == pytest.approx(72.0)
    assert bess.discharge_duration_hours == pytest.approx(3.6)


def test_soc_step_uses_ac_side_charge_and_discharge_power(bess: BESSPhysics) -> None:
    after_charge = bess.step(
        stored_energy_mwh=50.0,
        charge_ac_mw=10.0,
        discharge_ac_mw=0.0,
        dt_hours=1.0,
    )
    after_discharge = bess.step(
        stored_energy_mwh=50.0,
        charge_ac_mw=0.0,
        discharge_ac_mw=9.0,
        dt_hours=1.0,
    )

    assert after_charge == pytest.approx(59.5)
    assert after_discharge == pytest.approx(40.0)


def test_simultaneous_charge_and_discharge_is_rejected(bess: BESSPhysics) -> None:
    with pytest.raises(ValueError, match="simultaneous"):
        bess.step(
            stored_energy_mwh=50.0,
            charge_ac_mw=1.0,
            discharge_ac_mw=1.0,
            dt_hours=1.0,
        )


def test_half_hour_and_one_hour_steps_have_consistent_energy_units(
    bess: BESSPhysics,
) -> None:
    one_hour = bess.step(50.0, charge_ac_mw=10.0, discharge_ac_mw=0.0, dt_hours=1.0)
    first_half = bess.step(50.0, charge_ac_mw=10.0, discharge_ac_mw=0.0, dt_hours=0.5)
    two_halves = bess.step(
        first_half,
        charge_ac_mw=10.0,
        discharge_ac_mw=0.0,
        dt_hours=0.5,
    )

    assert two_halves == pytest.approx(one_hour)


def test_initial_energy_outside_soc_bounds_is_rejected(bess: BESSPhysics) -> None:
    with pytest.raises(ValueError, match="initial stored energy"):
        bess.step(
            stored_energy_mwh=5.0,
            charge_ac_mw=10.0,
            discharge_ac_mw=0.0,
            dt_hours=1.0,
        )


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_state_or_power_is_rejected(
    bess: BESSPhysics,
    invalid: float,
) -> None:
    with pytest.raises(ValueError, match="finite"):
        bess.step(
            stored_energy_mwh=invalid,
            charge_ac_mw=0.0,
            discharge_ac_mw=0.0,
            dt_hours=1.0,
        )
