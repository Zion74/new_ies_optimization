from __future__ import annotations

import pytest

from tes_bess_boundary.components.chp import (
    CHPCommitmentSpec,
    CHPFuelPoint,
    CHPFeasibleRegion,
    CHPUnitSpec,
    CHPVertex,
    HeatBasis,
    LowLoadFuelRule,
    UnresolvedHeatBasisError,
    coal_consumption_tph,
    yangling_chp_specs,
)


@pytest.fixture
def yangling_region() -> CHPFeasibleRegion:
    return CHPFeasibleRegion(
        (
            CHPVertex(power_gross_mw=98.0, heat_mw=0.0),
            CHPVertex(power_gross_mw=350.0, heat_mw=0.0),
            CHPVertex(power_gross_mw=286.0, heat_mw=438.0),
            CHPVertex(power_gross_mw=98.0, heat_mw=83.0),
        )
    )


@pytest.mark.parametrize(
    ("heat_mw", "expected_power_mw"),
    [
        (0.0, 98.0),
        (83.0, 98.0),
        (200.0, 159.960563),
        (438.0, 286.0),
    ],
)
def test_yangling_table_vertices_define_heat_induced_power_floor(
    yangling_region: CHPFeasibleRegion,
    heat_mw: float,
    expected_power_mw: float,
) -> None:
    assert yangling_region.minimum_power_for_heat(heat_mw) == pytest.approx(
        expected_power_mw,
        abs=1e-6,
    )


def test_two_online_units_reproduce_observed_heat_power_floor(
    yangling_region: CHPFeasibleRegion,
) -> None:
    total_heat_mw = 454.0

    total_power_mw = 2.0 * yangling_region.minimum_power_for_heat(total_heat_mw / 2.0)

    assert total_power_mw == pytest.approx(348.510, abs=0.05)


def test_heat_outside_table_region_is_rejected(
    yangling_region: CHPFeasibleRegion,
) -> None:
    with pytest.raises(ValueError, match="heat"):
        yangling_region.minimum_power_for_heat(439.0)


def test_unresolved_heat_basis_cannot_enter_formal_model(
    yangling_region: CHPFeasibleRegion,
) -> None:
    spec = CHPUnitSpec(
        name="unit_1",
        feasible_region=yangling_region,
        heat_basis=HeatBasis.UNRESOLVED,
        auxiliary_rate=0.04601,
    )

    with pytest.raises(UnresolvedHeatBasisError):
        spec.require_resolved_heat_basis()


def test_chp_unit_rejects_string_heat_basis(
    yangling_region: CHPFeasibleRegion,
) -> None:
    with pytest.raises(ValueError, match="HeatBasis"):
        CHPUnitSpec(
            name="invalid_string_heat_basis",
            feasible_region=yangling_region,
            heat_basis="unresolved",  # type: ignore[arg-type]
            auxiliary_rate=0.04601,
        )


def test_supply_coal_rate_is_converted_from_net_to_gross_power_basis() -> None:
    consumption = coal_consumption_tph(
        gross_power_mw=350.0,
        auxiliary_rate=0.04601,
        supply_coal_rate_g_per_kwh=300.0,
    )

    assert consumption == pytest.approx(100.16895)


def test_yangling_chp_specs_preserve_exact_primary_record_contract() -> None:
    unit_1, unit_2 = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.LINEAR_TOTAL_FLOW_EXTRAPOLATION
    )

    assert unit_1.name == "yangling_unit_1"
    assert unit_2.name == "yangling_unit_2"
    assert unit_1.auxiliary_rate == pytest.approx(0.0460139347345251, abs=1e-16)
    assert unit_2.auxiliary_rate == pytest.approx(0.0465236409080113, abs=1e-16)
    expected_vertices = (
        CHPVertex(98.0, 0.0),
        CHPVertex(350.0, 0.0),
        CHPVertex(286.0, 438.0),
        CHPVertex(98.0, 83.0),
    )
    assert unit_1.feasible_region.vertices == expected_vertices
    assert unit_2.feasible_region.vertices == expected_vertices
    assert tuple(point.power_gross_mw for point in unit_1.fuel_points) == tuple(
        float(power) for power in range(105, 351, 35)
    )
    assert tuple(point.supply_coal_rate_g_per_kwh for point in unit_1.fuel_points) == (
        394.556195140916,
        371.155307452574,
        329.25173575833,
        324.017882072051,
        319.958047664171,
        317.072232534689,
        315.360436683605,
        314.82266011092,
    )
    assert tuple(point.supply_coal_rate_g_per_kwh for point in unit_2.fuel_points) == (
        378.556195140916,
        360.155307452574,
        337.452770525067,
        327.448584358394,
        320.142748952555,
        315.535264307551,
        313.626130423382,
        314.415347300047,
    )
    assert isinstance(unit_1.fuel_points[-1], CHPFuelPoint)
    assert unit_1.fuel_points[-1].total_fuel_tce_per_hour(
        unit_1.auxiliary_rate
    ) == pytest.approx(105.1177507714693)
    assert unit_2.fuel_points[-1].total_fuel_tce_per_hour(
        unit_2.auxiliary_rate
    ) == pytest.approx(104.9256602052022)
    assert unit_1.normal_ramp_mw_per_min == 5.25
    assert unit_1.unresolved_minimum_start_stop_hours == 3.5
    assert unit_1.unresolved_cycle_event_cost_cny == 300_000.0


def test_yangling_low_load_fuel_rule_must_be_selected_explicitly() -> None:
    with pytest.raises(ValueError, match="low_load_fuel_rule"):
        yangling_chp_specs()


def test_low_load_rules_are_distinct_and_leave_raw_points_untouched() -> None:
    extrapolated, _ = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.LINEAR_TOTAL_FLOW_EXTRAPOLATION
    )
    clamped, _ = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE
    )
    raised, _ = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.RAISE_MIN_POWER_TO_105
    )

    assert extrapolated.fuel_flow_knots()[0] == pytest.approx(
        (98.0, 37.51238437014931)
    )
    assert clamped.fuel_flow_knots()[0] == pytest.approx(
        (98.0, 36.88730898860274)
    )
    assert raised.fuel_flow_knots()[0] == pytest.approx(
        (105.0, 39.52211677350293)
    )
    assert extrapolated.minimum_online_power_mw == 98.0
    assert clamped.minimum_online_power_mw == 98.0
    assert raised.minimum_online_power_mw == 105.0
    assert extrapolated.fuel_points == clamped.fuel_points == raised.fuel_points


def test_fuel_knots_must_cover_the_chp_region_maximum_power() -> None:
    spec = CHPCommitmentSpec(
        unit=CHPUnitSpec(
            name="synthetic_short_fuel_curve",
            feasible_region=CHPFeasibleRegion(
                (
                    CHPVertex(98.0, 0.0),
                    CHPVertex(350.0, 0.0),
                    CHPVertex(286.0, 438.0),
                )
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.05,
        ),
        fuel_points=(CHPFuelPoint(105.0, 400.0), CHPFuelPoint(140.0, 350.0)),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
    )

    with pytest.raises(ValueError, match="cover.*maximum"):
        spec.fuel_flow_knots()


def test_low_load_extrapolation_must_not_create_negative_fuel_flow() -> None:
    spec = CHPCommitmentSpec(
        unit=CHPUnitSpec(
            name="synthetic_negative_extrapolation",
            feasible_region=CHPFeasibleRegion(
                (
                    CHPVertex(98.0, 0.0),
                    CHPVertex(140.0, 0.0),
                    CHPVertex(120.0, 40.0),
                )
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.05,
        ),
        fuel_points=(CHPFuelPoint(105.0, 10.0), CHPFuelPoint(140.0, 1000.0)),
        low_load_fuel_rule=LowLoadFuelRule.LINEAR_TOTAL_FLOW_EXTRAPOLATION,
    )

    with pytest.raises(ValueError, match="fuel.*non-negative"):
        spec.fuel_flow_knots()


def test_generic_commitment_spec_does_not_inherit_yangling_metadata() -> None:
    spec = CHPCommitmentSpec(
        unit=CHPUnitSpec(
            name="synthetic_without_source_metadata",
            feasible_region=CHPFeasibleRegion(
                (
                    CHPVertex(100.0, 0.0),
                    CHPVertex(140.0, 0.0),
                    CHPVertex(120.0, 40.0),
                )
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.05,
        ),
        fuel_points=(CHPFuelPoint(100.0, 350.0), CHPFuelPoint(140.0, 330.0)),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
    )

    assert spec.normal_ramp_mw_per_min is None
    assert spec.unresolved_minimum_start_stop_hours is None
    assert spec.unresolved_cycle_event_cost_cny is None


@pytest.mark.parametrize(
    "factory",
    (
        pytest.param(lambda: CHPVertex(float("nan"), 0.0), id="vertex-power-nan"),
        pytest.param(lambda: CHPVertex(100.0, float("inf")), id="vertex-heat-inf"),
        pytest.param(
            lambda: CHPFuelPoint(float("nan"), 300.0), id="fuel-power-nan"
        ),
        pytest.param(
            lambda: CHPFuelPoint(100.0, float("inf")), id="fuel-rate-inf"
        ),
        pytest.param(
            lambda: coal_consumption_tph(
                gross_power_mw=float("nan"),
                auxiliary_rate=0.05,
                supply_coal_rate_g_per_kwh=300.0,
            ),
            id="conversion-power-nan",
        ),
        pytest.param(
            lambda: coal_consumption_tph(
                gross_power_mw=100.0,
                auxiliary_rate=float("nan"),
                supply_coal_rate_g_per_kwh=300.0,
            ),
            id="conversion-auxiliary-nan",
        ),
        pytest.param(
            lambda: coal_consumption_tph(
                gross_power_mw=100.0,
                auxiliary_rate=0.05,
                supply_coal_rate_g_per_kwh=float("nan"),
            ),
            id="conversion-rate-nan",
        ),
    ),
)
def test_chp_value_objects_reject_non_finite_inputs(factory: object) -> None:
    with pytest.raises(ValueError, match="finite"):
        factory()


def test_chp_unit_rejects_non_finite_auxiliary_rate(
    yangling_region: CHPFeasibleRegion,
) -> None:
    with pytest.raises(ValueError, match="finite"):
        CHPUnitSpec(
            name="invalid_auxiliary_rate",
            feasible_region=yangling_region,
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=float("nan"),
        )


@pytest.mark.parametrize(
    "metadata",
    (
        {"normal_ramp_mw_per_min": float("nan")},
        {"unresolved_minimum_start_stop_hours": float("inf")},
        {"unresolved_cycle_event_cost_cny": float("nan")},
    ),
)
def test_chp_commitment_metadata_must_be_finite(metadata: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="finite"):
        CHPCommitmentSpec(
            unit=CHPUnitSpec(
                name="invalid_commitment_metadata",
                feasible_region=CHPFeasibleRegion(
                    (
                        CHPVertex(100.0, 0.0),
                        CHPVertex(140.0, 0.0),
                        CHPVertex(120.0, 40.0),
                    )
                ),
                heat_basis=HeatBasis.USEFUL,
                auxiliary_rate=0.05,
            ),
            fuel_points=(
                CHPFuelPoint(100.0, 350.0),
                CHPFuelPoint(140.0, 330.0),
            ),
            low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
            **metadata,
        )


def test_final_fuel_knots_reject_non_finite_converted_flow() -> None:
    spec = CHPCommitmentSpec(
        unit=CHPUnitSpec(
            name="overflowing_fuel_conversion",
            feasible_region=CHPFeasibleRegion(
                (
                    CHPVertex(1.0e154, 0.0),
                    CHPVertex(2.0e154, 0.0),
                    CHPVertex(1.5e154, 40.0),
                )
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.05,
        ),
        fuel_points=(
            CHPFuelPoint(1.0e154, 1.0e200),
            CHPFuelPoint(2.0e154, 1.0e200),
        ),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
    )

    with pytest.raises(ValueError, match="fuel.*finite"):
        spec.fuel_flow_knots()
