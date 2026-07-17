# E0-D-49 formal BESS method-gate evidence

Updated: 2026-07-16

Remote canonical directory:

`/root/e0-b-20260711-019f4f64/results/e0d49_physics_first_fuel_projection_primal_recovery/`

## Audited terminal state

- Formal status: `no_primal_status_closure`
- Architecture order: BESS only
- Candidate status: `null`
- Repair status: `null`
- Audited feasible upper bound: `null`
- Successful architecture count: `0`
- TES/Hybrid executed: `false`
- Formal project TAC ready: `false`
- Technical ranking permitted: `false`

The candidate parent hard wall triggered after `3720.637203153223 s`. The
child received `SIGTERM` and returned `-15`. No `bess_candidate.csv.gz` or
`bess_candidate.json` was created, so exact fuel-code lift and the clean
original-cost repair were not entered.

The execution was not stopped by memory pressure: peak child process-tree RSS
was `3.137737274169922 GiB`, peak parent--child aggregate RSS was
`3.1623153686523438 GiB`, and minimum available host memory was
`94.17270278930664 GiB`. Active residual process count was zero. The execution
sidecar records `resource_gate_passed=false` because the parent hard wall is a
controlled stop reason, not because the 35/45 GiB RSS or 30 GiB available-memory
thresholds were crossed.

## Evidence hashes

- Formal manifest: `0d66f06defcc8ecabe247bc7eb38c3f9e7f457d41dac82927295f54b0ad62a14`
- BESS manifest: `7f86f9c4a2cb0e0fd258edf027627d3bba40b47aaa6088754dcddd539d26aeec`
- Candidate execution: `4979c845b1df5fc5b71ec6cc5fdd5d9f82f02015e57eb681c26d92eded9c398f`
- Candidate heartbeat: `c226513f73c04abedfc30c1638c9ad669436968883e52cf067fa04fa7b72b9b8`
- Empty solver log: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Canonical checksum file: `77020fd8049d29810ea95cea3db996c6cf84c1be6594219ca74e42651e64914a`
- Empty launcher log: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Launcher PID record: `35bd267ba05692754950f5211f3472371ceb59c97e0a0ec77b333201ba7b490a`

The five canonical remote artifacts listed in `SHA256SUMS.txt` and all four
artifacts declared by `formal_manifest.json` were checked after download with
zero mismatches. The supplemental launcher log/PID were also downloaded and
hashed. No active D49 or HiGHS process remained on the server.

## Claim boundary

This result does not prove BESS physical or rational infeasibility. It does not
provide a candidate, feasible capacity, original-MILP upper bound, gap, project
TAC, or technology ranking. Under the frozen D49 contract it closes D49 without
rerun and only permits a separately preregistered D50 method design.
