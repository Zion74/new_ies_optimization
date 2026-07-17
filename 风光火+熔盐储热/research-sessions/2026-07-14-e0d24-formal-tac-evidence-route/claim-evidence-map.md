# E0-D-24 claim–evidence map

## Certified claims

| Claim | Evidence | Status |
|---|---|---|
| Complete formal TAC requires 16 non-optional accounts | E0-D-15 12-account TES gate + E0-D-20 4-account operating gate | Certified structural claim |
| Strict formal accounts currently ready | `e0d24_formal_tac_account_routes.csv` | `0/16` |
| TES accounts with incomplete direct candidates | D15 candidate blockers joined by D24 | `8/12` |
| TES accounts with no direct candidate | High-grade charge HX, medium-grade charge HX, heat-delivery HX, power-block retrofit | `4/12` |
| Formal operating accounts require Yangling primary records | D20 project-scope/numerical/boundary/driver gates | `4/4` |
| *Energy* venue quality does not certify account-level cost | DOI `10.1016/j.energy.2023.130132` + official IF snapshot + missing account fields | Certified non-laundering claim |
| Official engineering values cannot be relabeled as peer-reviewed formal values | NREL/DLR/DOE source-layer audit | Certified non-laundering claim |
| Layered-route approval alone is insufficient | Synthetic approval regression in `test_formal_tac_evidence_route.py` | Certified gate claim |

## Prohibited claims

- No public source substitutes for the four Yangling project-primary accounts.
- No aggregate anchor is allocated backward to TES component accounts.
- No journal impact factor repairs a missing price basis, denominator or topology boundary.
- D24 does not produce a formal TES portfolio, complete TAC, E1 readiness or a storage-technology winner.

## Machine evidence

- `风光火+熔盐储热/数据采集/e0d24_formal_tac_evidence_route/e0d24_formal_tac_account_routes.csv`
- `风光火+熔盐储热/数据采集/e0d24_formal_tac_evidence_route/e0d24_public_source_audit.csv`
- `风光火+熔盐储热/数据采集/e0d24_formal_tac_evidence_route/manifest.json`

Canonical conclusion:

```text
strict_formal_account_count = 0
project_primary_required_count = 4
layered_route_approved = false
formal_tac_ready = false
e1_ready = false
```
