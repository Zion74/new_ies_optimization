"""Price-agnostic settlement exposure for same-annual-PCC dispatch traces."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from tes_bess_boundary.e0d17_exploration import DEFAULT_WINDOWS, E0D17WindowSpec
from tes_bess_boundary.e0d19_same_pcc_service import (
    E0D19PCCTraceRecord,
    E0D19Run,
    run_e0d19,
)

_ENERGY_ABS_TOL_MWH = 1e-5
_D19_CANONICAL_ABS_TOL = 5.1e-4
_CANONICAL_FLOAT_DECIMALS = 9
E0D22_SCHEMA = "tes_bess_boundary.e0d22_pcc_settlement_exposure.v1"
E0D19_SCHEMA = "tes_bess_boundary.e0d19_same_pcc_service.v2"
E0D19_CSV_SHA256 = (
    "4b07e91b010fa9d5aa525f196037bbf0c93bae16ac74035f6ca32292e36cf786"
)
E0D19_MANIFEST_SHA256 = (
    "c112c210aa9a86edfcb116f614c1f4a5da14f314a128e31ee329fbefd65aab63"
)


@dataclass(frozen=True)
class PCCSettlementExposure:
    """Annualized redistribution and price-spread exposure for one trace."""

    window_id: str
    hours: int
    annual_weight_per_hour: float
    common_pcc_export_mwh: float
    comparator_pcc_export_mwh: float
    candidate_pcc_export_mwh: float
    annual_export_difference_mwh: float
    positive_shifted_export_mwh: float
    negative_shifted_export_mwh: float
    gross_absolute_redistribution_mwh: float
    redistributed_export_mwh: float
    redistribution_fraction_of_common_export: float
    max_abs_period_delta_mw: float
    settlement_delta_bound_cny_per_year_per_cny_per_mwh_spread: float
    flat_price_settlement_difference_cny_per_year: float
    time_varying_settlement_complete: bool
    trace_solution_uniqueness_proven: bool
    scientific_status: str


@dataclass(frozen=True)
class E0D22Run:
    d19_run: E0D19Run
    exposures: tuple[PCCSettlementExposure, ...]


@dataclass(frozen=True)
class E0D22Export:
    trace_csv_path: Path
    exposure_csv_path: Path
    manifest_path: Path
    execution_path: Path
    canonical_sha256: dict[str, str]


def _validated_trace(
    trace: Sequence[E0D19PCCTraceRecord],
) -> tuple[E0D19PCCTraceRecord, ...]:
    points = tuple(trace)
    if not points:
        raise ValueError("trace must contain at least one PCC point")
    window_ids = {point.window_id for point in points}
    if len(window_ids) != 1:
        raise ValueError("trace points must belong to one window")
    if tuple(point.period_index for point in points) != tuple(range(len(points))):
        raise ValueError("trace period_index must be contiguous and zero-based")
    weights = {point.annual_weight_per_hour for point in points}
    if len(weights) != 1 or next(iter(weights)) <= 0.0:
        raise ValueError("trace must use one positive annual weight per hour")
    numeric_values = (
        value
        for point in points
        for value in (
            point.comparator_pcc_export_mw,
            point.candidate_pcc_export_mw,
            point.annual_weight_per_hour,
        )
    )
    if not all(math.isfinite(value) for value in numeric_values):
        raise ValueError("trace values must be finite")
    return points


def _annual_delta_energy_mwh(
    trace: Sequence[E0D19PCCTraceRecord],
) -> tuple[float, ...]:
    points = _validated_trace(trace)
    return tuple(
        point.annual_weight_per_hour
        * (point.candidate_pcc_export_mw - point.comparator_pcc_export_mw)
        for point in points
    )


def summarize_pcc_settlement_exposure(
    trace: Sequence[E0D19PCCTraceRecord],
    *,
    common_pcc_export_mwh: float,
    energy_abs_tolerance_mwh: float = _ENERGY_ABS_TOL_MWH,
) -> PCCSettlementExposure:
    """Summarize a selected same-service trace without assigning a price path."""

    points = _validated_trace(trace)
    if not math.isfinite(common_pcc_export_mwh) or common_pcc_export_mwh <= 0.0:
        raise ValueError("common_pcc_export_mwh must be finite and positive")
    if not math.isfinite(energy_abs_tolerance_mwh) or energy_abs_tolerance_mwh < 0.0:
        raise ValueError("energy_abs_tolerance_mwh must be finite and non-negative")
    delta_energy = _annual_delta_energy_mwh(points)
    comparator_export = math.fsum(
        point.annual_weight_per_hour * point.comparator_pcc_export_mw
        for point in points
    )
    candidate_export = math.fsum(
        point.annual_weight_per_hour * point.candidate_pcc_export_mw
        for point in points
    )
    if (
        abs(comparator_export - common_pcc_export_mwh) > energy_abs_tolerance_mwh
        or abs(candidate_export - common_pcc_export_mwh) > energy_abs_tolerance_mwh
    ):
        raise ValueError(
            "trace does not reproduce the common export under the same annual PCC service"
        )
    annual_difference = math.fsum(delta_energy)
    if abs(annual_difference) > energy_abs_tolerance_mwh:
        raise ValueError("trace does not satisfy the same annual PCC service")
    positive_shift = math.fsum(max(value, 0.0) for value in delta_energy)
    negative_shift = -math.fsum(min(value, 0.0) for value in delta_energy)
    gross_redistribution = math.fsum(abs(value) for value in delta_energy)
    redistributed = 0.5 * gross_redistribution
    max_abs_delta = max(
        abs(point.candidate_pcc_export_mw - point.comparator_pcc_export_mw)
        for point in points
    )
    return PCCSettlementExposure(
        window_id=points[0].window_id,
        hours=len(points),
        annual_weight_per_hour=points[0].annual_weight_per_hour,
        common_pcc_export_mwh=common_pcc_export_mwh,
        comparator_pcc_export_mwh=comparator_export,
        candidate_pcc_export_mwh=candidate_export,
        annual_export_difference_mwh=annual_difference,
        positive_shifted_export_mwh=positive_shift,
        negative_shifted_export_mwh=negative_shift,
        gross_absolute_redistribution_mwh=gross_redistribution,
        redistributed_export_mwh=redistributed,
        redistribution_fraction_of_common_export=(
            redistributed / common_pcc_export_mwh
        ),
        max_abs_period_delta_mw=max_abs_delta,
        settlement_delta_bound_cny_per_year_per_cny_per_mwh_spread=(
            redistributed
        ),
        flat_price_settlement_difference_cny_per_year=0.0,
        time_varying_settlement_complete=False,
        trace_solution_uniqueness_proven=False,
        scientific_status=(
            "selected_dispatch_price_spread_exposure_not_formal_tac"
        ),
    )


def settlement_difference_cny_per_year(
    trace: Sequence[E0D19PCCTraceRecord],
    prices_cny_per_mwh: Sequence[float],
) -> float:
    """Evaluate candidate-minus-comparator settlement for an explicit price path."""

    points = _validated_trace(trace)
    prices = tuple(prices_cny_per_mwh)
    if len(prices) != len(points):
        raise ValueError("one price per trace point is required")
    if not all(math.isfinite(price) for price in prices):
        raise ValueError("prices must be finite")
    return math.fsum(
        price * delta_energy
        for price, delta_energy in zip(
            prices, _annual_delta_energy_mwh(points), strict=True
        )
    )


def price_spread_settlement_bound_cny_per_year(
    exposure: PCCSettlementExposure,
    *,
    minimum_price_cny_per_mwh: float,
    maximum_price_cny_per_mwh: float,
) -> float:
    """Return the exact arbitrary-bounded-price envelope for the selected trace."""

    if not all(
        math.isfinite(price)
        for price in (minimum_price_cny_per_mwh, maximum_price_cny_per_mwh)
    ):
        raise ValueError("price bounds must be finite")
    if maximum_price_cny_per_mwh < minimum_price_cny_per_mwh:
        raise ValueError("maximum price must not be below minimum price")
    return (
        maximum_price_cny_per_mwh - minimum_price_cny_per_mwh
    ) * exposure.redistributed_export_mwh


def build_e0d22(d19_run: E0D19Run) -> E0D22Run:
    """Build D22 diagnostics from a freshly solved D19 run with PCC traces."""

    if not isinstance(d19_run, E0D19Run) or not d19_run.records:
        raise ValueError("d19_run must contain same-PCC records")
    exposures: list[PCCSettlementExposure] = []
    for record in d19_run.records:
        trace = tuple(
            point
            for point in d19_run.pcc_traces
            if point.window_id == record.window_id
        )
        if len(trace) != record.hours:
            raise ValueError("D19 run does not contain one PCC trace per period")
        exposures.append(
            summarize_pcc_settlement_exposure(
                trace,
                common_pcc_export_mwh=record.pcc_export_target_mwh,
            )
        )
    if len(d19_run.pcc_traces) != sum(item.hours for item in exposures):
        raise ValueError("D19 run contains unregistered PCC trace points")
    return E0D22Run(d19_run=d19_run, exposures=tuple(exposures))


def run_e0d22(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    windows: tuple[E0D17WindowSpec, ...] = DEFAULT_WINDOWS,
) -> E0D22Run:
    """Re-run the exact D19 service contract and retain selected PCC dispatches."""

    return build_e0d22(run_e0d19(heat_path, vre_path, windows=windows))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_ready(value: object) -> object:
    if isinstance(value, float):
        rounded = round(value, 12)
        return 0.0 if rounded == 0.0 else rounded
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _csv_value(value: object) -> object:
    if isinstance(value, float):
        return f"{value:.{_CANONICAL_FLOAT_DECIMALS}f}"
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _validate_d19_source_lock(
    run: E0D22Run,
    source_dir: Path,
) -> tuple[Path, Path]:
    csv_path = source_dir / "e0d19_same_pcc_service.csv"
    manifest_path = source_dir / "manifest.json"
    if not csv_path.is_file() or not manifest_path.is_file():
        raise ValueError("D22 requires the locked D19 CSV and manifest")
    if _sha256(csv_path) != E0D19_CSV_SHA256:
        raise ValueError("D19 CSV hash does not match the D22 source lock")
    if _sha256(manifest_path) != E0D19_MANIFEST_SHA256:
        raise ValueError("D19 manifest hash does not match the D22 source lock")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != E0D19_SCHEMA:
        raise ValueError("D19 manifest schema is incompatible with D22")
    if manifest.get("output", {}).get("csv_sha256") != E0D19_CSV_SHA256:
        raise ValueError("D19 manifest lost its canonical CSV identity")
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        locked_rows = {
            row["window_id"]: row for row in csv.DictReader(handle)
        }
    fields = (
        "pcc_export_target_mwh",
        "comparator_pcc_export_mwh",
        "candidate_pcc_export_mwh",
        "pcc_export_difference_mwh",
    )
    for current in run.d19_run.records:
        if current.window_id not in locked_rows:
            raise ValueError("D22 window is absent from the locked D19 source")
        locked = locked_rows[current.window_id]
        for field in fields:
            if abs(float(locked[field]) - float(getattr(current, field))) > (
                _D19_CANONICAL_ABS_TOL
            ):
                raise ValueError(f"D22 re-solve does not reproduce D19 field {field}")
    return csv_path, manifest_path


def write_e0d22(
    run: E0D22Run,
    output_dir: str | Path,
    *,
    d19_source_dir: str | Path,
) -> E0D22Export:
    """Write canonical D22 traces, exposure summaries, and a provenance manifest."""

    if not isinstance(run, E0D22Run) or not run.exposures:
        raise ValueError("run must contain E0-D-22 exposure records")
    locked_csv, locked_manifest = _validate_d19_source_lock(
        run, Path(d19_source_dir)
    )
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    trace_csv_path = destination / "e0d22_pcc_dispatch_trace.csv"
    exposure_csv_path = destination / "e0d22_settlement_exposure.csv"
    manifest_path = destination / "manifest.json"
    execution_path = destination / "execution.json"

    trace_fields = (
        "window_id",
        "timestamp",
        "period_index",
        "annual_weight_per_hour",
        "comparator_pcc_export_mw",
        "candidate_pcc_export_mw",
        "delta_pcc_export_mw",
        "annualized_delta_export_energy_mwh",
    )
    with trace_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=trace_fields, lineterminator="\n")
        writer.writeheader()
        for point in run.d19_run.pcc_traces:
            delta_mw = (
                point.candidate_pcc_export_mw
                - point.comparator_pcc_export_mw
            )
            writer.writerow(
                {
                    "window_id": point.window_id,
                    "timestamp": point.timestamp,
                    "period_index": point.period_index,
                    "annual_weight_per_hour": _csv_value(
                        point.annual_weight_per_hour
                    ),
                    "comparator_pcc_export_mw": _csv_value(
                        point.comparator_pcc_export_mw
                    ),
                    "candidate_pcc_export_mw": _csv_value(
                        point.candidate_pcc_export_mw
                    ),
                    "delta_pcc_export_mw": _csv_value(delta_mw),
                    "annualized_delta_export_energy_mwh": _csv_value(
                        point.annual_weight_per_hour * delta_mw
                    ),
                }
            )

    exposure_fields = tuple(asdict(run.exposures[0]))
    with exposure_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=exposure_fields, lineterminator="\n"
        )
        writer.writeheader()
        for exposure in run.exposures:
            writer.writerow(
                {
                    key: _csv_value(value)
                    for key, value in asdict(exposure).items()
                }
            )

    trace_hash = _sha256(trace_csv_path)
    exposure_hash = _sha256(exposure_csv_path)
    source_dir = Path(__file__).resolve().parent
    source_names = (
        "pcc_settlement_exposure.py",
        "e0d19_same_pcc_service.py",
        "model.py",
    )
    manifest = _json_ready(
        {
            "schema": E0D22_SCHEMA,
            "scientific_scope": (
                "selected_dispatch_price_spread_exposure_not_formal_tac_not_e1"
            ),
            "d19_source_lock": {
                "csv": locked_csv.name,
                "csv_sha256": E0D19_CSV_SHA256,
                "manifest": locked_manifest.name,
                "manifest_sha256": E0D19_MANIFEST_SHA256,
            },
            "inputs": {
                "formal_heat": {
                    "file": run.d19_run.heat_path.name,
                    "sha256": _sha256(run.d19_run.heat_path),
                },
                "renewable_shape": {
                    "file": run.d19_run.vre_path.name,
                    "sha256": _sha256(run.d19_run.vre_path),
                    "status": (
                        "legacy_2019_resource_year_mapped_to_2024_calendar"
                    ),
                },
            },
            "mathematical_contract": {
                "same_service_identity": "sum(delta_E_t)=0",
                "flat_price_identity": "pi_flat*sum(delta_E_t)=0",
                "selected_trace_envelope": (
                    "abs(sum(pi_t*delta_E_t))<=(pi_max-pi_min)"
                    "*0.5*sum(abs(delta_E_t))"
                ),
                "envelope_status": (
                    "exact_for_arbitrary_period_prices_within_bounds_for_the_"
                    "selected_trace"
                ),
            },
            "scientific_boundary": {
                "actual_price_path_assigned": False,
                "flat_price_settlement_complete": True,
                "time_varying_settlement_complete": False,
                "trace_solution_uniqueness_proven": False,
                "formal_tac": False,
                "e1_ready": False,
            },
            "dispatch_selection": {
                "solver": "appsi_highs",
                "primary": "minimum_known_annual_cost",
                "secondary": (
                    "fix_primary_incumbent_integers_then_minimize_curtailment"
                ),
                "interpretation": (
                    "one_reproducible_selected_dispatch;continuous_alternate_"
                    "optima_not_excluded"
                ),
            },
            "sources": {name: _sha256(source_dir / name) for name in source_names},
            "windows": [
                {
                    "window_id": item.window_id,
                    "hours": item.hours,
                    "annual_weight_per_hour": item.annual_weight_per_hour,
                }
                for item in run.exposures
            ],
            "output": {
                trace_csv_path.name: {
                    "rows": len(run.d19_run.pcc_traces),
                    "sha256": trace_hash,
                },
                exposure_csv_path.name: {
                    "rows": len(run.exposures),
                    "sha256": exposure_hash,
                },
            },
        }
    )
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
        )
        handle.write("\n")
    execution = {
        "schema": f"{E0D22_SCHEMA}.execution",
        "noncanonical": True,
        "records": [asdict(record) for record in run.d19_run.execution],
    }
    with execution_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                _json_ready(execution),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        handle.write("\n")
    canonical_hashes = {
        trace_csv_path.name: trace_hash,
        exposure_csv_path.name: exposure_hash,
        manifest_path.name: _sha256(manifest_path),
    }
    return E0D22Export(
        trace_csv_path=trace_csv_path,
        exposure_csv_path=exposure_csv_path,
        manifest_path=manifest_path,
        execution_path=execution_path,
        canonical_sha256=canonical_hashes,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the E0-D-22 PCC settlement-exposure diagnostic."
    )
    parser.add_argument("--heat-path", required=True, type=Path)
    parser.add_argument("--vre-path", required=True, type=Path)
    parser.add_argument("--d19-source-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    export = write_e0d22(
        run_e0d22(args.heat_path, args.vre_path),
        args.output_dir,
        d19_source_dir=args.d19_source_dir,
    )
    for path in (
        export.trace_csv_path,
        export.exposure_csv_path,
        export.manifest_path,
    ):
        print(f"{path.name} {export.canonical_sha256[path.name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
