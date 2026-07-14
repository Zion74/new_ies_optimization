# E0-D-24 source log

Date: 2026-07-14

## Screening rule

- Core peer-reviewed evidence must be *Energy* level or above.
- *Energies* and comparable low-tier sources are excluded from the core evidence chain.
- Official reports are retained as engineering/method anchors, never promoted to peer-reviewed formal values through secondary citation.
- Project-specific settlement, allowance compliance, CHP VOM and TES VOM require Yangling primary records for formal TAC.

## Access log

| Source | Access route | Venue/authority check | Extracted support | D24 disposition |
|---|---|---|---|---|
| Zhang et al., DOI `10.1016/j.energy.2023.130132` | InstSci search; ScienceDirect publisher page | *Energy*; official Elsevier page reported IF `9.4` on 2026-07-14 | Coal-fired molten-salt retrofit; publisher abstract reports aggregate equipment/material cost and LCOD | `aggregate_technology_anchor`; no component certificate |
| Turchi & Heath, DOI `10.2172/1067902` | OSTI/NREL official record | NREL technical report | Component-based 100 MWe two-tank nitrate-salt CSP cost model; storage and steam-generation system boundaries | `component_engineering_anchor` only |
| Glatzmaier, DOI `10.2172/1031953` | OSTI official record | NREL technical report | TES cost-model methodology for advanced-cycle temperatures | `methodology_only` |
| Stoddard et al., DOI `10.2172/1335150` | OSTI official record | DOE / Black & Veatch technical report dated 2016-06-30 | Approx. 10 MWe high-temperature molten-salt/sCO2 concept and capital cost estimate | `component_engineering_anchor` only; report date is not silently treated as price base |
| DLR 2021 two-tank Solar Salt report | DLR official repository | Official engineering | `20–22 EUR_2020/kWh_th-net`, central 21, two-tank aggregate | `aggregate_technology_anchor` only |

## InstSci execution note

`instsci v0.1.1` was used for search. An exact publisher-PDF fetch for DOI `10.1016/j.energy.2023.130132` did not complete in the local access path and its child process tree was terminated after inspection. No file was produced. This is recorded as an access failure, not evidence that the paper lacks a component table. The D24 decision uses only publisher metadata that was actually accessible.

## Official links

- Energy article: https://www.sciencedirect.com/science/article/abs/pii/S0360544223035260
- Energy journal metric page: https://www.sciencedirect.com/journal/energy/about/insights
- NREL 2013 / OSTI: https://www.osti.gov/biblio/1067902
- NREL 2011 / OSTI: https://www.osti.gov/biblio/1031953
- DOE / Black & Veatch 2016 / OSTI: https://www.osti.gov/biblio/1335150
- DLR: https://elib.dlr.de/141315/

## Non-support decisions

- The *Energy* 2024 source does not provide a certified price year or account-level decomposition in the accessible publisher record.
- NREL/DOE/DLR reports do not pass the Energy+ venue gate and do not directly match the current three-temperature, five-path, dual-service CHP-TES topology.
- None of the public sources substitutes for Yangling settlement, allowance or O&M primary records.
