# E0-D-49 OpenBayes Gate A evidence

- Status: `gate_a_passed`
- Formal run permitted: `true`
- Formal architecture: BESS only
- TES/Hybrid formal execution permitted: `false`
- Formal optimization invoked during Gate A: `false`
- Locked Git commit: `865cc97b0428f12bb3592c931db27bfd5ed0e223`
- Gate A manifest SHA-256: `11b283d6825cd5fcc5b41a09b8400bdb6116bb11e830b1dd1bc42b9417e789dd`
- Gate A execution SHA-256: `2fd4a89660ff6b8443832eb29891e8dec689601bf54ca6bd041387502c60792b`
- Runtime: OpenBayes, Python 3.10.18, Pyomo 6.10.1, HiGHS 1.15.1

The sibling directory `../e0d49_gate_a_work_86a8b80/` contains the three
8784 h build-only audits, three JUnit files, Ruff and `py_compile` logs, and
the preserved input-rejection log. The build audits did not invoke a solver.

| Architecture | Original variables | Original binaries | Projected physical binaries | Constraints | Build audit |
|---|---:|---:|---:|---:|---|
| BESS | 597,318 | 79,057 | 26,353 | 527,053 | passed |
| TES | 650,052 | 87,840 | 35,136 | 606,163 | passed |
| Hybrid | 685,194 | 96,625 | 43,921 | 667,662 | passed |

All three architectures project exactly 52,704 registered CHP fuel-code
binaries, retain every original variable and constraint, prove the registered
fuel-code dependency boundary, and pass the all-segment/all-knot deterministic
lift audit.

Test evidence:

- D49 targeted suite: 14 passed, 0 failed, 0 skipped.
- D40-D49 compatibility suite: 219 passed, 0 failed, 0 skipped.
- Full package: 673 passed, 0 failed, 0 skipped.
- Ruff and `py_compile`: passed with recorded sentinels.

The first build CLI attempt supplied `bess_guide.json`, the D46 run summary,
instead of the locked complete-variable snapshot `bess_guide.csv.gz`. The
pre-registered guide SHA-256 gate rejected it before any solver call; the log
is preserved as `gate_a_build_bess_wrong_json_rejected.log`. No code, model,
option, tolerance, seed, or wall clock was changed. The accepted run used the
three original D46 `*_guide.csv.gz` artifacts and their locked hashes.

Remote checksum files cover 19 work artifacts and 2 Gate A artifacts. Their
local copies were checked on 2026-07-16 with zero mismatches. This Gate A is
not a candidate solution, feasible capacity, upper bound, gap, project TAC,
infeasibility proof, or technology ranking. It only authorizes the single
pre-registered BESS candidate--lift--repair method gate.
