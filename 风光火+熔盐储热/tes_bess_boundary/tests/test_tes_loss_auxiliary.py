from __future__ import annotations

import pytest


def _author_sensitivity_spec(**overrides: object) -> object:
    from tes_bess_boundary.tes_loss_auxiliary import (
        LossCompensationMode,
        TESLossAuxiliarySpec,
        TESParameterIdentity,
        TESPumpAuxiliarySpec,
    )

    values: dict[str, object] = {
        "ht_standing_loss_fraction_per_hour": 0.10,
        "mt_standing_loss_fraction_per_hour": 0.20,
        "ht_loss_compensation_fraction": 0.50,
        "mt_loss_compensation_fraction": 0.25,
        "tracing_heater_efficiency": 0.50,
        "pump": TESPumpAuxiliarySpec(
            electric_lt_to_ht_kwh_per_tonne=1.0,
            steam_lt_to_ht_kwh_per_tonne=2.0,
            steam_lt_to_mt_kwh_per_tonne=3.0,
            power_ht_to_mt_kwh_per_tonne=4.0,
            heat_mt_to_lt_kwh_per_tonne=5.0,
        ),
        "compensation_mode": LossCompensationMode.FIXED_FRACTION,
        "parameter_identity": TESParameterIdentity.AUTHOR_SENSITIVITY,
        "parameter_source_id": "author:e0d9_synthetic_gold",
        "evidence_source_ids": (
            "doi:10.1016/j.enconman.2022.116362",
            "doi:10.1016/j.apenergy.2024.124524",
        ),
        "reference_ambient_temperature_c": 25.0,
    }
    values.update(overrides)
    return TESLossAuxiliarySpec(**values)


def test_interval_loss_coefficient_preserves_compounded_hourly_fraction() -> None:
    spec = _author_sensitivity_spec()

    assert spec.ht_loss_flow_coefficient(dt_hours=2.0) == pytest.approx(0.095)
    assert spec.mt_loss_flow_coefficient(dt_hours=0.5) == pytest.approx(
        (1.0 - 0.8**0.5) / 0.5
    )


def test_pump_coefficients_convert_each_path_from_kwh_per_tonne_to_mw() -> None:
    spec = _author_sensitivity_spec()

    assert spec.pump.electric_power_mw(
        electric_lt_to_ht_tph=1.0,
        steam_lt_to_ht_tph=2.0,
        steam_lt_to_mt_tph=3.0,
        power_ht_to_mt_tph=4.0,
        heat_mt_to_lt_tph=5.0,
    ) == pytest.approx(0.055)


def test_loss_coefficient_scales_with_state_to_ambient_temperature_difference() -> None:
    spec = _author_sensitivity_spec(reference_ambient_temperature_c=0.0)

    assert spec.ht_loss_flow_coefficient(
        dt_hours=1.0,
        state_temperature_c=3.0,
        ambient_temperature_c=1.0,
    ) == pytest.approx(1.0 - 0.9 ** (2.0 / 3.0))
    assert spec.mt_loss_flow_coefficient(
        dt_hours=1.0,
        state_temperature_c=2.0,
        ambient_temperature_c=1.0,
    ) == pytest.approx(1.0 - 0.8**0.5)


def test_uncompensated_mode_rejects_nonzero_tracing_fraction() -> None:
    from tes_bess_boundary.tes_loss_auxiliary import LossCompensationMode

    with pytest.raises(ValueError, match="UNCOMPENSATED"):
        _author_sensitivity_spec(
            compensation_mode=LossCompensationMode.UNCOMPENSATED,
            ht_loss_compensation_fraction=0.1,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("ht_standing_loss_fraction_per_hour", 1.0),
        ("mt_standing_loss_fraction_per_hour", -0.1),
        ("tracing_heater_efficiency", 0.0),
        ("reference_ambient_temperature_c", float("nan")),
    ),
)
def test_loss_auxiliary_spec_rejects_invalid_numeric_inputs(
    field: str,
    value: float,
) -> None:
    with pytest.raises(ValueError):
        _author_sensitivity_spec(**{field: value})


def test_author_sensitivity_identity_cannot_claim_a_paper_as_value_source() -> None:
    with pytest.raises(ValueError, match="author:"):
        _author_sensitivity_spec(
            parameter_source_id="doi:10.1016/j.enconman.2022.116362"
        )
