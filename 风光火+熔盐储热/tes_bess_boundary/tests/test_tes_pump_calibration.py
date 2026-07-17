from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import fields

import pytest


def test_wang_hitec_properties_and_sensible_capacity_have_numeric_golds() -> None:
    from tes_bess_boundary.tes_pump_calibration import (
        hitec_density_kg_per_m3,
        hitec_sensible_energy_mwh_per_tonne,
        hitec_specific_heat_j_per_kg_k,
    )

    assert hitec_density_kg_per_m3(180.0) == pytest.approx(2153.36)
    assert hitec_density_kg_per_m3(390.0) == pytest.approx(1996.28)
    assert hitec_specific_heat_j_per_kg_k(180.0) == pytest.approx(1489.0)
    assert hitec_specific_heat_j_per_kg_k(390.0) == pytest.approx(1468.0)
    assert hitec_sensible_energy_mwh_per_tonne(180.0, 390.0) == pytest.approx(
        0.08624583333333333
    )


def test_trevisan_hydraulic_anchor_builds_author_pressure_levels() -> None:
    from tes_bess_boundary.tes_pump_calibration import (
        E0D9B2PumpLevel,
        build_e0d9b2_pump_pressure_scenarios,
        build_trevisan_2022_pump_hydraulic_anchor,
    )

    anchor = build_trevisan_2022_pump_hydraulic_anchor()
    scenarios = build_e0d9b2_pump_pressure_scenarios()

    assert anchor.source_doi == "10.1016/j.enconman.2022.116362"
    assert anchor.operating_pressure_pa == pytest.approx(200_000.0)
    assert anchor.loop_pressure_loss_fraction == pytest.approx(0.20)
    assert anchor.active_component_pressure_loss_fraction == pytest.approx(0.05)
    assert anchor.pump_efficiency == pytest.approx(0.90)
    assert tuple(scenario.level for scenario in scenarios) == (
        E0D9B2PumpLevel.LOW,
        E0D9B2PumpLevel.BASE,
        E0D9B2PumpLevel.HIGH,
    )
    assert tuple(scenario.pressure_drop_pa for scenario in scenarios) == pytest.approx(
        (40_000.0, 50_000.0, 200_000.0)
    )
    assert all(
        scenario.parameter_source_id.startswith("author:") for scenario in scenarios
    )
    assert all(
        scenario.evidence_source_ids
        == (
            "doi:10.1016/j.enconman.2022.116362",
            "doi:10.1016/j.apenergy.2025.126876",
        )
        for scenario in scenarios
    )


def test_balanced_mt_path_coefficients_have_numeric_golds() -> None:
    from tes_bess_boundary.tes_pump_calibration import (
        E0D9B2PumpLevel,
        build_e0d9b2_pump_pressure_scenarios,
        calibrate_pump_for_mt,
    )
    from tes_bess_boundary.tes_temperature_scenarios import (
        build_e0d8_hitec_normalized_mt_scenarios,
    )

    point = build_e0d8_hitec_normalized_mt_scenarios().point("balanced_50")
    scenarios = {
        scenario.level: scenario
        for scenario in build_e0d9b2_pump_pressure_scenarios()
    }
    expected = {
        E0D9B2PumpLevel.LOW: (
            0.005733216467,
            0.005733216467,
            0.005733216467,
            0.006184342383,
            0.005950240991,
        ),
        E0D9B2PumpLevel.BASE: (
            0.007166520584,
            0.007166520584,
            0.007166520584,
            0.007730427979,
            0.007437801238,
        ),
        E0D9B2PumpLevel.HIGH: (
            0.028666082337,
            0.028666082337,
            0.028666082337,
            0.030921711915,
            0.029751204954,
        ),
    }

    for level, gold in expected.items():
        calibration = calibrate_pump_for_mt(scenarios[level], point)
        values = tuple(
            getattr(calibration.pump, field.name) for field in fields(calibration.pump)
        )
        assert values == pytest.approx(gold, abs=5e-13)


def test_pump_calibration_is_monotone_in_pressure_and_hotter_mt_temperature() -> None:
    from tes_bess_boundary.tes_pump_calibration import (
        build_e0d9b2_pump_pressure_scenarios,
        calibrate_pump_for_mt,
    )
    from tes_bess_boundary.tes_temperature_scenarios import (
        build_e0d8_hitec_normalized_mt_scenarios,
    )

    points = build_e0d8_hitec_normalized_mt_scenarios().points
    scenarios = build_e0d9b2_pump_pressure_scenarios()
    balanced = points[1]
    by_pressure = [
        calibrate_pump_for_mt(scenario, balanced).pump.heat_mt_to_lt_kwh_per_tonne
        for scenario in scenarios
    ]
    by_mt = [
        calibrate_pump_for_mt(scenarios[1], point).pump.heat_mt_to_lt_kwh_per_tonne
        for point in points
    ]

    assert by_pressure[0] < by_pressure[1] < by_pressure[2]
    assert by_mt[0] < by_mt[1] < by_mt[2]


def test_standard_cycle_has_pre_registered_mass_and_five_path_throughput() -> None:
    from tes_bess_boundary.tes_pump_calibration import (
        build_standard_dual_service_cycle,
    )
    from tes_bess_boundary.tes_temperature_scenarios import (
        build_e0d8_hitec_normalized_mt_scenarios,
    )

    point = build_e0d8_hitec_normalized_mt_scenarios().point("balanced_50")
    cycle = build_standard_dual_service_cycle(point)

    assert cycle.thermal_capacity_mwh == pytest.approx(45.0)
    assert cycle.cycles_per_year == pytest.approx(365.0)
    assert cycle.salt_mass_t == pytest.approx(521.764336441374)
    assert cycle.path_throughput.electric_lt_to_ht_t == pytest.approx(
        cycle.salt_mass_t * 365.0
    )
    assert cycle.path_throughput.steam_lt_to_ht_t == pytest.approx(0.0)
    assert cycle.path_throughput.steam_lt_to_mt_t == pytest.approx(0.0)
    assert cycle.path_throughput.power_ht_to_mt_t == pytest.approx(
        cycle.salt_mass_t * 365.0
    )
    assert cycle.path_throughput.heat_mt_to_lt_t == pytest.approx(
        cycle.salt_mass_t * 365.0
    )
    assert cycle.path_throughput.total_t == pytest.approx(571_331.9484033044)


@pytest.mark.parametrize(
    ("level", "expected_mwh"),
    (
        ("low", 3.4028149656442475),
        ("base", 4.253518707055309),
        ("high", 17.014074828221236),
    ),
)
def test_balanced_standard_cycle_pump_energy_has_numeric_golds(
    level: str,
    expected_mwh: float,
) -> None:
    from tes_bess_boundary.tes_pump_calibration import (
        audit_standard_dual_service_cycle,
        build_e0d9b2_pump_pressure_scenarios,
    )
    from tes_bess_boundary.tes_temperature_scenarios import (
        build_e0d8_hitec_normalized_mt_scenarios,
    )

    point = build_e0d8_hitec_normalized_mt_scenarios().point("balanced_50")
    scenario = next(
        item for item in build_e0d9b2_pump_pressure_scenarios() if item.level.value == level
    )
    audit = audit_standard_dual_service_cycle(scenario, point)

    assert audit.annual_pump_electricity_mwh == pytest.approx(expected_mwh)
    assert audit.trevisan_aggregate_pump_anchor_mwh == pytest.approx(105.55)
    assert audit.aggregate_implied_uniform_kwh_per_tonne == pytest.approx(
        0.18474373837307628
    )
    assert audit.fraction_of_trevisan_pump_anchor == pytest.approx(
        expected_mwh / 105.55
    )
    assert audit.share_of_trevisan_total_electricity == pytest.approx(
        expected_mwh / 21_110.0
    )


def test_bottom_up_base_pump_remains_distinct_from_aggregate_implied_coefficient() -> None:
    from tes_bess_boundary.tes_pump_calibration import (
        E0D9B2PumpLevel,
        audit_standard_dual_service_cycle,
        build_e0d9b2_pump_pressure_scenarios,
    )
    from tes_bess_boundary.tes_temperature_scenarios import (
        build_e0d8_hitec_normalized_mt_scenarios,
    )

    point = build_e0d8_hitec_normalized_mt_scenarios().point("balanced_50")
    base = next(
        item
        for item in build_e0d9b2_pump_pressure_scenarios()
        if item.level is E0D9B2PumpLevel.BASE
    )
    audit = audit_standard_dual_service_cycle(base, point)

    assert audit.fraction_of_trevisan_pump_anchor == pytest.approx(
        0.0402986139948395
    )
    assert audit.aggregate_implied_uniform_kwh_per_tonne > max(
        getattr(audit.path_calibration.pump, field.name)
        for field in fields(audit.path_calibration.pump)
    )


def test_pump_calibration_artifacts_are_deterministic_and_self_hashing(
    tmp_path: object,
) -> None:
    from pathlib import Path

    from tes_bess_boundary.tes_pump_calibration import (
        write_e0d9b2_pump_calibration_artifacts,
    )

    root = Path(str(tmp_path))
    first = write_e0d9b2_pump_calibration_artifacts(root / "first")
    second = write_e0d9b2_pump_calibration_artifacts(root / "second")

    assert first.csv_path.read_bytes() == second.csv_path.read_bytes()
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    with first.csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 9
    assert manifest["schema_id"] == "e0-d-9b-2-pump-calibration-v1"
    assert manifest["row_count"] == 9
    assert manifest["csv_sha256"] == hashlib.sha256(
        first.csv_path.read_bytes()
    ).hexdigest()


@pytest.mark.parametrize(
    ("function_name", "args"),
    (
        ("hitec_density_kg_per_m3", (-300.0,)),
        ("hitec_specific_heat_j_per_kg_k", (float("nan"),)),
        ("hydraulic_pump_specific_energy_kwh_per_tonne", (0.0, 2000.0, 0.9)),
        ("hydraulic_pump_specific_energy_kwh_per_tonne", (40_000.0, 0.0, 0.9)),
        ("hydraulic_pump_specific_energy_kwh_per_tonne", (40_000.0, 2000.0, 0.0)),
    ),
)
def test_pump_calibration_rejects_invalid_physical_inputs(
    function_name: str,
    args: tuple[float, ...],
) -> None:
    from tes_bess_boundary import tes_pump_calibration

    with pytest.raises(ValueError):
        getattr(tes_pump_calibration, function_name)(*args)
