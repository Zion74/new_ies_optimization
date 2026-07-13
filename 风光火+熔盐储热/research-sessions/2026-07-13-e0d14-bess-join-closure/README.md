# E0-D-14 BESS model-join closure

Date: 2026-07-13

Purpose: close the three model joins that remained after the Rahman linked-source certificate without weakening the Energy-or-above evidence gate or inventing a PCS learning formula.

## Decisions

1. Cell price and degradation ownership are separated. Rahman supplies `216.27 USD_2019/kWh_internal`; Schmidt et al. (*Joule*, DOI `10.1016/j.joule.2018.12.008`) supply the direct non-price values `13 years` and `3250 full-equivalent cycles`. The existing calendar-plus-AC-throughput kernel is the sole replacement ledger. Rahman's 12.03-year cycle-only replacement is not added to the formal baseline.
2. Rahman Table 3.5 variable O&M is mapped to AC discharge. Its underlying reference is Zakeri and Syri, *Renewable and Sustainable Energy Reviews* 42 (2015) 569-596, DOI `10.1016/j.rser.2014.10.011`; Rahman's LCOS method defines `Eout` as electricity discharged per cycle. The rate converts from `2.74 USD_2019/MWh` to `23.9428497032 CNY_2024/MWh_ac_discharge` through the existing audited bridge.
3. PCS uses a constant `206.81 USD_2019/kW` only inside the Rahman study domain, 5-100 MW. EPRI-DOE Handbook 1001834 identifies a 5 MW module/scale convention and a multiplicity concept but does not provide one uniquely reproducible 95% parallel-module formula. The implementation therefore rejects capacities outside 5-100 MW and does not claim an exact PWL curve. A PWL multiplicity treatment remains an E6 sensitivity only after a unique formula is obtained.

## Implementation outcome

- `economics.py`: added an auditable AC-discharge variable O&M value object and price conversion; `AnnualEconomicsSpec` now carries the converted rate.
- `formal_bess_costs.py`: added the resolved join contract and a complete fixed-capacity BESS annual-economics builder.
- `model.py`: degradation cycle cost and variable O&M are reported separately and added once each to annual total cost.
- PCS source-domain validation rejects `<5 MW` and `>100 MW`.

## Verification

- Focused economics/HiGHS tests: `41 passed`.
- Full local suite: `268 passed in 32.53s`.
- One pre-existing `.pytest_cache` write-permission warning remains non-functional.
- `ruff` was not available in the local E0 virtual environment; the full Python/HiGHS regression passed.

## Boundary after E0-D-14

The fixed-capacity BESS lifecycle sub-ledger is model-ready. E0 is not complete: TES formal costs, system-level settlement/carbon terms, endogenous capacity, representative periods, and E1-E6 entry remain blocked.
