# E0-D-48 OpenBayes Gate A evidence

- Status: `gate_a_passed`
- Formal run permitted: `true`
- Formal optimization invoked during Gate A: `false`
- Locked Git commit: `1090cd83b54aac8a99dce0041c1371b1e0b4320d`
- Gate A manifest SHA-256: `1d894652bfb91f9995f428c8f36fc7ad555675496e42c1dbec4c6673c14c8bfe`
- Runtime: OpenBayes, Python 3.10.18, Pyomo 6.10.1, HiGHS 1.15.1

The sibling directory `../e0d48_gate_a_work_1090cd8/` contains the three
build-only audits, JUnit files, Ruff log, and `py_compile` log compiled into
the manifest. The build audits did not call `solve()` and verified that the
equal-weight Hamming objective leaves every active original constraint
unchanged.

| Architecture | Variables | Original binaries | Constraints | Build audit |
|---|---:|---:|---:|---|
| BESS | 597,318 | 79,057 | 527,053 | passed |
| TES | 650,052 | 87,840 | 606,163 | passed |
| Hybrid | 685,194 | 96,625 | 667,662 | passed |

Test evidence:

- D48 targeted suite: 15 passed, 0 failed, 0 skipped.
- Full package: 659 passed, 0 failed, 0 skipped.
- Ruff and `py_compile`: passed with recorded sentinels.

Locked D46 guide SHA-256 values:

- BESS: `b69f4035deb5aa5f83a504e1e40347a23fa352b4104087bc017da6940c828b1f`
- TES: `d38004e6c3607cc2095c93def187de6d5300f5b9d9e97928872aaf6ce176e8e9`
- Hybrid: `9def0298195dbbebe477d9ff3b91f3b475082325eeea01dfc80c49930d532655`

This Gate A grants permission only for the one preregistered formal D48 batch.
It is not an upper bound, feasible capacity result, project TAC, infeasibility
proof, gap certificate, or technology ranking.
