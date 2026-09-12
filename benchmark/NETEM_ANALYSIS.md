> # ⚠️ RETRACTED — 2026-09-07
>
> **Superseded 2026-09-12 by `BASELINE_ANALYSIS.md` section 12**
> (Stage N: 340 runs, multi-client, on the corrected measurement
> path, with the injected delay verified in every run from
> `rtt.json`). Read that instead of this document.
>
> **The conclusion drawn below does not hold. The delay did reach the
> application's own sockets, yet the commit path shows no trace of
> it. That contradiction is unresolved.**
>
> The ping table below is accurate, and the mechanism is in fact
> better verified than this document claimed. Ping alone would only
> prove the rules affect ICMP — but the replicas' own connection logs
> time the inter-replica TCP handshake at **400.2ms** on every delayed
> link (exactly 2 x 200ms RTT) against **11.0ms** on an undelayed run.
> So `tc` demonstrably shapes real consensus sockets, not just ICMP.
>
> What does not follow is the commit latency. See the retraction header
> in `NETEM_FACTORIAL_ANALYSIS.md`: delayed links carry 400ms RTT at
> connection time, while commits complete in ~7ms. Both measurements
> are solid and they cannot both describe the same steady state.
>
> ## The number that should have caught this immediately
>
> This document reports leader+50ms with **p50 latency of 3.11ms**.
> Client latency is true end-to-end (timer starts at send, stops on
> the f+1-th ack; a replica only acks from inside the commit path —
> `do_decide`, `src/consensus.cpp:148`). A commit crosses ~6 delayed
> hops, so 50ms one-way implies a floor near 300ms. 3.11ms is
> physically impossible under a working 50ms injection.
>
> Confirmed later across ~1.7M commands: under 200ms on all three
> follower links, the *slowest* of 431,947 commands was 36.55ms —
> 5.5x faster than a single one-way hop.
>
> ## The reasoning error
>
> This document explained the null result by saying a fixed per-link
> delay "gets absorbed by pipelining rather than serializing onto the
> critical path." That is wrong. Pipelining hides delay's effect on
> **throughput**, because many commands are in flight across
> overlapping rounds. It cannot hide it from **per-command latency**,
> because each individual command still waits its own 3 rounds.
> Conflating the two turned an impossible measurement into an
> apparent explanation, and let a broken mechanism look verified for
> the entire 384-run factorial that followed.
>
> ## What survives
>
> The +17% same-sweep difference reported below (baseline 43.0k vs
> leader+50ms 50.4k, back-to-back, 3 reps each) is a real, unexplained
> effect — but it cannot be a latency effect. Across the full
> factorial, delay *magnitude* turned out to be inert
> (r ~ 0 with tps within every well-sampled shape), which points at
> the act of installing the qdisc rather than the delay it carries.
> Installing `prio` replaces the NIC's default root qdisc — `mq` with
> 64 hardware TX queues each running `fq_codel`. See the retraction
> header in `NETEM_FACTORIAL_ANALYSIS.md` for the full re-analysis and
> the `delay 0ms` control that would settle it.
>
> ---

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
