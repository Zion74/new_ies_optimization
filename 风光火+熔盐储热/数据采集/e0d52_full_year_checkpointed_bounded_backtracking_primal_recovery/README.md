# D52 full-year checkpointed bounded-backtracking primal recovery

This directory is the byte-for-byte local archive of the unique formal BESS run at:

`/root/e0-b-20260711-019f4f64/results/e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery`

Final classification:

- formal status: `no_primal_status_closure`;
- formal manifest SHA-256: `c80fc8bffa5cb49478e552ef44b2eea1726660f3421d306ed68146e8f9bc0f73`;
- total runtime: `1185.0414108345285 s`;
- stage 0 and stage 1: HiGHS `Optimal`, with immutable checkpoints;
- stage 2 attempt 0: no returned result before the frozen `390 s` parent hard wall;
- termination: `attempt_hard_wall`, `SIGTERM`, return code `-15`;
- complete candidate, exact lift and clean repair: not produced;
- audited feasible upper bound: not produced;
- restart or resume: not permitted;
- TES or Hybrid execution: not performed.

The termination was not an RSS or host-memory exhaustion event: peak child-tree RSS
was `3.444622 GiB`, peak parent-child aggregate RSS was `3.470619 GiB`, minimum
available host memory was `93.859192 GiB`, no RSS warning fired, and the final
residual-process count was zero. The host formal lock was released normally.

The stage-0 and stage-1 checkpoints are intermediate feasibility incumbents only.
Both explicitly set `formal_upper_bound_eligible=false`; they do not form a complete
8784 h trajectory, capacity result, project TAC, upper bound, gap, infeasibility
proof, or technology ranking. `SHA256SUMS` covers every formal file plus the external
launcher log and PID; all values were verified against the server after termination.
