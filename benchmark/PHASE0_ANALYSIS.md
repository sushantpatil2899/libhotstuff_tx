# Phase 0 — thread calibration result

1 rep per config, d6515 (32-core) x 4 replicas + 1 dedicated client host,
block_size=200, pace_maker=dummy, sb_users=1000.

| max_async | default (4/4/4) tps | scaled (16/8/16) tps | Δ | default lat (ms) | scaled lat (ms) |
|---:|---:|---:|---:|---:|---:|
| 100  | 39,981 | 39,116 | -2.2% | 2.496 | 2.551 |
| 400  | 46,606 | 45,874 | -1.6% | 8.587 | 8.723 |
| 900  | 47,015 | 46,749 | -0.6% | 19.179 | 19.275 |
| 1300 | 47,795 | 50,292 | **+5.2%** | 27.244 | 25.880 |

**Verdict: keep default threads (nworker=4, repnworker=4, clinworker=4)
for Phase 1.** Per the decision rule set before running this (≥10%
growth needed to justify scaling up), only the highest load point
(ma=1300) showed any real gap, and it's half the threshold (+5.2%).
Everywhere else scaled is flat-to-slightly-worse than default —
consistent with the old (different hardware, different workload)
study's own finding that more verification/network threads mostly add
contention rather than parallelism at n=4. Scaling threads is not
where this system's ceiling comes from.

Caveat: 1 rep per config, no replication — this is a directional
result for picking Phase 1's fixed thread config, not a claim with
error bars. If Phase 1's block_size x max_async grid surfaces a
surprising ceiling, revisit with reps before trusting it further.
