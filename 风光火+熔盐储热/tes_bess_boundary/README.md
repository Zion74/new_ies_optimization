# TES–BESS Boundary Model

This package is the isolated Pyomo + HiGHS implementation for the current Yangling
TES/BESS/Hybrid boundary study. It deliberately does not import the repository's
legacy oemof/Gurobi environment.

The current E0 slice contains:

- structural audits for the 2024 hourly operations and planning CSV files;
- an auditable E0-B builder for the two raw heat workbooks, including a 52,707-row source ledger, three hourly heat interpretations, quality flags, and a reproducibility manifest;
- a strict E0-B-to-E0-C heat-demand adapter that validates the complete 8,784-hour source and manifest v2 before selecting `net_clipped`, `forward`, or `zero_sensitivity_clipped`, with separate full-source and window modification audits;
- a table-vertex CHP feasible-region contract with explicit gross/net and heat-basis checks, three explicit 98--105 MW fuel rules, adjacent-segment fuel PWL, and evidence-bounded unit commitment;
- closed-form BESS energy-balance validation on the PCC AC basis;
- three-temperature molten-salt inventory and enthalpy validation;
- a unique salt/tank/five-port cost-capacity ledger with component temperature-range checks;
- a pre-model cost-evidence gate that separately checks venue tier, price basis, capacity denominator, technology boundary, provenance, and allowed use before any source can certify a formal baseline;
- a 12-account formal-TES readiness gate that rejects aggregate anchors from component accounts and requires explicit approval before combining multiple source packages;
- a penalty-free TES break-even accounting seam that reports one whole-system EAC ceiling plus fuel, curtailment, PCC-export, and auxiliary-energy deltas without allocating the ceiling back to components;
- a conservative E0-C annual-result adapter with explicit curtailment service, weighted renewable/PCC audits, complete TES-ownership removal, and a primary-cost-incumbent-conditional curtailment tie-break;
- a hash-locked E0-D-17 historical exploration CLI plus an E0-D-18 performance runner that closes the 24-hour exact point and the 336-hour bounded-gap gate with explicit primal/dual propagation;
- an E0-D-19 same-PCC-service runner, E0-D-20 operating-cost evidence gate, and E0-D-21 source-independent shadow-cost robustness layer;
- an E0-D-22 hourly-PCC settlement-exposure exporter plus an E0-D-23 joint alternative-dispatch envelope that reopens both architectures' integer patterns under the D19 cost and curtailment caps;
- an E0-D-26 strict numerical certificate that normalizes annual admissibility rows, separates the D19-selected integer face from the reopened global set, seeds global solves with known feasible witnesses, and distinguishes a termination label from a finite bound certificate;
- an E0-D-27 direction-generation and sign-reformulation certificate that removes sign binaries from fixed support directions, recomputes feasible L1 exposure from returned PCC traces, and replaces the global `2M` absolute-value rows with an exact positive/negative disaggregation;
- an E0-D-28 preregistered multistart direction screen that tests negated and alternating sign seeds without promoting fixed-direction duals to global L1 bounds;
- a hash-locked NREL 2022 ATB 4-hour utility-BESS sensitivity ledger with separate power/usable-energy denominators, aggregate/FOM reconciliation, and a hard guard against counting source FOM together with a second augmentation-replacement ledger;
- a five-path topology-evidence audit that distinguishes Energy+ direct evidence, reduced-order mapping, modular synthesis, and explicitly proposed extensions;
- a provenance-aware MT-to-LT heat-delivery audit covering endpoint pinches, HITEC liquid/material limits, inventory/port heat caps, and salt/water flow units;
- a provenance-locked MT scenario set that maps 25/50/75% low-grade sensible-enthalpy shares to 232.5/285/337.5 °C author sensitivities without presenting them as site or paper values;
- inventory- and temperature-dependent TES loss, fixed heat tracing, five-path pumping, three-MT loss calibration, and low/base/high bottom-up hydraulic pump audits;
- a fixed-capacity unified No-storage/BESS/TES/Hybrid dispatch model with one PCC and useful-heat boundary;
- an auditable lifetime-economics kernel with project NPV/EAC, component-specific replacement and residual ledgers, BESS calendar/AC-discharge two-anchor calibration, and structural cell double-count protection;
- an optional fixed-capacity annual-economics seam with strictly scored 8,784-hour weights, canonical non-cell EAC, BESS calendar and PCC AC-discharge costs, an annual EFC limit, closed state boundaries, and a public annual audit;
- two orthogonal 24-hour real-Yangling no-storage bridge diagnostics (six HiGHS solves) with deterministic scientific outputs and a separate runtime sidecar;
- deterministic tests for both the legacy `SolverFactory("appsi_highs")` interface and direct Appsi `Highs`.

This is not yet the full planning/economic model. The lifetime cash-flow mechanics,
fixed-capacity annual Pyomo seam, explicit 2024-CNY price conversion audit, and TES
generation-cost classification are complete, but no unverified default equipment
prices are embedded. The current HITEC 53/40/7 and 180/390 °C values are a physical
candidate only. A 120/70 °C Energy 2026 heat-network case is registered only as a
core reference scenario: it proves feasible heat grade under explicit approach
assumptions but does not identify Yangling site temperatures or a unique medium
temperature. E0-D-8 pre-registers MT through the normalized low-grade enthalpy
share `(MT-LT)/(HT-LT) = 0.25/0.50/0.75`; the resulting three values are
author sensitivities rather than a formal site baseline. E0-D-10 records the initial
cost-source audit. E0-D-11 adds one reproducible NREL engineering anchor for
sensitivity analysis only. Its 2020-USD power and usable-energy terms, 4-hour
aggregate, and FOM are reconciled, but it is structurally ineligible for the formal
Energy+ baseline; the workbook/webpage round-trip-efficiency discrepancy is excluded
from the cost anchor rather than silently resolved. E0-D-13 registers the Rahman
*Applied Energy* paper plus the same-author official University of Alberta dissertation
chapter as the only BESS formal-source candidate and maps the principal non-cell cost
lines. E0-D-14 closes the fixed-capacity model joins: Rahman supplies cell price only,
Schmidt supplies the 13-year/3250-EFC non-price life inputs, VOM is charged on AC
discharge, and the constant PCS unit cost is rejected outside 5-100 MW. The resulting
BESS lifecycle ledger is complete. E0-D-15 separates 12 mandatory TES cost accounts
from aggregate calibration anchors and requires explicit approval for a multi-source
evidence portfolio. All 12 accounts remain blocked under the strict route. The DLR
2020-EUR two-tank Solar Salt value is retained for calibration/sensitivity only and
cannot certify the component ledger or the proposed three-temperature HITEC topology.
E0-D-16 therefore leaves every TES ownership price unset and computes only the
maximum whole-system TES EAC consistent with a matched annual service outcome. It
rejects artificial curtailment penalties, heat shortfall, non-optimal outcomes,
zero-capacity TES, and cross-scope comparisons; normalized views cannot be allocated
back to components. The current claim remains exploratory because the formal TES
portfolio and complete non-TES system-cost scope are both unfinished. E0-D-17 connects
actual annual E0-C results to that kernel and locks one 24-hour winter screening slice.
The slice uses formal heat but a legacy 2019 renewable shape mapped onto 2024, scores
one day with a weight of 366, and includes fuel cost only. Its whole-system EAC ceiling
must not be described as a full-year result, a TES component price, or an E1 winner.
E0-D-18 reduces the 336-hour model from 7,728 to 3,024 unfixed binaries using an exact
logarithmic fuel-segment formulation, an explicitly selected continuous transition
envelope, and path-specific TES flow bounds. The 24-hour primary/secondary solves are
exact; the 336-hour primary gap is 0.004800 and the fixed-integer secondary gap is zero.
Its whole-system EAC is therefore reported as the bounded interval
57.572--59.818 million CNY/a, not as a point estimate.
E0-D-19 then enforces the same annual PCC export and reduces the fuel-only space to
12.893 million CNY/a for 24 hours and 15.031--16.330 million CNY/a for 336 hours.
E0-D-20 keeps settlement, carbon compliance, CHP VOM, and TES VOM blocked rather than
inventing project values; E0-D-21 propagates those missing accounts as risk budgets.
E0-D-22 exports the selected hourly PCC traces, and E0-D-23 defines their joint
annualized L1 envelope. E0-D-26 adds dimensionless cap rows, `1e-9` feasibility
tolerances, PCC trace recomputation, and known-witness dominance checks. E0-D-27
supersedes the D26 maximum-end precision with fixed support directions and an exact
positive/negative sign formulation. The strict 24-hour global envelope is
26,010.171143--26,010.174929 MWh/a. The 336-hour minimum remains bounded by
0--15,594.993900 MWh/a and the maximum is tightened to
36,382.462799--1,081,649.139331 MWh/a; its global envelope remains open. A support
direction dual bounds only that direction and is never reported as the global L1
upper bound. These are
settlement-exposure bounds, not actual price losses or a technology winner. Formal sweeps must not start until
the real BESS/TES component portfolio, site-calibrated
TES loss and auxiliary parameters, VOM/carbon/settlement terms,
structured representative periods, and endogenous capacity are completed.

E0-D-28 tested one 1,800-second fixed-support iteration from each of two diverse
336-hour seeds. Neither returned an L1 witness above 36,382.462799 MWh/a, so the
D27 interval is unchanged. Both solves ended at the time limit without a sign fixed
point; this bounded negative screen does not exclude other orthants or prove global
optimality.

`AnnualHorizonSpec` currently describes scored periods only. Every weight must be
strictly positive and `sum(weight[t] * dt) = 8784 h`. The later representative-week
module must give warm-up periods an explicit structural role and state boundary;
zero weights are not accepted as an implicit warm-up shortcut.

Build the formal E0-B artifacts without overwriting legacy CSV files:

```python
from tes_bess_boundary.heat_dataset import (
    HeatBuildSpec,
    HeatSourceBundle,
    build_heat_dataset,
    write_heat_dataset,
)

dataset = build_heat_dataset(
    HeatSourceBundle(first_half_workbook, second_half_workbook),
    spec=HeatBuildSpec(),
)
write_heat_dataset(dataset, output_directory)
```

The resulting hourly columns are deliberately unambiguous: `heat_net_mw` remains
signed, `heat_forward_mw` clips each branch before aggregation, and
`heat_zero_sensitivity_mw` changes only the registered 226-point zero segment.

Build the three formal E0-C demand products and the six locked bridge diagnostics:

```bash
python -m tes_bess_boundary.heat_bridge_cli \
  --hourly-csv /path/to/e0b_formal_2024/e0b_heat_hourly_2024.csv \
  --source-manifest /path/to/e0b_formal_2024/manifest.json \
  --output-dir /path/to/e0c_heat_demand_adapter
```

The primary model input is `net_clipped = max(heat_net_mw, 0)`. `forward` and
`zero_sensitivity_clipped` are explicitly labelled sensitivities rather than plant
facts. Window selection is half-open and the complete source is always validated
before slicing.

Server verification:

```bash
python -m pip install -e ".[test]"
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m pytest -q -p no:cacheprovider
```

Data-integration tests read Yangling files outside this package and are run only
where those files already exist. Set `TES_BESS_E0B_FORMAL_DIR` when the formal
directory is not in the local repository layout. The current full OpenBayes
regression and D27/D28 hashes are recorded in
`docs/03_sci_paper/e0_validation_status.md`. E0-D-26--D28 source/tests and the
authorized D19/D22 inputs are synchronized; their strict probes and deterministic
bundles are generated on the server. The D23/D26 historical outputs remain
hash-locked but no longer define the preferred maximum-end numerical precision.
With `TES_BESS_E0B_FORMAL_DIR=/root/e0-b-20260711-019f4f64/formal_data/e0b_formal_2024`
set explicitly, all remote data-integration tests pass; omitting it addresses a
nonexistent repository-relative directory and is an environment-path error.

```bash
python -m pytest -q -m data_integration
```

The supported runtime is Python 3.10–3.11 with the exact Pyomo and HiGHS versions
declared in pyproject.toml.
