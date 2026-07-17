from __future__ import annotations

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
            name="synthetic_audit_unit",
            feasible_region=CHPFeasibleRegion(
                (
                    CHPVertex(200.0, 0.0),
                    CHPVertex(201.0, 0.0),
                    CHPVertex(200.0, 100.0),
                )
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.10,
        ),
        fuel_points=(CHPFuelPoint(200.0, 300.0), CHPFuelPoint(201.0, 300.0)),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
    )


def _bess_fixed_spec(*, cyclic: bool = False) -> object:
    from tes_bess_boundary.components.bess import BESSPhysics
    from tes_bess_boundary.model import BESSFixedSpec

    return BESSFixedSpec(
        physics=BESSPhysics(
            energy_capacity_mwh=100.0,
            charge_power_mw=20.0,
            discharge_power_mw=20.0,
            soc_min=0.0,
            soc_max=1.0,
            charge_efficiency=1.0,
            discharge_efficiency=1.0,
        ),
        initial_energy_mwh=0.0,
        cyclic=cyclic,
    )


def _tes_fixed_spec(
    *,
    cyclic: bool = False,
    steam_to_mt_efficiency: float = 1.0,
) -> object:
    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
    )
    from tes_bess_boundary.model import TESFixedSpec, TESPortCaps

    return TESFixedSpec(
        physics=MoltenSaltPhysics(
            salt_mass_t=100.0,
            ht_tank_capacity_t=100.0,
            mt_tank_capacity_t=100.0,
            lt_tank_capacity_t=100.0,
            specific_heat_mwh_per_tonne_k=1.0,
            temperature_ht=3.0,
            temperature_mt=2.0,
            temperature_lt=1.0,
            electric_heater_efficiency=1.0,
            steam_to_ht_efficiency=1.0,
            steam_to_mt_efficiency=steam_to_mt_efficiency,
            power_block_efficiency=1.0,
            heat_exchanger_efficiency=1.0,
        ),
        initial_inventory=SaltInventory(0.0, 0.0, 100.0),
        port_caps=TESPortCaps(10.0, 10.0, 10.0, 10.0, 10.0),
        cyclic=cyclic,
    )


def _case_for_architecture(architecture: object) -> object:
    from tes_bess_boundary.model import Architecture, E0CCase, E0CTimeSeries

    return E0CCase(
        architecture=architecture,
        timeseries=E0CTimeSeries((0.0,), (0.0,), (0.0,)),
        chp_units=(_synthetic_chp_spec(),),
        chp_initial_online=(0,),
        pcc_export_capacity_mw=500.0,
        bess=(
            _bess_fixed_spec()
            if architecture in (Architecture.BESS, Architecture.HYBRID)
            else None
        ),
        tes=(
            _tes_fixed_spec()
            if architecture in (Architecture.TES, Architecture.HYBRID)
            else None
        ),
    )


def _synthetic_mechanism_case(architecture: object, *, repeats: int) -> object:
    """Return a constant-gross-power mechanism fixture, not a Yangling result."""

    from tes_bess_boundary.components.bess import BESSPhysics
    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
    )
    from tes_bess_boundary.model import (
        Architecture,
        BESSFixedSpec,
        E0CCase,
        E0CTimeSeries,
        TESFixedSpec,
        TESPortCaps,
        ValidationObjectiveSpec,
    )

    bess = BESSFixedSpec(
        physics=BESSPhysics(
            energy_capacity_mwh=48.0,
            charge_power_mw=24.0,
            discharge_power_mw=12.0,
            soc_min=0.0,
            soc_max=1.0,
            charge_efficiency=1.0,
            discharge_efficiency=1.0,
        ),
        initial_energy_mwh=12.0,
        cyclic=True,
    )
    tes = TESFixedSpec(
        physics=MoltenSaltPhysics(
            salt_mass_t=24.0,
            ht_tank_capacity_t=24.0,
            mt_tank_capacity_t=24.0,
            lt_tank_capacity_t=24.0,
            specific_heat_mwh_per_tonne_k=1.0,
            temperature_ht=3.0,
            temperature_mt=2.0,
            temperature_lt=1.0,
            electric_heater_efficiency=1.0,
            steam_to_ht_efficiency=1.0,
            steam_to_mt_efficiency=1.0,
            power_block_efficiency=1.0,
            heat_exchanger_efficiency=1.0,
        ),
        initial_inventory=SaltInventory(0.0, 0.0, 24.0),
        port_caps=TESPortCaps(
            electric_charge_input_mw=24.0,
            steam_to_ht_reference_input_mw=0.0,
            steam_to_mt_reference_input_mw=0.0,
            electric_output_mw=12.0,
            heat_output_mw=12.0,
        ),
        cyclic=True,
    )
    return E0CCase(
        architecture=architecture,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(50.0,) * (6 * repeats),
            wind_available_mw=(0.0, 72.0, 72.0, 0.0, 0.0, 0.0) * repeats,
            pv_available_mw=(0.0,) * (6 * repeats),
        ),
        chp_units=(_synthetic_chp_spec(),),
        chp_initial_online=(0,),
        pcc_export_capacity_mw=204.0,
        bess=(
            bess if architecture in (Architecture.BESS, Architecture.HYBRID) else None
        ),
        tes=(tes if architecture in (Architecture.TES, Architecture.HYBRID) else None),
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=1.0,
            curtailment_penalty_cny_per_mwh=1000.0,
        ),
    )


def _assert_model_is_linear(model: object) -> None:
    from pyomo.core import Constraint, Objective
    from pyomo.repn.standard_repn import generate_standard_repn

    for constraint in model.component_data_objects(Constraint, active=True):
        assert generate_standard_repn(constraint.body).is_linear(), constraint.name
    for objective in model.component_data_objects(Objective, active=True):
        assert generate_standard_repn(objective.expr).is_linear(), objective.name


def test_architecture_values_are_stable() -> None:
    from tes_bess_boundary.model import Architecture

    assert {architecture.value for architecture in Architecture} == {
        "no_storage",
        "bess",
        "tes",
        "hybrid",
    }


def test_time_series_rejects_mismatched_or_negative_inputs() -> None:
    from tes_bess_boundary.model import E0CTimeSeries

    with pytest.raises(ValueError, match="same non-zero length"):
        E0CTimeSeries(
            heat_demand_mw=(0.0,),
            wind_available_mw=(0.0, 1.0),
            pv_available_mw=(0.0,),
        )
    with pytest.raises(ValueError, match="non-negative"):
        E0CTimeSeries(
            heat_demand_mw=(-1.0,),
            wind_available_mw=(0.0,),
            pv_available_mw=(0.0,),
        )


def test_fixed_specs_reject_invalid_initial_state_and_port_caps() -> None:
    from tes_bess_boundary.components.bess import BESSPhysics
    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
    )
    from tes_bess_boundary.model import BESSFixedSpec, TESFixedSpec, TESPortCaps

    bess = BESSPhysics(
        energy_capacity_mwh=10.0,
        charge_power_mw=2.0,
        discharge_power_mw=2.0,
        soc_min=0.1,
        soc_max=0.9,
        charge_efficiency=1.0,
        discharge_efficiency=1.0,
    )
    with pytest.raises(ValueError, match="initial BESS energy"):
        BESSFixedSpec(physics=bess, initial_energy_mwh=0.0)

    with pytest.raises(ValueError, match="port caps"):
        TESPortCaps(
            electric_charge_input_mw=-1.0,
            steam_to_ht_reference_input_mw=0.0,
            steam_to_mt_reference_input_mw=0.0,
            electric_output_mw=0.0,
            heat_output_mw=0.0,
        )

    salt = MoltenSaltPhysics(
        salt_mass_t=10.0,
        ht_tank_capacity_t=10.0,
        mt_tank_capacity_t=10.0,
        lt_tank_capacity_t=10.0,
        specific_heat_mwh_per_tonne_k=1.0,
        temperature_ht=3.0,
        temperature_mt=2.0,
        temperature_lt=1.0,
        electric_heater_efficiency=1.0,
        steam_to_ht_efficiency=1.0,
        steam_to_mt_efficiency=1.0,
        power_block_efficiency=1.0,
        heat_exchanger_efficiency=1.0,
    )
    with pytest.raises(ValueError, match="initial TES inventory"):
        TESFixedSpec(
            physics=salt,
            initial_inventory=SaltInventory(0.0, 0.0, 9.0),
            port_caps=TESPortCaps(0.0, 0.0, 0.0, 0.0, 0.0),
        )


def test_case_rejects_architecture_component_leakage() -> None:
    from tes_bess_boundary.components.bess import BESSPhysics
    from tes_bess_boundary.model import (
        Architecture,
        BESSFixedSpec,
        E0CCase,
        E0CTimeSeries,
    )

    time_series = E0CTimeSeries((0.0,), (0.0,), (0.0,))
    bess = BESSFixedSpec(
        physics=BESSPhysics(
            energy_capacity_mwh=10.0,
            charge_power_mw=2.0,
            discharge_power_mw=2.0,
            soc_min=0.0,
            soc_max=1.0,
            charge_efficiency=1.0,
            discharge_efficiency=1.0,
        ),
        initial_energy_mwh=0.0,
    )
    common = dict(
        timeseries=time_series,
        chp_units=(_synthetic_chp_spec(),),
        chp_initial_online=(0,),
        pcc_export_capacity_mw=1.0,
    )

    with pytest.raises(ValueError, match="requires a BESS"):
        E0CCase(architecture=Architecture.BESS, **common)
    with pytest.raises(ValueError, match="disabled BESS"):
        E0CCase(
            architecture=Architecture.NO_STORAGE,
            bess=bess,
            **common,
        )


def test_validation_objective_and_boundary_capacity_must_be_non_negative() -> None:
    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
    )

    with pytest.raises(ValueError, match="objective coefficients"):
        ValidationObjectiveSpec(coal_price_cny_per_tce=-1.0)
    with pytest.raises(ValueError, match="PCC export capacity"):
        E0CCase(
            architecture=Architecture.NO_STORAGE,
            timeseries=E0CTimeSeries((0.0,), (0.0,), (0.0,)),
            chp_units=(_synthetic_chp_spec(),),
            chp_initial_online=(0,),
            pcc_export_capacity_mw=-1.0,
        )


def test_case_requires_an_explicit_architecture_enum() -> None:
    from tes_bess_boundary.model import E0CCase, E0CTimeSeries

    with pytest.raises(ValueError, match="Architecture enum"):
        E0CCase(
            architecture="bess",  # type: ignore[arg-type]
            timeseries=E0CTimeSeries((0.0,), (0.0,), (0.0,)),
            chp_units=(_synthetic_chp_spec(),),
            chp_initial_online=(0,),
            pcc_export_capacity_mw=1.0,
        )


def test_initially_online_unit_does_not_pay_a_false_first_hour_startup() -> None:
    from pyomo.environ import value

    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
        build_e0c_model,
    )
    from tes_bess_boundary.solver import create_highs_solver

    case = E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries((0.0,), (0.0,), (0.0,)),
        chp_units=(_synthetic_chp_spec(),),
        chp_initial_online=(1,),
        chp_terminal_online=(1,),
        pcc_export_capacity_mw=500.0,
        objective=ValidationObjectiveSpec(cycle_event_cost_proxy_cny=300_000.0),
    )

    model = build_e0c_model(case)
    result = create_highs_solver().solve(model)

    assert str(result.solver.termination_condition).lower() == "optimal"
    assert value(model.chp[0].online[0]) == pytest.approx(1.0)
    assert value(model.chp[0].startup[0]) == pytest.approx(0.0)
    assert value(model.total_transition_proxy_cost) == pytest.approx(0.0)


@pytest.mark.parametrize("terminal", (None, (1,)))
def test_cycle_event_cost_proxy_requires_an_explicit_closed_status_boundary(
    terminal: tuple[int, ...] | None,
) -> None:
    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
    )

    with pytest.raises(ValueError, match="closed CHP status boundary"):
        E0CCase(
            architecture=Architecture.NO_STORAGE,
            timeseries=E0CTimeSeries((0.0,), (0.0,), (0.0,)),
            chp_units=(_synthetic_chp_spec(),),
            chp_initial_online=(0,),
            chp_terminal_online=terminal,
            pcc_export_capacity_mw=500.0,
            objective=ValidationObjectiveSpec(cycle_event_cost_proxy_cny=1.0),
        )


@pytest.mark.parametrize(
    ("initial", "terminal"),
    (
        ((), None),
        ((2,), None),
        ((0,), ()),
        ((0,), (-1,)),
    ),
)
def test_case_requires_one_binary_boundary_state_per_chp_unit(
    initial: tuple[int, ...],
    terminal: tuple[int, ...] | None,
) -> None:
    from tes_bess_boundary.model import Architecture, E0CCase, E0CTimeSeries

    with pytest.raises(ValueError, match="CHP boundary states"):
        E0CCase(
            architecture=Architecture.NO_STORAGE,
            timeseries=E0CTimeSeries((0.0,), (0.0,), (0.0,)),
            chp_units=(_synthetic_chp_spec(),),
            chp_initial_online=initial,
            chp_terminal_online=terminal,
            pcc_export_capacity_mw=500.0,
        )


@pytest.mark.parametrize("heat_basis_name", ("EXTRACTION", "UNRESOLVED"))
def test_e0c_case_rejects_every_non_useful_chp_heat_basis(
    heat_basis_name: str,
) -> None:
    from dataclasses import replace

    from tes_bess_boundary.components.chp import HeatBasis
    from tes_bess_boundary.model import Architecture, E0CCase, E0CTimeSeries

    original = _synthetic_chp_spec()
    non_useful = replace(
        original,
        unit=replace(
            original.unit,
            heat_basis=getattr(HeatBasis, heat_basis_name),
        ),
    )

    with pytest.raises(ValueError, match="useful heat basis"):
        E0CCase(
            architecture=Architecture.NO_STORAGE,
            timeseries=E0CTimeSeries((0.0,), (0.0,), (0.0,)),
            chp_units=(non_useful,),
            chp_initial_online=(0,),
            pcc_export_capacity_mw=500.0,
        )


@pytest.mark.parametrize(
    ("architecture_name", "expect_bess", "expect_tes"),
    (
        ("NO_STORAGE", False, False),
        ("BESS", True, False),
        ("TES", False, True),
        ("HYBRID", True, True),
    ),
)
def test_build_isolates_storage_blocks_by_architecture(
    architecture_name: str,
    expect_bess: bool,
    expect_tes: bool,
) -> None:
    from tes_bess_boundary.model import Architecture, build_e0c_model

    model = build_e0c_model(
        _case_for_architecture(getattr(Architecture, architecture_name))
    )

    assert hasattr(model, "bess") is expect_bess
    assert hasattr(model, "tes") is expect_tes
    _assert_model_is_linear(model)


def test_one_hour_pcc_audit_counts_auxiliary_and_bess_ac_charge_once() -> None:
    from pyomo.environ import value

    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        build_e0c_model,
    )
    from tes_bess_boundary.solver import create_highs_solver

    base_case = E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries((0.0,), (0.0,), (0.0,)),
        chp_units=(_synthetic_chp_spec(),),
        chp_initial_online=(0,),
        pcc_export_capacity_mw=500.0,
    )
    base_model = build_e0c_model(base_case)
    base_model.chp[0].online[0].fix(1)
    base_model.chp[0].power_gross[0].fix(200.0)
    base_model.chp[0].heat[0].fix(0.0)
    base_result = create_highs_solver().solve(base_model)

    assert str(base_result.solver.termination_condition).lower() == "optimal"
    assert value(base_model.chp[0].auxiliary_power[0]) == pytest.approx(20.0)
    assert value(base_model.chp[0].fuel_tce_per_hour[0]) == pytest.approx(54.0)
    assert value(base_model.pcc_export[0]) == pytest.approx(180.0)

    bess_case = E0CCase(
        architecture=Architecture.BESS,
        timeseries=base_case.timeseries,
        chp_units=base_case.chp_units,
        chp_initial_online=base_case.chp_initial_online,
        pcc_export_capacity_mw=500.0,
        bess=_bess_fixed_spec(),
    )
    bess_model = build_e0c_model(bess_case)
    bess_model.chp[0].online[0].fix(1)
    bess_model.chp[0].power_gross[0].fix(200.0)
    bess_model.chp[0].heat[0].fix(0.0)
    bess_model.bess.charge_ac[0].fix(10.0)
    bess_model.bess.discharge_ac[0].fix(0.0)
    bess_result = create_highs_solver().solve(bess_model)

    assert str(bess_result.solver.termination_condition).lower() == "optimal"
    assert value(bess_model.pcc_export[0]) == pytest.approx(170.0)


def test_vre_split_pcc_cap_and_solve_result_are_auditable_and_deterministic() -> None:
    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        solve_e0c,
    )

    case = E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries((0.0,), (5.0,), (7.0,)),
        chp_units=(_synthetic_chp_spec(),),
        chp_initial_online=(0,),
        pcc_export_capacity_mw=8.0,
    )

    first = solve_e0c(case)
    second = solve_e0c(case)

    assert first.termination == "optimal"
    assert first.solver_name == "appsi_highs"
    assert first.curtailment_mwh == pytest.approx(4.0)
    assert first.wind_curtailed_mwh + first.pv_curtailed_mwh == pytest.approx(4.0)
    assert first.pcc_export_mwh == pytest.approx(8.0)
    assert first.max_pcc_balance_residual_mw <= 1e-8
    assert first.max_heat_balance_residual_mw <= 1e-8
    assert second.objective_value == pytest.approx(first.objective_value)


def test_solve_accepts_the_direct_appsi_highs_interface() -> None:
    from pyomo.contrib.appsi.solvers import Highs

    from tes_bess_boundary.model import Architecture, solve_e0c

    result = solve_e0c(
        _case_for_architecture(Architecture.NO_STORAGE),
        solver=Highs(),
    )

    assert result.termination == "optimal"
    assert result.solver_name == "appsi_highs"


@pytest.mark.parametrize("direct_interface", (False, True))
def test_solve_reports_runtime_and_exact_mip_gap_for_both_highs_interfaces(
    direct_interface: bool,
) -> None:
    from pyomo.contrib.appsi.solvers import Highs

    from tes_bess_boundary.model import Architecture, solve_e0c
    from tes_bess_boundary.solver import create_highs_solver

    solver = Highs() if direct_interface else create_highs_solver()
    result = solve_e0c(
        _case_for_architecture(Architecture.NO_STORAGE),
        solver=solver,
    )

    assert result.runtime_seconds >= 0.0
    assert result.mip_gap is not None
    assert result.mip_gap == pytest.approx(0.0, abs=1e-12)


def test_solve_still_rejects_non_highs_solver_injection() -> None:
    from tes_bess_boundary.model import Architecture, solve_e0c

    with pytest.raises(ValueError, match="only the appsi_highs solver"):
        solve_e0c(
            _case_for_architecture(Architecture.NO_STORAGE),
            solver=object(),
        )


def test_tes_reference_heat_allocation_and_five_port_caps_are_enforced() -> None:
    from pyomo.environ import value

    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        build_e0c_model,
    )
    from tes_bess_boundary.solver import create_highs_solver

    case = E0CCase(
        architecture=Architecture.TES,
        timeseries=E0CTimeSeries((0.0,), (0.0,), (0.0,)),
        chp_units=(_synthetic_chp_spec(),),
        chp_initial_online=(0,),
        pcc_export_capacity_mw=500.0,
        tes=_tes_fixed_spec(steam_to_mt_efficiency=0.5),
    )
    model = build_e0c_model(case)
    model.chp[0].online[0].fix(1)
    model.chp[0].power_gross[0].fix(200.0)
    model.chp[0].heat[0].fix(10.0)
    model.direct_heat[0].fix(0.0)
    model.tes.electric_lt_to_ht[0].fix(0.0)
    model.tes.steam_lt_to_ht[0].fix(0.0)
    model.tes.steam_lt_to_mt[0].fix(5.0)
    model.tes.power_ht_to_mt[0].fix(0.0)
    model.tes.heat_mt_to_lt[0].fix(0.0)

    result = create_highs_solver().solve(model)

    assert str(result.solver.termination_condition).lower() == "optimal"
    assert value(model.tes.steam_to_mt_input[0]) == pytest.approx(10.0)
    assert value(model.chp_heat_total[0]) == pytest.approx(10.0)
    assert value(model.pcc_export[0]) == pytest.approx(180.0)
    for name in (
        "tes_electric_charge_cap",
        "tes_steam_to_ht_cap",
        "tes_steam_to_mt_cap",
        "tes_electric_output_cap",
        "tes_heat_output_cap",
    ):
        assert value(getattr(model, name)[0].upper) == pytest.approx(10.0)

    over_cap = build_e0c_model(case)
    over_cap.tes.electric_lt_to_ht[0].fix(6.0)
    over_cap.tes.steam_lt_to_ht[0].fix(0.0)
    over_cap.tes.steam_lt_to_mt[0].fix(0.0)
    over_cap.tes.power_ht_to_mt[0].fix(0.0)
    over_cap.tes.heat_mt_to_lt[0].fix(0.0)
    infeasible = create_highs_solver().solve(over_cap, load_solutions=False)
    assert str(infeasible.solver.termination_condition).lower() == "infeasible"


def test_tes_auxiliary_is_subtracted_at_pcc_exactly_once() -> None:
    from pyomo.environ import value

    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
    )
    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        TESFixedSpec,
        TESPortCaps,
        build_e0c_model,
        solve_e0c,
    )
    from tes_bess_boundary.solver import create_highs_solver
    from tes_bess_boundary.tes_loss_auxiliary import (
        LossCompensationMode,
        TESLossAuxiliarySpec,
        TESParameterIdentity,
        TESPumpAuxiliarySpec,
    )

    loss_auxiliary = TESLossAuxiliarySpec(
        ht_standing_loss_fraction_per_hour=0.10,
        mt_standing_loss_fraction_per_hour=0.20,
        ht_loss_compensation_fraction=0.50,
        mt_loss_compensation_fraction=0.25,
        tracing_heater_efficiency=0.50,
        pump=TESPumpAuxiliarySpec(0.0, 0.0, 0.0, 0.0, 0.0),
        compensation_mode=LossCompensationMode.FIXED_FRACTION,
        parameter_identity=TESParameterIdentity.AUTHOR_SENSITIVITY,
        parameter_source_id="author:e0d9_pcc_gold",
        evidence_source_ids=("doi:10.1016/j.enconman.2022.116362",),
        reference_ambient_temperature_c=0.0,
    )
    tes = TESFixedSpec(
        physics=MoltenSaltPhysics(
            salt_mass_t=100.0,
            ht_tank_capacity_t=100.0,
            mt_tank_capacity_t=100.0,
            lt_tank_capacity_t=100.0,
            specific_heat_mwh_per_tonne_k=1.0,
            temperature_ht=3.0,
            temperature_mt=2.0,
            temperature_lt=1.0,
            electric_heater_efficiency=1.0,
            steam_to_ht_efficiency=1.0,
            steam_to_mt_efficiency=1.0,
            power_block_efficiency=1.0,
            heat_exchanger_efficiency=1.0,
        ),
        initial_inventory=SaltInventory(10.0, 20.0, 70.0),
        port_caps=TESPortCaps(0.0, 0.0, 0.0, 0.0, 0.0),
        loss_auxiliary=loss_auxiliary,
        cyclic=False,
    )
    case = E0CCase(
        architecture=Architecture.TES,
        timeseries=E0CTimeSeries((0.0,), (0.0,), (0.0,)),
        chp_units=(_synthetic_chp_spec(),),
        chp_initial_online=(1,),
        chp_terminal_online=(1,),
        pcc_export_capacity_mw=500.0,
        tes=tes,
    )
    model = build_e0c_model(case)
    model.chp[0].online[0].fix(1)
    model.chp[0].power_gross[0].fix(200.0)
    model.chp[0].heat[0].fix(0.0)
    for name in (
        "electric_lt_to_ht",
        "steam_lt_to_ht",
        "steam_lt_to_mt",
        "power_ht_to_mt",
        "heat_mt_to_lt",
    ):
        getattr(model.tes, name)[0].fix(0.0)

    result = create_highs_solver().solve(model)

    assert str(result.solver.termination_condition).lower() == "optimal"
    assert value(model.chp_auxiliary_total[0]) == pytest.approx(20.0)
    assert value(model.tes_auxiliary_total[0]) == pytest.approx(3.0)
    assert value(model.pcc_export[0]) == pytest.approx(177.0)
    assert abs(value(model.pcc_balance[0].body)) <= 1e-9

    audited = solve_e0c(case)
    assert audited.tes_pump_auxiliary_mwh == pytest.approx(0.0)
    assert audited.tes_tracing_auxiliary_mwh == pytest.approx(3.0)
    assert audited.tes_auxiliary_mwh == pytest.approx(3.0)
    assert audited.tes_operation is not None
    assert audited.tes_operation.weight_basis.value == "dispatch_horizon"
    assert audited.tes_operation.weighted_hours == pytest.approx(1.0)
    assert audited.tes_operation.path_throughput.total_t == pytest.approx(0.0)
    assert audited.tes_operation.raw_standing_loss_mwh_th == pytest.approx(5.0)
    assert audited.tes_operation.compensated_standing_loss_mwh_th == pytest.approx(
        1.5
    )
    assert audited.tes_operation.net_standing_loss_mwh_th == pytest.approx(3.5)
    assert audited.tes_operation.pump_auxiliary_mwh_e == pytest.approx(0.0)
    assert audited.tes_operation.tracing_auxiliary_mwh_e == pytest.approx(3.0)
    assert audited.tes_operation.total_auxiliary_mwh_e == pytest.approx(3.0)
    assert audited.tes_operation.compensation_fraction == pytest.approx(0.3)
    assert audited.tes_operation.pump_fraction_of_auxiliary == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("architecture_name", "expected_six_hour", "expected_twenty_four_hour"),
    (
        ("NO_STORAGE", 96.0, 384.0),
        ("BESS", 48.0, 192.0),
        ("TES", 48.0, 192.0),
        ("HYBRID", 0.0, 0.0),
    ),
)
def test_synthetic_mechanism_fixture_closes_six_and_twenty_four_hours(
    architecture_name: str,
    expected_six_hour: float,
    expected_twenty_four_hour: float,
) -> None:
    from tes_bess_boundary.model import Architecture, solve_e0c

    architecture = getattr(Architecture, architecture_name)
    six_hour = solve_e0c(_synthetic_mechanism_case(architecture, repeats=1))
    twenty_four_hour = solve_e0c(_synthetic_mechanism_case(architecture, repeats=4))

    assert six_hour.curtailment_mwh == pytest.approx(expected_six_hour, abs=1e-7)
    assert twenty_four_hour.curtailment_mwh == pytest.approx(
        expected_twenty_four_hour,
        abs=1e-7,
    )
    assert six_hour.max_pcc_balance_residual_mw <= 1e-8
    assert six_hour.max_heat_balance_residual_mw <= 1e-8
    if architecture in (Architecture.BESS, Architecture.HYBRID):
        assert six_hour.bess_cyclic_residual_mwh == pytest.approx(0.0, abs=1e-8)
        assert twenty_four_hour.bess_cyclic_residual_mwh == pytest.approx(
            0.0,
            abs=1e-8,
        )
    else:
        assert six_hour.bess_cyclic_residual_mwh is None
    if architecture in (Architecture.TES, Architecture.HYBRID):
        assert six_hour.tes_cyclic_residual_t == pytest.approx(0.0, abs=1e-8)
        assert twenty_four_hour.tes_cyclic_residual_t == pytest.approx(
            0.0,
            abs=1e-8,
        )
        assert six_hour.tes_operation is not None
        assert twenty_four_hour.tes_operation is not None
        assert six_hour.tes_operation.path_throughput.electric_lt_to_ht_t == (
            pytest.approx(24.0)
        )
        assert six_hour.tes_operation.path_throughput.steam_lt_to_ht_t == (
            pytest.approx(0.0)
        )
        assert six_hour.tes_operation.path_throughput.steam_lt_to_mt_t == (
            pytest.approx(0.0)
        )
        assert six_hour.tes_operation.path_throughput.power_ht_to_mt_t == (
            pytest.approx(24.0)
        )
        assert six_hour.tes_operation.path_throughput.heat_mt_to_lt_t == (
            pytest.approx(24.0)
        )
        assert six_hour.tes_operation.path_throughput.total_t == pytest.approx(72.0)
        assert twenty_four_hour.tes_operation.path_throughput.total_t == pytest.approx(
            288.0
        )
    else:
        assert six_hour.tes_cyclic_residual_t is None
        assert six_hour.tes_operation is None


def test_tes_operational_audit_uses_annual_period_weights_when_present() -> None:
    from dataclasses import replace

    from tes_bess_boundary.components.molten_salt import SaltInventory
    from tes_bess_boundary.economics import AnnualEconomicsSpec, AnnualHorizonSpec
    from tes_bess_boundary.model import Architecture, solve_e0c
    from tes_bess_boundary.tes_loss_auxiliary import (
        LossCompensationMode,
        TESLossAuxiliarySpec,
        TESParameterIdentity,
        TESPumpAuxiliarySpec,
    )

    case = _synthetic_mechanism_case(Architecture.TES, repeats=1)
    assert case.tes is not None
    loss_auxiliary = TESLossAuxiliarySpec(
        ht_standing_loss_fraction_per_hour=0.01,
        mt_standing_loss_fraction_per_hour=0.02,
        ht_loss_compensation_fraction=1.0,
        mt_loss_compensation_fraction=1.0,
        tracing_heater_efficiency=1.0,
        pump=TESPumpAuxiliarySpec(0.0, 0.0, 0.0, 0.0, 0.0),
        compensation_mode=LossCompensationMode.FIXED_FRACTION,
        parameter_identity=TESParameterIdentity.AUTHOR_SENSITIVITY,
        parameter_source_id="author:annual-weight-audit-gold-v1",
        evidence_source_ids=("doi:10.1016/j.enconman.2022.116362",),
        reference_ambient_temperature_c=0.0,
    )
    zero_ports = replace(
        case.tes.port_caps,
        electric_charge_input_mw=0.0,
        steam_to_ht_reference_input_mw=0.0,
        steam_to_mt_reference_input_mw=0.0,
        electric_output_mw=0.0,
        heat_output_mw=0.0,
    )
    annual_case = replace(
        case,
        chp_initial_online=(1,),
        chp_terminal_online=(1,),
        tes=replace(
            case.tes,
            initial_inventory=SaltInventory(12.0, 12.0, 0.0),
            port_caps=zero_ports,
            loss_auxiliary=loss_auxiliary,
        ),
        economics=AnnualEconomicsSpec(
            horizon=AnnualHorizonSpec(period_weights=(1464.0,) * 6)
        ),
    )

    result = solve_e0c(annual_case)

    assert result.tes_operation is not None
    assert result.tes_operation.weight_basis.value == "annual_period_weighted"
    assert result.tes_operation.weighted_hours == pytest.approx(8784.0)
    assert result.tes_operation.path_throughput.total_t == pytest.approx(0.0)
    assert result.tes_operation.raw_standing_loss_mwh_th == pytest.approx(
        0.36 * 8784.0
    )
    assert result.tes_operation.compensated_standing_loss_mwh_th == pytest.approx(
        0.36 * 8784.0
    )
    assert result.tes_operation.net_standing_loss_mwh_th == pytest.approx(0.0)
    assert result.tes_operation.tracing_auxiliary_mwh_e == pytest.approx(
        0.36 * 8784.0
    )


def test_real_yangling_chp_spec_has_an_optimal_24h_boundary_smoke() -> None:
    from tes_bess_boundary.components.chp import LowLoadFuelRule, yangling_chp_specs
    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
        solve_e0c,
    )

    units = yangling_chp_specs(low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE)
    # At 454 MWth, this is the minimum-net corner: unit 1 stays at
    # (98 MW, 83 MWth) and unit 2 supplies the remaining 371 MWth.
    unit_2_power_mw = units[1].feasible_region.minimum_power_for_heat(371.0)
    minimum_net_power_mw = 98.0 * (1.0 - units[0].auxiliary_rate) + (
        unit_2_power_mw * (1.0 - units[1].auxiliary_rate)
    )
    case = E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(454.0,) * 24,
            wind_available_mw=(0.0, 72.0, 72.0, 0.0, 0.0, 0.0) * 4,
            pv_available_mw=(0.0,) * 24,
        ),
        chp_units=units,
        chp_initial_online=(0, 0),
        pcc_export_capacity_mw=minimum_net_power_mw + 24.0,
        objective=ValidationObjectiveSpec(1.0, 1000.0),
    )

    result = solve_e0c(case)

    assert result.termination == "optimal"
    assert result.fuel_tce > 0.0
    assert result.max_pcc_balance_residual_mw <= 1e-8
    assert result.max_heat_balance_residual_mw <= 1e-8
