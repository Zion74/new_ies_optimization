from __future__ import annotations

import csv
import gzip
import hashlib
import math
from pathlib import Path

import pytest


def _seed_model():
    from pyomo.environ import (
        Binary,
        Block,
        ConcreteModel,
        NonNegativeReals,
        RangeSet,
        Var,
    )

    model = ConcreteModel()
    model.periods = RangeSet(0, 1)
    model.unit_index = RangeSet(0, 0)
    model.chp = Block(model.unit_index)
    for unit in model.unit_index:
        block = model.chp[unit]
        block.fuel_segment_index = RangeSet(0, 3)
        block.fuel_code_bit_index = RangeSet(0, 1)
        block.online = Var(model.periods, domain=Binary)
        block.fuel_segment_active = Var(
            model.periods,
            block.fuel_segment_index,
            domain=NonNegativeReals,
            bounds=(0.0, 1.0),
        )
        block.fuel_code_bit = Var(
            model.periods,
            block.fuel_code_bit_index,
            domain=Binary,
        )

    model.bess = Block()
    model.bess.installed = Var(domain=Binary)
    model.bess.charge_mode = Var(model.periods, domain=Binary)
    model.bess.charge_ac_mw = Var(model.periods, domain=NonNegativeReals)
    model.bess.discharge_ac_mw = Var(model.periods, domain=NonNegativeReals)
    model.bess.energy_capacity_mwh = Var(bounds=(0.0, 2_400.0))
    model.bess.charge_power_capacity_mw = Var(bounds=(0.0, 100.0))
    model.bess.discharge_power_capacity_mw = Var(bounds=(0.0, 100.0))
    model.bess.pcs_power_capacity_mw = Var(bounds=(0.0, 100.0))

    model.tes = Block()
    model.tes.ht_receiving_mode = Var(model.periods, domain=Binary)
    model.tes.mt_direct_charge_mode = Var(model.periods, domain=Binary)
    for name in (
        "electric_lt_to_ht",
        "steam_lt_to_ht",
        "power_ht_to_mt",
        "steam_lt_to_mt",
        "heat_mt_to_lt",
    ):
        setattr(
            model.tes,
            name,
            Var(model.periods, domain=NonNegativeReals),
        )
    model.tes.salt_mass_t = Var(bounds=(0.0, 55_654.86255374656))
    model.tes.ht_service_salt_mass_t = Var(
        bounds=(0.0, 55_654.86255374656)
    )
    model.tes.mt_service_salt_mass_t = Var(
        bounds=(0.0, 55_654.86255374656)
    )
    for name in (
        "ht_tank_capacity_t",
        "mt_tank_capacity_t",
        "lt_tank_capacity_t",
    ):
        setattr(model.tes, name, Var(bounds=(0.0, 55_654.86255374656)))
    for name in (
        "electric_charge_input_capacity_mw",
        "steam_to_ht_input_capacity_mw",
        "steam_to_mt_input_capacity_mw",
        "electric_output_capacity_mw",
        "heat_output_capacity_mw",
    ):
        setattr(model.tes, name, Var(bounds=(0.0, 300.0)))
    return model


def _set_seed_point(model) -> None:
    block = model.chp[0]
    block.online[0].set_value(0.6, skip_validation=True)
    block.online[1].set_value(0.4, skip_validation=True)
    segment_values = {
        (0, 0): 0.1,
        (0, 1): 0.4,
        (0, 2): 0.4,
        (0, 3): 0.1,
        (1, 0): 0.1,
        (1, 1): 0.1,
        (1, 2): 0.1,
        (1, 3): 0.1,
    }
    for index, value in segment_values.items():
        block.fuel_segment_active[index].set_value(value)
    for bit in block.fuel_code_bit.values():
        bit.set_value(0, skip_validation=True)

    model.bess.installed.set_value(0.2, skip_validation=True)
    model.bess.charge_ac_mw[0].set_value(4.0)
    model.bess.discharge_ac_mw[0].set_value(2.0)
    model.bess.charge_ac_mw[1].set_value(1.0)
    model.bess.discharge_ac_mw[1].set_value(1.0)
    for mode in model.bess.charge_mode.values():
        mode.set_value(0, skip_validation=True)

    model.tes.electric_lt_to_ht[0].set_value(2.0)
    model.tes.steam_lt_to_ht[0].set_value(1.0)
    model.tes.power_ht_to_mt[0].set_value(1.0)
    model.tes.steam_lt_to_mt[0].set_value(0.5)
    model.tes.heat_mt_to_lt[0].set_value(2.0)
    model.tes.electric_lt_to_ht[1].set_value(0.0)
    model.tes.steam_lt_to_ht[1].set_value(0.0)
    model.tes.power_ht_to_mt[1].set_value(0.0)
    model.tes.steam_lt_to_mt[1].set_value(2.0)
    model.tes.heat_mt_to_lt[1].set_value(1.0)
    for mode in model.tes.ht_receiving_mode.values():
        mode.set_value(0, skip_validation=True)
    for mode in model.tes.mt_direct_charge_mode.values():
        mode.set_value(0, skip_validation=True)

    from pyomo.environ import Var

    for variable in model.component_data_objects(Var, active=True):
        if variable.value is None:
            variable.set_value(0.0, skip_validation=True)


def _repair_model(*, export_offset_mwh: float = 0.0):
    from pyomo.environ import (
        Binary,
        Block,
        ConcreteModel,
        Constraint,
        Expression,
        NonNegativeReals,
        Objective,
        Var,
        minimize,
    )

    from tes_bess_boundary.e0d40_full_year_compute_gate import (
        PCC_EXPORT_TARGET_MWH,
    )

    model = ConcreteModel()
    model.bess = Block()
    model.bess.installed = Var(domain=Binary)
    model.bess.energy_capacity_mwh = Var(bounds=(0.0, 2_400.0))
    model.bess.charge_power_capacity_mw = Var(bounds=(0.0, 100.0))
    model.bess.discharge_power_capacity_mw = Var(bounds=(0.0, 100.0))
    model.bess.pcs_power_capacity_mw = Var(bounds=(0.0, 100.0))
    model.dispatch = Var(domain=NonNegativeReals)
    model.require_dispatch = Constraint(
        expr=model.dispatch >= 2.0 * model.bess.installed
    )
    model.annual_pcc_export_mwh = Expression(
        expr=PCC_EXPORT_TARGET_MWH + export_offset_mwh
    )
    model.annual_curtailment_mwh = Expression(expr=1.0)
    model.annual_operating_cost_cny = Expression(expr=10.0 + model.dispatch)
    model.planning_storage_capacity_cost_cny = Expression(expr=2.0)
    model.planning_bess_cycle_cost_cny = Expression(expr=3.0)
    model.planning_bess_variable_om_cost_cny = Expression(expr=4.0)
    model.planning_total_cost_cny = Expression(
        expr=(
            model.annual_operating_cost_cny
            + model.planning_storage_capacity_cost_cny
            + model.planning_bess_cycle_cost_cny
            + model.planning_bess_variable_om_cost_cny
        )
    )
    model.planning_cost = Objective(
        expr=model.planning_total_cost_cny,
        sense=minimize,
    )
    return model


def _pipeline_model():
    from pyomo.environ import (
        Binary,
        Block,
        ConcreteModel,
        Constraint,
        Expression,
        NonNegativeReals,
        Objective,
        RangeSet,
        Var,
        minimize,
    )

    from tes_bess_boundary.e0d40_full_year_compute_gate import (
        PCC_EXPORT_TARGET_MWH,
    )

    model = ConcreteModel()
    model.periods = RangeSet(0, 0)
    model.unit_index = RangeSet(0, 0)
    model.chp = Block(model.unit_index)
    block = model.chp[0]
    block.fuel_segment_index = RangeSet(0, 1)
    block.fuel_code_bit_index = RangeSet(0, 0)
    block.online = Var(model.periods, domain=Binary)
    block.fuel_segment_active = Var(
        model.periods,
        block.fuel_segment_index,
        domain=NonNegativeReals,
        bounds=(0.0, 1.0),
    )
    block.fuel_code_bit = Var(
        model.periods,
        block.fuel_code_bit_index,
        domain=Binary,
    )
    block.require_online = Constraint(expr=block.online[0] == 1)
    block.segment_sum = Constraint(
        expr=sum(block.fuel_segment_active[0, segment] for segment in (0, 1))
        == block.online[0]
    )
    block.code = Constraint(
        expr=block.fuel_segment_active[0, 1] == block.fuel_code_bit[0, 0]
    )

    model.bess = Block()
    model.bess.installed = Var(domain=Binary)
    model.bess.charge_mode = Var(model.periods, domain=Binary)
    model.bess.charge_ac_mw = Var(model.periods, domain=NonNegativeReals)
    model.bess.discharge_ac_mw = Var(model.periods, domain=NonNegativeReals)
    model.bess.require_installation = Constraint(expr=model.bess.installed == 1)
    model.bess.zero_charge = Constraint(expr=model.bess.charge_ac_mw[0] == 0)
    model.bess.zero_discharge = Constraint(
        expr=model.bess.discharge_ac_mw[0] == 0
    )
    model.bess.zero_mode = Constraint(expr=model.bess.charge_mode[0] == 0)

    model.annual_pcc_export_mwh = Expression(expr=PCC_EXPORT_TARGET_MWH)
    model.annual_curtailment_mwh = Expression(expr=0.0)
    model.annual_operating_cost_cny = Expression(expr=10.0 + block.online[0])
    model.planning_storage_capacity_cost_cny = Expression(
        expr=2.0 + model.bess.installed
    )
    model.planning_bess_cycle_cost_cny = Expression(expr=0.0)
    model.planning_bess_variable_om_cost_cny = Expression(expr=0.0)
    model.planning_total_cost_cny = Expression(
        expr=(
            model.annual_operating_cost_cny
            + model.planning_storage_capacity_cost_cny
            + model.planning_bess_cycle_cost_cny
            + model.planning_bess_variable_om_cost_cny
        )
    )
    model.planning_cost = Objective(
        expr=model.planning_total_cost_cny,
        sense=minimize,
    )
    return model


def _gate_a_24h_case(architecture):
    from tes_bess_boundary.capacity_planning import (
        BESSPlanningBounds,
        BESSPlanningSpec,
        TESPlanningBounds,
        TESPlanningSpec,
    )
    from tes_bess_boundary.components.chp import (
        CHPCommitmentSpec,
        CHPFeasibleRegion,
        CHPFuelPoint,
        CHPUnitSpec,
        CHPVertex,
        CommitmentTransitionFormulation,
        FuelSegmentFormulation,
        HeatBasis,
        LowLoadFuelRule,
    )
    from tes_bess_boundary.components.molten_salt import MoltenSaltPhysics
    from tes_bess_boundary.economics import (
        AnnualHorizonSpec,
        PriceBasisConversion,
        ProjectFinance,
    )
    from tes_bess_boundary.formal_bess_costs import (
        build_resolved_rahman_bess_join_contract,
    )
    from tes_bess_boundary.model import (
        AnnualCurtailmentServiceSpec,
        AnnualPCCExportServiceSpec,
        Architecture,
        E0CTimeSeries,
        ValidationObjectiveSpec,
    )
    from tes_bess_boundary.planning_model import EndogenousCapacityCase
    from tes_bess_boundary.public_tes_costs import (
        build_public_tes_cost_portfolio,
    )

    includes_bess = architecture in (Architecture.BESS, Architecture.HYBRID)
    includes_tes = architecture in (Architecture.TES, Architecture.HYBRID)
    chp = CHPCommitmentSpec(
        unit=CHPUnitSpec(
            name="d46_gate_a_chp",
            feasible_region=CHPFeasibleRegion(
                (
                    CHPVertex(400.0, 0.0),
                    CHPVertex(700.0, 0.0),
                    CHPVertex(400.0, 100.0),
                )
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.05,
        ),
        fuel_points=(
            CHPFuelPoint(400.0, 300.0),
            CHPFuelPoint(700.0, 280.0),
        ),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
    )
    bess = (
        BESSPlanningSpec(
            bounds=BESSPlanningBounds(2_400.0, 100.0, 100.0),
            soc_min=0.1,
            soc_max=0.9,
            charge_efficiency=0.95,
            discharge_efficiency=0.95,
            initial_soc_fraction=0.5,
            cyclic=True,
        )
        if includes_bess
        else None
    )
    bess_economics = (
        build_resolved_rahman_bess_join_contract().build_planning_economics(
            finance=ProjectFinance(project_years=20, real_discount_rate=0.10),
            conversion=PriceBasisConversion(
                source_currency="USD",
                source_price_base_year=2019,
                target_currency="CNY",
                target_price_base_year=2024,
                source_price_index=255.657,
                target_price_index=313.689,
                target_currency_per_source_currency=7.1217,
                price_index_series_id="D46 toy CPI",
                exchange_rate_series_id="D46 toy FX",
            ),
            reference_annual_ac_efc=365.0,
            ac_deliverable_fraction=0.8 * 0.95,
        )
        if includes_bess
        else None
    )
    tes = (
        TESPlanningSpec(
            physics_template=MoltenSaltPhysics(
                salt_mass_t=1.0,
                ht_tank_capacity_t=1.0,
                mt_tank_capacity_t=1.0,
                lt_tank_capacity_t=1.0,
                specific_heat_mwh_per_tonne_k=0.0004,
                temperature_ht=565.0,
                temperature_mt=425.0,
                temperature_lt=290.0,
                electric_heater_efficiency=0.95,
                steam_to_ht_efficiency=0.95,
                steam_to_mt_efficiency=0.95,
                power_block_efficiency=0.4,
                heat_exchanger_efficiency=0.95,
            ),
            bounds=TESPlanningBounds(
                salt_mass_upper_t=55_654.86255374656,
                ht_tank_capacity_upper_t=55_654.86255374656,
                mt_tank_capacity_upper_t=55_654.86255374656,
                lt_tank_capacity_upper_t=55_654.86255374656,
                electric_charge_input_upper_mw=300.0,
                steam_to_ht_input_upper_mw=300.0,
                steam_to_mt_input_upper_mw=300.0,
                electric_output_upper_mw=300.0,
                heat_output_upper_mw=300.0,
            ),
            initial_inventory_fractions=(0.0, 0.0, 1.0),
            cyclic=True,
        )
        if includes_tes
        else None
    )
    return EndogenousCapacityCase(
        architecture=architecture,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(10.0,) * 24,
            wind_available_mw=(0.0,) * 24,
            pv_available_mw=(0.0,) * 24,
        ),
        chp_units=(chp,),
        chp_initial_online=(1,),
        chp_terminal_online=(1,),
        pcc_export_capacity_mw=700.0,
        horizon=AnnualHorizonSpec((366.0,) * 24),
        bess=bess,
        bess_economics=bess_economics,
        tes=tes,
        tes_cost_portfolio=(
            build_public_tes_cost_portfolio(
                "aggregate_storage",
                "base",
                acknowledge_author_assumptions=True,
            )
            if includes_tes
            else None
        ),
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=800.0,
            curtailment_penalty_cny_per_mwh=0.0,
        ),
        curtailment_service=AnnualCurtailmentServiceSpec(
            service_id="d46-gate-a-curtailment",
            maximum_curtailment_mwh=339_569.90645758656,
        ),
        pcc_export_service=AnnualPCCExportServiceSpec(
            service_id="d46-gate-a-export",
            target_export_mwh=4_035_354.738554194,
        ),
        chp_fuel_segment_formulation=FuelSegmentFormulation.LOGARITHMIC,
        chp_transition_formulation=(
            CommitmentTransitionFormulation.CONTINUOUS_ENVELOPE
        ),
    )


def test_capacity_anchor_fixes_only_external_design_variables() -> None:
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        BESS_ENERGY_ANCHOR_MWH,
        BESS_POWER_ANCHOR_MW,
        TES_PORT_ANCHOR_MW,
        TES_TANK_ANCHOR_T,
        fix_engineering_capacity_anchor,
    )
    from tes_bess_boundary.model import Architecture

    model = _seed_model()
    audit = fix_engineering_capacity_anchor(model, Architecture.HYBRID)

    assert audit["passed"] is True
    assert model.bess.energy_capacity_mwh.value == BESS_ENERGY_ANCHOR_MWH
    assert model.bess.charge_power_capacity_mw.value == BESS_POWER_ANCHOR_MW
    assert model.tes.ht_tank_capacity_t.value == TES_TANK_ANCHOR_T
    assert model.tes.heat_output_capacity_mw.value == TES_PORT_ANCHOR_MW
    assert model.bess.installed.value == 1.0
    assert model.tes.salt_mass_t.fixed is False
    assert model.tes.ht_service_salt_mass_t.fixed is False
    assert model.tes.mt_service_salt_mass_t.fixed is False


def test_repair_b_releases_only_continuous_capacity_variables() -> None:
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        fix_engineering_capacity_anchor,
        release_continuous_capacity_variables,
    )
    from tes_bess_boundary.model import Architecture

    model = _seed_model()
    fix_engineering_capacity_anchor(model, Architecture.HYBRID)
    audit = release_continuous_capacity_variables(model, Architecture.HYBRID)

    assert audit["passed"] is True
    assert audit["released_capacity_variable_count"] == 12
    assert model.bess.energy_capacity_mwh.fixed is False
    assert model.tes.heat_output_capacity_mw.fixed is False
    assert model.bess.installed.fixed is True


def test_deterministic_seed_uses_legal_code_and_frozen_tie_breaks() -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        derive_binary_seed,
    )

    model = _seed_model()
    _set_seed_point(model)
    inventory = collect_binary_inventory(model)
    seed = derive_binary_seed(model, inventory)

    assert seed["chp[0].online[0]"] == 1
    assert seed["chp[0].online[1]"] == 0
    # Segments 1 and 2 tie; the smallest index 1 gives bits 01.
    assert seed["chp[0].fuel_code_bit[0,0]"] == 1
    assert seed["chp[0].fuel_code_bit[0,1]"] == 0
    assert seed["chp[0].fuel_code_bit[1,0]"] == 0
    assert seed["chp[0].fuel_code_bit[1,1]"] == 0
    assert seed["bess.installed"] == 1
    assert seed["bess.charge_mode[0]"] == 1
    assert seed["bess.charge_mode[1]"] == 0
    assert seed["tes.ht_receiving_mode[0]"] == 1
    assert seed["tes.ht_receiving_mode[1]"] == 0
    assert seed["tes.mt_direct_charge_mode[0]"] == 0
    assert seed["tes.mt_direct_charge_mode[1]"] == 1
    assert set(seed) == set(inventory.all_names)


def test_deterministic_seed_rejects_unregistered_binary_family() -> None:
    from pyomo.environ import Binary, Var

    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        derive_binary_seed,
    )

    model = _seed_model()
    model.unknown_binary = Var(domain=Binary)
    _set_seed_point(model)
    model.unknown_binary.set_value(0)
    inventory = collect_binary_inventory(model)

    with pytest.raises(ValueError, match="do not cover"):
        derive_binary_seed(model, inventory)


def test_seed_artifact_is_deterministic_and_identity_locked(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        derive_complete_seed,
        read_seed_csv_gz,
        write_seed_csv_gz,
    )

    model = _seed_model()
    _set_seed_point(model)
    inventory = collect_binary_inventory(model)
    values, binaries = derive_complete_seed(model, inventory)
    first = tmp_path / "first.csv.gz"
    second = tmp_path / "second.csv.gz"
    first_audit = write_seed_csv_gz(first, values, binaries)
    second_audit = write_seed_csv_gz(second, values, binaries)

    assert first.read_bytes() == second.read_bytes()
    assert first_audit["file_sha256"] == second_audit["file_sha256"]
    loaded_values, loaded_binaries = read_seed_csv_gz(
        first,
        expected_variable_names=tuple(sorted(values)),
        expected_binary_names=inventory.all_names,
    )
    assert loaded_values == values
    assert loaded_binaries == binaries
    with pytest.raises(ValueError, match="variable names"):
        read_seed_csv_gz(first, expected_variable_names=("wrong",))


def test_locked_d41_bess_guide_is_reencoded_by_d46_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pyomo.environ import Var, value

    import tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair as d46
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )

    model = _seed_model()
    _set_seed_point(model)
    inventory = collect_binary_inventory(model)
    topology = set(inventory.topology_names)
    operational = set(inventory.operational_names)
    guide = tmp_path / "d41.csv.gz"
    with gzip.open(guide, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("variable_name", "value", "variable_class"))
        for variable in sorted(
            model.component_data_objects(Var, active=True, descend_into=True),
            key=lambda item: item.name,
        ):
            variable_class = (
                "topology_binary"
                if variable.name in topology
                else (
                    "operational_binary"
                    if variable.name in operational
                    else "continuous"
                )
            )
            writer.writerow(
                (
                    variable.name,
                    format(float(value(variable)), ".17g"),
                    variable_class,
                )
            )
    monkeypatch.setattr(
        d46,
        "D41_BESS_R1_GUIDE_SHA256",
        hashlib.sha256(guide.read_bytes()).hexdigest(),
    )

    values, binary_seed = d46.convert_d41_bess_guide_to_seed(
        model,
        inventory,
        guide,
    )

    assert binary_seed == d46.derive_binary_seed(model, inventory)
    assert all(values[name] == float(raw) for name, raw in binary_seed.items())

    guide.write_bytes(guide.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        d46.convert_d41_bess_guide_to_seed(model, inventory, guide)


def test_apply_complete_seed_rejects_missing_and_fractional_binary() -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        apply_complete_seed,
        derive_complete_seed,
    )

    source = _seed_model()
    _set_seed_point(source)
    source_inventory = collect_binary_inventory(source)
    values, binaries = derive_complete_seed(source, source_inventory)

    target = _seed_model()
    target_inventory = collect_binary_inventory(target)
    missing = dict(values)
    missing.pop(next(iter(missing)))
    with pytest.raises(ValueError, match="do not match"):
        apply_complete_seed(target, target_inventory, missing, binaries)

    fractional_values = dict(values)
    first_binary = target_inventory.all_names[0]
    fractional_values[first_binary] = 0.5
    with pytest.raises(ValueError, match="binary is invalid"):
        apply_complete_seed(
            target,
            target_inventory,
            fractional_values,
            binaries,
        )


@pytest.mark.solver
def test_r0_guide_and_first_incumbent_pipeline_is_reproducible(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
        apply_relaxation,
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        build_candidate_from_seed,
        solve_continuous_guide,
    )

    guide_model = _pipeline_model()
    guide_inventory = collect_binary_inventory(guide_model)
    apply_relaxation(guide_model, guide_inventory, RelaxationMode.R0)
    seed_path = tmp_path / "guide.csv.gz"
    guide = solve_continuous_guide(
        guide_model,
        guide_inventory,
        seed_output_path=seed_path,
        time_limit_seconds=30.0,
        threads=1,
    )

    assert guide["status"] == "continuous_guide_recovered"
    assert guide["formal_upper_bound_eligible"] is False
    assert seed_path.is_file()

    candidate_model = _pipeline_model()
    candidate_inventory = collect_binary_inventory(candidate_model)
    candidate_path = tmp_path / "candidate.csv.gz"
    candidate = build_candidate_from_seed(
        candidate_model,
        candidate_inventory,
        seed_path=seed_path,
        candidate_output_path=candidate_path,
        time_limit_seconds=30.0,
        threads=1,
    )

    assert candidate["status"] == "candidate_incumbent_captured"
    assert candidate["formal_upper_bound_eligible"] is False
    assert candidate["binary_snapshot_variable_count"] == 4
    assert candidate_path.is_file()


@pytest.mark.solver
@pytest.mark.integration
@pytest.mark.parametrize("architecture_name", ["bess", "tes", "hybrid"])
def test_gate_a_24h_original_model_rebuild_recovers_toy_upper_bound(
    tmp_path: Path,
    architecture_name: str,
) -> None:
    from pyomo.environ import Var

    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
        apply_relaxation,
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        build_candidate_from_seed,
        fix_engineering_capacity_anchor,
        read_seed_csv_gz,
        solve_continuous_guide,
        solve_fixed_binary_repair,
    )
    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.planning_model import build_endogenous_capacity_model

    architecture = Architecture(architecture_name)
    case = _gate_a_24h_case(architecture)
    guide_model = build_endogenous_capacity_model(case)
    guide_inventory = collect_binary_inventory(guide_model)
    assert fix_engineering_capacity_anchor(
        guide_model,
        architecture,
    )["passed"]
    assert apply_relaxation(
        guide_model,
        guide_inventory,
        RelaxationMode.R0,
    )["passed"]
    seed_path = tmp_path / f"{architecture_name}_guide.csv.gz"
    guide = solve_continuous_guide(
        guide_model,
        guide_inventory,
        seed_output_path=seed_path,
        time_limit_seconds=30.0,
        threads=1,
    )
    assert guide["status"] == "continuous_guide_recovered"

    if architecture is Architecture.BESS:
        rejection_model = build_endogenous_capacity_model(case)
        rejection_inventory = collect_binary_inventory(rejection_model)
        assert fix_engineering_capacity_anchor(
            rejection_model,
            architecture,
        )["passed"]
        rejected = build_candidate_from_seed(
            rejection_model,
            rejection_inventory,
            seed_path=seed_path,
            candidate_output_path=tmp_path / "explicitly_rejected.csv.gz",
            time_limit_seconds=30.0,
            threads=1,
            stop_on_explicit_seed_rejection=True,
        )
        assert rejected["status"] == "seed_explicitly_rejected"
        assert rejected["seed_explicitly_rejected"] is True

    candidate_model = build_endogenous_capacity_model(case)
    candidate_inventory = collect_binary_inventory(candidate_model)
    assert fix_engineering_capacity_anchor(
        candidate_model,
        architecture,
    )["passed"]
    candidate_path = tmp_path / f"{architecture_name}_candidate.csv.gz"
    candidate = build_candidate_from_seed(
        candidate_model,
        candidate_inventory,
        seed_path=seed_path,
        candidate_output_path=candidate_path,
        time_limit_seconds=30.0,
        threads=1,
    )
    assert candidate["status"] == "candidate_incumbent_captured"

    repair_model = build_endogenous_capacity_model(case)
    repair_inventory = collect_binary_inventory(repair_model)
    assert fix_engineering_capacity_anchor(
        repair_model,
        architecture,
    )["passed"]
    _, snapshot = read_seed_csv_gz(
        candidate_path,
        expected_variable_names=tuple(
            sorted(
                variable.name
                for variable in repair_model.component_data_objects(
                    Var,
                    active=True,
                    descend_into=True,
                )
            )
        ),
        expected_binary_names=repair_inventory.all_names,
    )
    repaired = solve_fixed_binary_repair(
        repair_model,
        repair_inventory,
        snapshot,
        time_limit_seconds=30.0,
        architecture=architecture,
        threads=1,
        require_named_constraint_groups=True,
    )
    assert repaired["status"] == "audited_feasible_upper_bound_recovered"
    assert repaired["solution_audit"]["passed"] is True
    assert (
        repaired["solution_audit"]["audited_feasible_upper_bound_cny"]
        is not None
    )


@pytest.mark.solver
def test_first_incumbent_callback_captures_complete_solution() -> None:
    from pyomo.environ import (
        Binary,
        ConcreteModel,
        Constraint,
        Objective,
        RangeSet,
        Var,
        minimize,
    )

    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        capture_first_incumbent,
    )

    model = ConcreteModel()
    model.item_index = RangeSet(0, 7)
    model.select = Var(model.item_index, domain=Binary)
    model.require = Constraint(
        expr=sum(model.select[index] for index in model.item_index) >= 4
    )
    model.cost = Objective(
        expr=sum(
            (index + 1) * model.select[index] for index in model.item_index
        ),
        sense=minimize,
    )
    for index in model.item_index:
        model.select[index].set_value(int(index < 4))

    result = capture_first_incumbent(model, time_limit_seconds=30.0, threads=1)

    assert result["incumbent_captured"] is True
    assert result["variable_count"] == 8
    assert all(math.isfinite(value) for value in result["variable_values"].values())
    assert all(value in (0.0, 1.0) for value in result["variable_values"].values())


@pytest.mark.solver
def test_fixed_binary_repair_grants_upward_rounded_upper_bound() -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        fix_engineering_capacity_anchor,
        solve_fixed_binary_repair,
    )
    from tes_bess_boundary.model import Architecture

    model = _repair_model()
    inventory = collect_binary_inventory(model)
    fix_engineering_capacity_anchor(model, Architecture.BESS)
    result = solve_fixed_binary_repair(
        model,
        inventory,
        {"bess.installed": 1},
        time_limit_seconds=30.0,
        architecture=Architecture.BESS,
        threads=1,
    )

    assert result["status"] == "audited_feasible_upper_bound_recovered"
    assert result["solution_audit"]["passed"] is True
    assert result["solution_audit"]["audited_feasible_upper_bound_cny"] == (
        "21.0000000000"
    )
    assert result["formal_project_tac_ready"] is False
    assert result["technical_ranking_permitted"] is False


@pytest.mark.solver
def test_repair_rejects_service_residual_even_when_solver_is_feasible() -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        fix_engineering_capacity_anchor,
        solve_fixed_binary_repair,
    )
    from tes_bess_boundary.model import Architecture

    model = _repair_model(export_offset_mwh=1.0)
    inventory = collect_binary_inventory(model)
    fix_engineering_capacity_anchor(model, Architecture.BESS)
    result = solve_fixed_binary_repair(
        model,
        inventory,
        {"bess.installed": 0},
        time_limit_seconds=30.0,
        architecture=Architecture.BESS,
        threads=1,
    )

    assert result["status"] == "fixed_binary_repair_failed"
    assert result["solution_audit"]["service"]["passed"] is False
    assert result["solution_audit"]["audited_feasible_upper_bound_cny"] is None


def test_repair_b_failure_never_revokes_repair_a_and_cheaper_b_can_win() -> None:
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        select_preferred_repair,
    )

    repair_a = {
        "repair": "A",
        "solution_audit": {
            "passed": True,
            "audited_feasible_upper_bound_cny": "100.0000000000",
            "objective": {"model_objective_cny": 100.0},
        },
    }
    failed_b = {
        "repair": "B",
        "solution_audit": {"passed": False},
    }
    selected = select_preferred_repair(repair_a, failed_b)
    assert selected["selected_repair"] == "A"
    assert selected["repair_a_preserved_on_repair_b_failure"] is True

    repair_b = {
        "repair": "B",
        "solution_audit": {
            "passed": True,
            "audited_feasible_upper_bound_cny": "90.0000000000",
            "objective": {"model_objective_cny": 90.0},
        },
    }
    selected = select_preferred_repair(repair_a, repair_b)
    assert selected["selected_repair"] == "B"
