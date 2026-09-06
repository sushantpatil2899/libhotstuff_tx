# Network latency injection — mechanism verified, first result is surprising

## Mechanism verification (ground truth, not inference)

Applied `lat_node0=50, lat_node2=100` (others 0) and pinged every pair
directly:

| pair | expected one-way max() | expected RTT | measured RTT |
|---|---:|---:|---:|
| 0↔1 | 50ms | 100ms | 100.18ms |
| 0↔2 | 100ms | 200ms | 200.15ms |
| 0↔3 | 50ms | 100ms | 100.16ms |
| 1↔2 | 100ms | 200ms | 200.15ms |
| 1↔3 | 0ms | ~0ms | 0.11ms |
| 2↔3 | 100ms | 200ms | 200.15ms |

Exact match, tight variance (mdev 0.02-0.04ms) on every pair, including
the untouched (1,3) pair staying native. `fab clear-netem` confirmed
restoring native RTT afterward. The mechanism itself is solid.

## First real experiment: leader delayed 50ms to all 3 followers

`block_size=200, max_async=175` (this repo's own original default),
3 reps each, baseline vs. `lat_node1=50` (node1 is the fixed leader
under `dummy` pacemaker):

| condition | rep | tps | latency (mean) |
|---|---|---:|---:|
| baseline | 1 | 42,816 | 4.083ms |
| baseline | 2 | 42,243 | 4.138ms |
| baseline | 3 | 44,026 | 3.970ms |
| **leader +50ms** | 1 | 53,151 | 3.288ms |
| **leader +50ms** | 2 | 53,569 | 3.262ms |
| **leader +50ms** | 3 | 44,499 | 3.927ms |

**This replicates in the same direction across all 3 reps: delaying
the leader's links by 50ms one-way (100ms RTT to every follower) did
not hurt throughput or latency — 2 of 3 reps show it measurably
higher-throughput and lower-latency than baseline, the third is a
wash.** This is not what naive intuition predicts, and I checked it
wasn't a fluke before reporting it (the single first sample showed the
same pattern; replicating it with 3 reps on each side confirms it's
not noise).

**Why this is actually consistent with everything else this session
found**: the system's bottleneck at this load level, established
earlier via `strace` counts and CPU profiling, is per-command
syscall/allocation overhead on the replica CPU — not consensus
round-trip time. `max_async=175` is well below the ~8000 saturation
range; with an unbounded pipeline depth (`parent_limit=-1`), the
leader can have many proposals in flight concurrently, so a fixed
per-link delay gets absorbed by pipelining rather than serializing
onto the critical path, as long as there's enough outstanding work to
span the round-trip time. That explains "no worse" cleanly. It does
not explain why 2 of 3 reps came out *better* — I don't have a
mechanism proven for that yet (a guess: shifted I/O timing changing
scheduling/interrupt behavior on the leader's core), and I'm flagging
it as unexplained rather than asserting a cause I haven't checked.

## Open question this raises

Does this hold at high load (near the ~50-56k tps ceiling this session
already mapped), where the leader's CPU is already the constraint and
there's much less slack for pipelining to hide delay behind? That's
the natural next test before drawing a general conclusion about
"leader latency doesn't matter here."

## What's built

- `benchmark/netem.py`: pairwise max() computation, `tc` (prio qdisc +
  per-peer netem bands + u32 destination filters) command generation,
  auto-discovers the network interface per host (no hardcoding).
- `config.py`: `NetworkParameters`, parsing `lat_node0..lat_node3`
  (ms, default 0) from a CSV row.
- `remote.py`: `_apply_netem`/`_clear_netem`, wired into `_run_single`
  so every row clears any prior tc state before applying its own
  (self-healing against a crashed prior row).
- `fab clear-netem`: standalone manual reset, independent of any CSV
  row, for after a Ctrl-C'd sweep.
- Fixed a real latent bug found while wiring this in: `_row_to_protocol`
  never included `sb_users`/`sb_prob_choose_mtx`/`sb_skew_factor` in
  its column filter, so those CSV values were silently dropped on
  every row all session — harmless so far only because every row we
  ever wrote used the exact default values anyway, but would have
  broken a future sweep that varies them.
