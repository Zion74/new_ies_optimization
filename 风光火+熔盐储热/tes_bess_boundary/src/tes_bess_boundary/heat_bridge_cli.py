"""Command-line builder for formal E0-C heat-adapter and bridge evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tes_bess_boundary.heat_adapter import (
    HeatDemandAdapterSpec,
    HeatDemandInterpretation,
    adapt_e0b_heat_demand,
    write_adapted_heat_demand,
)
from tes_bess_boundary.heat_bridge import (
    run_e0c_heat_bridge_diagnostics,
    write_e0c_heat_bridge_diagnostics,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build three full-year E0-C heat interpretations and the six locked "
            "real-CHP bridge diagnostics."
        )
    )
    parser.add_argument("--hourly-csv", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    full_year_hashes: dict[str, str] = {}
    for interpretation in HeatDemandInterpretation:
        adapted = adapt_e0b_heat_demand(
            args.hourly_csv,
            spec=HeatDemandAdapterSpec(interpretation=interpretation),
            source_manifest=args.source_manifest,
        )
        exported = write_adapted_heat_demand(adapted, args.output_dir)
        full_year_hashes.update(exported.output_sha256)

    run = run_e0c_heat_bridge_diagnostics(
        args.hourly_csv,
        source_manifest=args.source_manifest,
        adapter_output_dir=args.output_dir / "windows",
    )
    bridge = write_e0c_heat_bridge_diagnostics(run, args.output_dir)
    summary = {
        "full_year_output_sha256": dict(sorted(full_year_hashes.items())),
        "bridge_canonical_output_sha256": dict(
            sorted(bridge.canonical_output_sha256.items())
        ),
        "bridge_execution_metadata": bridge.execution_metadata_path.name,
        "bridge_execution_metadata_sha256": bridge.execution_metadata_sha256,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
