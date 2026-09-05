# Phase 1 — saturation grid, extended load, and bottleneck localization

1 rep per config throughout. N=4 replicas (d6515), 1 dedicated client
host, default threads per Phase 0 (nworker=4, repnworker=4,
clinworker=4), pace_maker=dummy, sb_users=1000, sb_prob_choose_mtx=0.9,
sb_skew_factor=0.1.

## Main grid (`main_grid.csv`, 40 runs): block_size × max_async

Peak tps by block_size across max_async ∈ {10..1300}: bs=100 → 50,645
(at ma=600); bs=200 → 49,656; bs=400 → 49,019; bs=800 → 49,447 (all at
ma=1300). **The four curves are effectively identical** — block_size
in this range does not move the ceiling. This settles the "false
saturation from a fixed wrong block_size" concern raised earlier: it
wasn't the confound.

Latency grows roughly monotonically with max_async across every
block_size (0.5ms at ma=10 → ~26ms at ma=1300) with no sharp single
elbow — a continuous, decelerating throughput curve rather than a
clean knee.

## Extended sweep (`extended_load.csv`, ma ∈ {2000, 3000, 5000, 8000}, bs=200)

| max_async | tps | latency (ms) |
|---:|---:|---:|
| 1300 | 49,656 | 26.2 |
| 2000 | 50,576 | 39.7 |
| 3000 | 52,232 | 57.8 |
| 5000 | 54,192 | 93.1 |
| 8000 | 55,925 | 145.6 |

Throughput is *still* climbing at ma=8000, but the shape is now
obviously diminishing returns: a 6× increase in offered load (1300→8000)
buys +12.6% tps at the cost of +455% latency. There is no hard ceiling
in this range — just a curve asymptoting toward something a bit above
~56k tps while latency blows up. Practically, nothing past roughly
ma≈400-600 is worth paying for.

## Bottleneck localization (this is the actual finding)

Two CPU checks, both via per-process `%CPU` (not system-wide aggregate
— the d6515 has 64 logical cores, so a single saturated thread is
invisible in `top`'s aggregate view and only shows up correctly via
`ps -eo %cpu` on the specific process):

- **Client (node4), during the ma=2000-8000 sweep**: `hotstuff-client`
  used **~160-164% of one core** — under 2 of 64 available cores. Not
  remotely CPU-bound. Ruled out as the bottleneck.
- **Replicas (leader vs. follower), during a dedicated 90s ma=5000
  probe**: both `hotstuff-app` processes climbed steadily to **just
  over 100% of a single core** — leader (amd026, the fixed proposer
  under `dummy` pacemaker) plateaued around **119%**, follower (amd004)
  around **102%**. Both single-core-saturated, on a 32-core/64-thread
  machine with 30+ idle cores each.

**Conclusion: the ceiling is replica-side, and it's a single-threaded
bottleneck** — almost certainly the core consensus/event-loop path
(salticidae's dispatch loop, or the sequential state-machine advance),
not the thread pools this session spent Phase 0 calibrating.
`nworker`/`repnworker`/`clinworker` control *pool* sizes for
verification and network I/O, which have plenty of headroom (30+ idle
cores); none of that helps if the actual constraint is one thread that
can't be parallelized by adding more workers elsewhere. This also
retroactively explains Phase 0 (scaling threads barely moved tps) and
the main grid (block_size didn't matter) — both were tuning knobs
around a bottleneck that isn't in either of those subsystems.

Root-causing *which* single-threaded path it is (perf/flame-graph
profiling on the leader) is a natural next step but out of scope for
today's baseline pass.

## Practical baseline operating point

For the "baseline" this whole session set out to find: **max_async ≈
400-600, block_size = 200** (the repo's own original default,
statistically indistinguishable from the others here) gives ~46-50k
tps at 9-14ms latency — within single-digit percent of the asymptotic
ceiling for a small fraction of the latency cost of pushing further.
This is the number to build the async-network-perturbation experiments
against.

## Caveat

Every number above is 1 rep. Directionally solid (the bottleneck
finding was cross-checked twice — once via the extended load curve
shape, once via direct CPU sampling on both a leader and a follower)
but not yet statistically replicated. Before this goes in anything
that gets reported externally, re-run the proposed baseline point (and
a couple of neighboring max_async values) with 3 reps.
