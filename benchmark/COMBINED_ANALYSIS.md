# Combined sweep — threads x block_size x max_async, replicated (96 runs, 3 reps each)

Follow-up to the user's review of Phase 0/1: does the +5.2% scaled-thread
edge (seen once, at ma=1300, 1 rep) hold up under replication and at
higher load? Does block_size matter once pushed further (1600, 3200)?

## Thread config: default (4/4/4) vs scaled (16/8/16)

| block_size | max_async | default tps (±stdev) | scaled tps (±stdev) | Δ |
|---:|---:|---:|---:|---:|
| 200 | 2000 | 51,359 ±1,516 | 50,424 ±455 | -1.8% |
| 200 | 3000 | 52,378 ±1,204 | 52,971 ±1,014 | +1.1% |
| 200 | 5000 | 54,632 ±742 | 54,362 ±239 | -0.5% |
| 200 | 8000 | 55,659 ±2,161 | 55,406 ±746 | -0.5% |
| 800 | 2000 | 50,334 ±1,227 | 51,353 ±1,035 | +2.0% |
| 800 | 3000 | 52,355 ±476 | 52,721 ±1,305 | +0.7% |
| 800 | 5000 | 53,532 ±355 | 54,112 ±1,195 | +1.1% |
| 800 | 8000 | 56,377 ±1,357 | 55,126 ±846 | -2.2% |
| 1600 | 2000 | 50,202 ±1,489 | 50,616 ±1,724 | +0.8% |
| 1600 | 3000 | 52,356 ±1,854 | 52,298 ±1,023 | -0.1% |
| 1600 | 5000 | 54,095 ±930 | 55,218 ±511 | +2.1% |
| 1600 | 8000 | 54,456 ±776 | 54,643 ±1,116 | +0.3% |
| 3200 | 2000 | 50,500 ±1,185 | 50,408 ±1,610 | -0.2% |
| 3200 | 3000 | 51,641 ±668 | 53,648 ±987 | +3.9% |
| 3200 | 5000 | 52,789 ±1,277 | 54,046 ±739 | +2.4% |
| 3200 | 8000 | 54,883 ±894 | 55,539 ±1,220 | +1.2% |

**Verdict: no real effect.** Across all 16 combinations, deltas range
from -2.2% to +3.9% with **no consistent sign and no growth with
load** — exactly the opposite of what the "threads help under
contention" hypothesis predicts (which required the gap to grow
monotonically with max_async). The deltas are the same size as the
rep-to-rep standard deviation, which is the signature of noise, not a
real effect. **The original Phase 0 result (+5.2% at ma=1300, 1 rep)
was noise** — a good instinct to check, and the check settled it
cleanly rather than leaving it as a guess. This is also now consistent
with, not contradicted by, the CPU-sampling finding: if the true
bottleneck is a single thread outside the nworker/repnworker/clinworker
pools, scaling those pools has no reason to help at any load level,
and that's exactly what 96 replicated runs show.

## Block size: 200, 800, 1600, 3200

| max_async | bs=200 | bs=800 | bs=1600 | bs=3200 |
|---:|---:|---:|---:|---:|
| 2000 | 50,891 | 50,843 | 50,409 | 50,454 |
| 3000 | 52,674 | 52,538 | 52,327 | 52,644 |
| 5000 | 54,497 | 53,822 | 54,657 | 53,417 |
| 8000 | 55,532 | 55,751 | 54,549 | 55,211 |

**Verdict: no effect, now confirmed across a 16x wider range than
Phase 1** (100-800 there, up to 3200 here). Differences at any given
max_async are within ~2%, the same order as noise. block_size is
conclusively not a factor in this system's throughput ceiling — this
was worth checking (a 32x total range from 100 to 3200 is thorough)
but the earlier Phase 1 flatness was real, not a coincidence of the
range tested.

## max_async — the real trend, now with 24 samples per point

| max_async | mean tps | stdev | step Δ |
|---:|---:|---:|---:|
| 2000 | 50,649 | 1,195 | — |
| 3000 | 52,546 | 1,100 | +3.7% |
| 5000 | 54,098 | 975 | +3.0% (over a much bigger load step) |
| 8000 | 55,261 | 1,178 | +2.1% |

Still climbing, but each successive doubling-ish of load buys a
shrinking increment — a clean asymptotic curve consistent with a hard
service-rate ceiling being approached from below. This matches the
single-core-saturated replica finding: a fixed per-core service rate
produces exactly this shape (throughput → capacity asymptotically,
latency diverging) under queueing theory, independent of client load,
thread pool size, or batching.

## Where this leaves the baseline

Nothing in this 96-run replicated sweep changes the practical
recommendation from Phase 1: **max_async ≈ 400-600, block_size = 200**
(or any of the tested block sizes — genuinely doesn't matter),
**default threads** (now confirmed, not just directionally suggested)
remains the baseline operating point for future async-network
experiments. The asymptotic ceiling itself sits somewhere in the
56-58k tps range, gated by whatever single thread is saturated on the
replica side — profiling that thread (perf/flame graph on the leader)
is the natural next research question, separate from parameter tuning.
