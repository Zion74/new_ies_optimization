from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest


QUALITY_COUNT_COLUMNS = (
    "source_duplicate_count",
    "non_grid_excluded_count",
    "sentinel_interpolated_count",
    "signed_reverse_flow_count",
    "resident_negative_count",
    "all_signal_zero_count",
    "zero_segment_imputed_count",
    "dongfang_sign_mismatch_count",
)


def _formal_data_dir() -> Path:
    configured = os.environ.get("TES_BESS_E0B_FORMAL_DIR")
    if configured:
        return Path(configured)
    package_root = Path(__file__).resolve().parents[1]
    return package_root.parent / "数据采集" / "e0b_formal_2024"


def _write_hourly_fixture(tmp_path, values):
    path = tmp_path / "e0b_heat_hourly_2024.csv"
    fieldnames = (
        "timestamp",
        "heat_net_mw",
        "heat_forward_mw",
        "heat_zero_sensitivity_mw",
        "source_sample_count",
        *QUALITY_COUNT_COLUMNS,
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for hour, (net, forward, zero_sensitivity) in enumerate(values):
            writer.writerow(
                {
                    "timestamp": f"2024-01-01T{hour:02d}:00:00",
                    "heat_net_mw": net,
                    "heat_forward_mw": forward,
                    "heat_zero_sensitivity_mw": zero_sensitivity,
                    "source_sample_count": 6,
                    **{column: 0 for column in QUALITY_COUNT_COLUMNS},
                }
            )
    return path


def test_net_clipped_preserves_the_signed_source_and_audits_the_boundary_change(
    tmp_path,
) -> None:
    from tes_bess_boundary.heat_adapter import (
        HeatDemandAdapterSpec,
        HeatDemandInterpretation,
        HeatDemandModification,
        adapt_e0b_heat_demand,
    )

    hourly_csv = _write_hourly_fixture(
        tmp_path,
        values=((4.0, 4.5, 4.0), (-1.25, 0.75, -1.25), (0.0, 0.0, 0.0)),
    )

    adapted = adapt_e0b_heat_demand(
        hourly_csv,
        spec=HeatDemandAdapterSpec(
            interpretation=HeatDemandInterpretation.NET_CLIPPED,
            enforce_formal_contract=False,
        ),
    )

    expected_modification = HeatDemandModification(
        timestamp=datetime(2024, 1, 1, 1),
        source_value_mw=-1.25,
        model_value_mw=0.0,
        clipped_amount_mw=1.25,
    )
    assert adapted.timestamps == tuple(
        datetime(2024, 1, 1, hour) for hour in range(3)
    )
    assert adapted.source_values_mw == (4.0, -1.25, 0.0)
    assert adapted.values_mw == (4.0, 0.0, 0.0)
    assert adapted.full_source_modifications == (expected_modification,)
    assert adapted.window_modifications == (expected_modification,)


@pytest.mark.parametrize(
    ("interpretation_name", "expected_source", "expected_model", "modification_count"),
    (
        ("FORWARD", 2.0, 2.0, 0),
        ("ZERO_SENSITIVITY_CLIPPED", -3.0, 0.0, 1),
    ),
)
def test_registered_sensitivity_interpretations_consume_their_e0b_columns(
    tmp_path,
    interpretation_name,
    expected_source,
    expected_model,
    modification_count,
) -> None:
    from tes_bess_boundary.heat_adapter import (
        HeatDemandAdapterSpec,
        HeatDemandInterpretation,
        adapt_e0b_heat_demand,
    )

    hourly_csv = _write_hourly_fixture(
        tmp_path,
        values=((-1.0, 2.0, -3.0),),
    )

    adapted = adapt_e0b_heat_demand(
        hourly_csv,
        spec=HeatDemandAdapterSpec(
            interpretation=getattr(HeatDemandInterpretation, interpretation_name),
            enforce_formal_contract=False,
        ),
    )

    assert adapted.source_values_mw == (expected_source,)
    assert adapted.values_mw == (expected_model,)
    assert len(adapted.full_source_modifications) == modification_count


@pytest.mark.parametrize(
    ("values", "error_match"),
    (
        ((1.0, "nan", 1.0), "candidate heat columns must be finite"),
        ((1.0, -0.01, 1.0), "heat_forward_mw must be non-negative"),
    ),
)
def test_every_candidate_series_is_validated_before_one_interpretation_is_selected(
    tmp_path,
    values,
    error_match,
) -> None:
    from tes_bess_boundary.heat_adapter import (
        HeatDemandAdapterSpec,
        HeatDemandInterpretation,
        adapt_e0b_heat_demand,
    )

    hourly_csv = _write_hourly_fixture(tmp_path, values=(values,))

    with pytest.raises(ValueError, match=error_match):
        adapt_e0b_heat_demand(
            hourly_csv,
            spec=HeatDemandAdapterSpec(
                interpretation=HeatDemandInterpretation.NET_CLIPPED,
                enforce_formal_contract=False,
            ),
        )


def test_formal_mode_requires_the_companion_manifest_to_be_explicit(tmp_path) -> None:
    from tes_bess_boundary.heat_adapter import (
        HeatDemandAdapterSpec,
        HeatDemandInterpretation,
        adapt_e0b_heat_demand,
    )

    hourly_csv = _write_hourly_fixture(tmp_path, values=((1.0, 1.0, 1.0),))

    with pytest.raises(ValueError, match="source_manifest is required"):
        adapt_e0b_heat_demand(
            hourly_csv,
            spec=HeatDemandAdapterSpec(
                interpretation=HeatDemandInterpretation.NET_CLIPPED,
            ),
        )


@pytest.mark.data_integration
@pytest.mark.parametrize(
    ("interpretation_name", "expected_energy_mwh", "expected_modifications"),
    (
        ("NET_CLIPPED", 1_395_670.599074074, 1),
        ("FORWARD", 1_396_218.455092593, 0),
        ("ZERO_SENSITIVITY_CLIPPED", 1_398_529.574074074, 1),
    ),
)
def test_formal_2024_source_reproduces_the_independent_full_year_goldens(
    interpretation_name,
    expected_energy_mwh,
    expected_modifications,
) -> None:
    from tes_bess_boundary.heat_adapter import (
        HeatDemandAdapterSpec,
        HeatDemandInterpretation,
        adapt_e0b_heat_demand,
    )

    formal_dir = _formal_data_dir()

    adapted = adapt_e0b_heat_demand(
        formal_dir / "e0b_heat_hourly_2024.csv",
        spec=HeatDemandAdapterSpec(
            interpretation=getattr(HeatDemandInterpretation, interpretation_name),
        ),
        source_manifest=formal_dir / "manifest.json",
    )

    assert len(adapted.timestamps) == 8_784
    assert adapted.timestamps[0] == datetime(2024, 1, 1)
    assert adapted.timestamps[-1] == datetime(2024, 12, 31, 23)
    assert math.fsum(adapted.values_mw) == pytest.approx(
        expected_energy_mwh, abs=1e-6
    )
    assert len(adapted.full_source_modifications) == expected_modifications
    if expected_modifications:
        modification = adapted.full_source_modifications[0]
        assert modification.timestamp == datetime(2024, 5, 27, 2)
        assert modification.source_value_mw == pytest.approx(-1.195370370370)
        assert modification.model_value_mw == 0.0


@pytest.mark.data_integration
@pytest.mark.parametrize(
    (
        "start",
        "interpretation_name",
        "expected_energy_mwh",
        "expected_peak_mw",
        "expected_full_modifications",
        "expected_window_modifications",
    ),
    (
        (datetime(2024, 5, 27), "NET_CLIPPED", 564.469444444444, 74.150462962963, 1, 1),
        (datetime(2024, 5, 27), "FORWARD", 569.646296296297, 74.150462962963, 0, 0),
        (
            datetime(2024, 5, 27),
            "ZERO_SENSITIVITY_CLIPPED",
            564.469444444444,
            74.150462962963,
            1,
            1,
        ),
        (datetime(2024, 10, 11), "NET_CLIPPED", 0.0, 0.0, 1, 0),
        (datetime(2024, 10, 11), "FORWARD", 0.0, 0.0, 0, 0),
        (
            datetime(2024, 10, 11),
            "ZERO_SENSITIVITY_CLIPPED",
            1_872.258101851853,
            87.315740740741,
            1,
            0,
        ),
    ),
)
def test_formal_windows_are_half_open_and_keep_full_source_audit_separate(
    start,
    interpretation_name,
    expected_energy_mwh,
    expected_peak_mw,
    expected_full_modifications,
    expected_window_modifications,
) -> None:
    from tes_bess_boundary.heat_adapter import (
        HeatDemandAdapterSpec,
        HeatDemandInterpretation,
        HourlyWindow,
        adapt_e0b_heat_demand,
    )

    formal_dir = _formal_data_dir()

    adapted = adapt_e0b_heat_demand(
        formal_dir / "e0b_heat_hourly_2024.csv",
        spec=HeatDemandAdapterSpec(
            interpretation=getattr(HeatDemandInterpretation, interpretation_name),
            window=HourlyWindow(start=start, hours=24),
        ),
        source_manifest=formal_dir / "manifest.json",
    )

    assert len(adapted.timestamps) == 24
    assert adapted.timestamps[0] == start
    assert adapted.timestamps[-1] == start.replace(hour=23)
    assert math.fsum(adapted.values_mw) == pytest.approx(
        expected_energy_mwh, abs=1e-6
    )
    assert max(adapted.values_mw) == pytest.approx(expected_peak_mw, abs=1e-9)
    assert len(adapted.full_source_modifications) == expected_full_modifications
    assert len(adapted.window_modifications) == expected_window_modifications


def test_adapter_export_is_deterministic_and_carries_the_complete_audit(tmp_path) -> None:
    from tes_bess_boundary.heat_adapter import (
        HeatDemandAdapterSpec,
        HeatDemandInterpretation,
        adapt_e0b_heat_demand,
        write_adapted_heat_demand,
    )

    hourly_csv = _write_hourly_fixture(
        tmp_path,
        values=((4.0, 4.5, 4.0), (-1.25, 0.75, -1.25), (0.0, 0.0, 0.0)),
    )
    adapted = adapt_e0b_heat_demand(
        hourly_csv,
        spec=HeatDemandAdapterSpec(
            interpretation=HeatDemandInterpretation.NET_CLIPPED,
            enforce_formal_contract=False,
        ),
    )

    first = write_adapted_heat_demand(adapted, tmp_path / "first")
    second = write_adapted_heat_demand(adapted, tmp_path / "second")

    assert first.csv_path.name == "e0c_heat_demand_2024_net_clipped.csv"
    assert first.manifest_path.name == (
        "e0c_heat_demand_2024_net_clipped.manifest.json"
    )
    assert first.csv_path.read_bytes() == second.csv_path.read_bytes()
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()
    assert b"\r\n" not in first.manifest_path.read_bytes()
    assert first.output_sha256[first.csv_path.name] == hashlib.sha256(
        first.csv_path.read_bytes()
    ).hexdigest()
    assert first.output_sha256[first.manifest_path.name] == hashlib.sha256(
        first.manifest_path.read_bytes()
    ).hexdigest()

    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "tes_bess_boundary.e0c_heat_demand_adapter.v1"
    assert manifest["interpretation"] == "net_clipped"
    assert manifest["scientific_status"] == "primary"
    assert manifest["source"]["hourly_csv"] == hourly_csv.name
    assert manifest["source"]["hourly_csv_sha256"] == hashlib.sha256(
        hourly_csv.read_bytes()
    ).hexdigest()
    assert manifest["source"]["manifest"] is None
    assert manifest["audit"]["full_source"]["rows"] == 3
    assert manifest["audit"]["full_source"]["energy_before_mwh"] == 2.75
    assert manifest["audit"]["full_source"]["energy_after_mwh"] == 4.0
    assert manifest["audit"]["selection"]["rows"] == 3
    assert manifest["audit"]["selection"]["modifications"] == [
        {
            "clipped_amount_mw": 1.25,
            "model_value_mw": 0.0,
            "source_value_mw": -1.25,
            "timestamp": "2024-01-01T01:00:00",
        }
    ]
    assert manifest["audit"]["selection"]["quality_count_sums"] == {
        column: 0 for column in QUALITY_COUNT_COLUMNS
    }
    assert manifest["output"]["csv_sha256"] == first.output_sha256[
        first.csv_path.name
    ]


@pytest.mark.parametrize(
    ("start", "hours", "error_match"),
    (
        (datetime(2024, 1, 1, 0, 30), 24, "naive whole hour"),
        (datetime(2024, 1, 1, tzinfo=timezone.utc), 24, "naive whole hour"),
        (datetime(2024, 1, 1), 0, "positive integer"),
        (datetime(2024, 1, 1), True, "positive integer"),
    ),
)
def test_hourly_window_rejects_ambiguous_or_non_positive_boundaries(
    start, hours, error_match
) -> None:
    from tes_bess_boundary.heat_adapter import HourlyWindow

    with pytest.raises(ValueError, match=error_match):
        HourlyWindow(start=start, hours=hours)


@pytest.mark.data_integration
@pytest.mark.parametrize(
    ("mutation", "error_match"),
    (
        ("schema", "source manifest schema"),
        ("formal_ready", "formal_ready"),
        ("year", "manifest year"),
        ("rows", "row count"),
        ("sha256", "SHA-256"),
    ),
)
def test_formal_manifest_contract_rejects_tampering(
    tmp_path, mutation, error_match
) -> None:
    from tes_bess_boundary.heat_adapter import (
        HeatDemandAdapterSpec,
        HeatDemandInterpretation,
        adapt_e0b_heat_demand,
    )

    formal_dir = _formal_data_dir()
    hourly_csv = formal_dir / "e0b_heat_hourly_2024.csv"
    manifest = json.loads((formal_dir / "manifest.json").read_text(encoding="utf-8"))
    if mutation == "schema":
        manifest["schema"] = "wrong"
    elif mutation == "formal_ready":
        manifest["formal_ready"] = 1
    elif mutation == "year":
        manifest["year"] = 2023
    elif mutation == "rows":
        manifest["outputs"][hourly_csv.name]["rows"] = 8_783
    else:
        manifest["outputs"][hourly_csv.name]["sha256"] = "0" * 64
    tampered_manifest = tmp_path / "manifest.json"
    tampered_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match=error_match):
        adapt_e0b_heat_demand(
            hourly_csv,
            spec=HeatDemandAdapterSpec(
                interpretation=HeatDemandInterpretation.NET_CLIPPED,
            ),
            source_manifest=tampered_manifest,
        )


@pytest.mark.data_integration
def test_a_malformed_row_outside_the_requested_window_still_rejects_the_source(
    tmp_path,
) -> None:
    from tes_bess_boundary.heat_adapter import (
        HeatDemandAdapterSpec,
        HeatDemandInterpretation,
        HourlyWindow,
        adapt_e0b_heat_demand,
    )

    formal_dir = _formal_data_dir()
    source_path = formal_dir / "e0b_heat_hourly_2024.csv"
    rows = list(csv.reader(source_path.open("r", encoding="utf-8", newline="")))
    zero_column = rows[0].index("heat_zero_sensitivity_mw")
    rows[-1][zero_column] = "nan"
    malformed_path = tmp_path / source_path.name
    with malformed_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows(rows)

    with pytest.raises(ValueError, match="candidate heat columns must be finite"):
        adapt_e0b_heat_demand(
            malformed_path,
            spec=HeatDemandAdapterSpec(
                interpretation=HeatDemandInterpretation.NET_CLIPPED,
                window=HourlyWindow(start=datetime(2024, 5, 27), hours=24),
            ),
            source_manifest=formal_dir / "manifest.json",
        )


@pytest.mark.solver
@pytest.mark.integration
@pytest.mark.data_integration
@pytest.mark.parametrize(
    ("start", "interpretation_name", "expected_fuel_tce", "expected_pcc_mwh"),
    (
        (
            datetime(2024, 5, 27),
            "NET_CLIPPED",
            813.568638503642,
            2_149.135713393343,
        ),
        (
            datetime(2024, 5, 27),
            "FORWARD",
            848.941188003801,
            2_242.576396584357,
        ),
        (
            datetime(2024, 5, 27),
            "ZERO_SENSITIVITY_CLIPPED",
            813.568638503642,
            2_149.135713393343,
        ),
        (datetime(2024, 10, 11), "NET_CLIPPED", 0.0, 0.0),
        (datetime(2024, 10, 11), "FORWARD", 0.0, 0.0),
        (
            datetime(2024, 10, 11),
            "ZERO_SENSITIVITY_CLIPPED",
            852.127253672083,
            2_250.992757772414,
        ),
    ),
)
def test_adapted_values_bridge_to_six_optimal_real_chp_diagnostics(
    start,
    interpretation_name,
    expected_fuel_tce,
    expected_pcc_mwh,
) -> None:
    from tes_bess_boundary.components.chp import LowLoadFuelRule, yangling_chp_specs
    from tes_bess_boundary.heat_adapter import (
        HeatDemandAdapterSpec,
        HeatDemandInterpretation,
        HourlyWindow,
        adapt_e0b_heat_demand,
    )
    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
        solve_e0c,
    )
    from tes_bess_boundary.solver import create_highs_solver

    formal_dir = _formal_data_dir()
    adapted = adapt_e0b_heat_demand(
        formal_dir / "e0b_heat_hourly_2024.csv",
        spec=HeatDemandAdapterSpec(
            interpretation=getattr(HeatDemandInterpretation, interpretation_name),
            window=HourlyWindow(start=start, hours=24),
        ),
        source_manifest=formal_dir / "manifest.json",
    )
    period_count = len(adapted.values_mw)
    case = E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries(
            heat_demand_mw=adapted.values_mw,
            wind_available_mw=(0.0,) * period_count,
            pv_available_mw=(0.0,) * period_count,
        ),
        chp_units=yangling_chp_specs(
            low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE
        ),
        chp_initial_online=(0, 0),
        pcc_export_capacity_mw=700.0,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=1.0,
            curtailment_penalty_cny_per_mwh=0.0,
            cycle_event_cost_proxy_cny=None,
        ),
    )

    result = solve_e0c(
        case,
        solver=create_highs_solver(threads=1, random_seed=0, mip_rel_gap=0.0),
    )

    assert result.termination == "optimal"
    assert result.mip_gap == pytest.approx(0.0, abs=1e-12)
    assert result.fuel_tce == pytest.approx(expected_fuel_tce, abs=1e-8)
    assert result.objective_value == pytest.approx(expected_fuel_tce, abs=1e-8)
    assert result.pcc_export_mwh == pytest.approx(expected_pcc_mwh, abs=1e-8)
    assert result.max_pcc_balance_residual_mw <= 1e-8
    assert result.max_heat_balance_residual_mw <= 1e-8
