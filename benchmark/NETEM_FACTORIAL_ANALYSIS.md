> # ⚠️ RETRACTED — 2026-09-07
>
> **The headline findings in this document are void. The injected
> network latency never reached the consensus path, so every result
> below was measured under a manipulation that did not happen.**
>
> ## Proof
>
> Client-side latency is genuine end-to-end: the timer starts at
> command send (`examples/hotstuff_client.cpp`) and stops on the
> f+1-th ack, and a replica only acks from inside the commit path
> (`do_decide`, `src/consensus.cpp:148`, after the 3-chain safety
> check). A commit therefore crosses ~6 delayed hops, so 200ms
> one-way implies a floor of roughly 1200ms per command.
>
> Measured, across ~1.7M commands:
>
> | condition | min | p50 | p99 | max |
> |---|---|---|---|---|
> | no delay (control) | 1.79 | 8.19 | 17.23 | 32.25 ms |
> | follower0 @200ms | 2.25 | 8.54 | 18.06 | 34.86 ms |
> | leader @200ms | 0.94 | 6.87 | 16.26 | 35.84 ms |
> | all 3 followers @200ms | **1.17** | 7.14 | 16.88 | **36.55 ms** |
>
> The slowest of 431,947 commands under "all followers +200ms" was
> 36.55ms — 5.5x faster than a *single* one-way hop. Not one command
> shows any trace of the delay.
>
> The `tc` rules were installed (ping verification in
> `NETEM_ANALYSIS.md` is exact) and the replicas do use the filtered
> addresses (`10.10.1.x:10000` on `enp65s0f0np0`). The break is
> somewhere between "rules installed" and "app traffic traverses
> them"; diagnosing it needs the cluster.
>
> ## What the data actually shows
>
> Re-analysed with the delay assumed inert:
>
> - **Delay magnitude does nothing.** Within each shape (qdisc
>   topology fixed, only the value varying), r(tps, magnitude) is
>   ~0 for every well-sampled shape: +0.08, -0.05, +0.22, +0.33.
>   The 50/100/150/200 ladder has no effect.
> - **Six of seven shapes are indistinguishable.** bs200: 55.3-56.3k
>   (within 1.8%). bs3200: 63.2-64.4k (within 1.9%). There is no
>   1->2->3-follower ladder and no leader-vs-follower gradient.
> - **One anomaly remains**: `f0only` at 46.2k (bs200) / 55.0k
>   (bs3200), 14-17% below all others — present in the
>   single-reservation bs3200 block, so not a reservation artifact.
> - **Unexplained**: in `NETEM_ANALYSIS.md`'s sanity test, baseline
>   (43.0k) and leader+50ms (50.4k) ran back-to-back in one sweep,
>   +17%. Installing the rules moved throughput even though the
>   delay did not apply.
>
> **Leading hypothesis (untested):** installing `prio` replaces the
> NIC's default root qdisc, which is `mq` with 64 hardware TX queues
> each running `fq_codel`. Collapsing that into one classful `prio`
> qdisc is a large egress-path change independent of the delay
> value — consistent with both the magnitude-independence and the
> step-not-gradient shape.
>
> **Control experiment to settle it:** apply the identical qdisc
> topology with `delay 0ms` on every band. If throughput still
> moves, it is the qdisc replacement, not network delay.
>
> Everything below is retained for the record. The harness, parser,
> run_logs and ~1.7M raw latency samples remain valid; only the
> latency-injection link is broken.
>
> ---

# Network-Latency Factorial — 384 Runs, Complete

N=4 replicas (node1 = fixed leader, `dummy` pacemaker), 1 dedicated
client node, SmallBank (`sb_users=1000`, `p_mtx=0.9`, `skew=0.1`),
60s per run, CloudLab Utah `d6515`.

Design: 7 node-latency shapes × 4-value ladder {50,100,150,200}ms, full
factorial (192 assignments) × 2 baseline points = **384 runs**.
Latency injected with `tc` `prio`+`netem`+`u32`, link delay =
`max(lat_a, lat_b)` applied symmetrically. All 384 rows completed with
valid metrics; 0 missing.

## Headline result

**Injecting network latency does not degrade this system. It usually
improves it. The single worst configuration is delaying exactly one
follower — and delaying all three followers is the best.**

Reference points with **no** artificial latency (from `baseline_refresh`):

| baseline | tps | mean latency |
|---|---|---|
| bs=200, ma=400 | ~46,400 | ~8.6 ms |
| bs=3200, ma=8000 | 57,079 | 141.9 ms |

Against that, in the bs=3200/ma=8000 block (all 192 rows on a single
reservation, no confound), every node delayed at 200ms:

| condition | tps | vs no-delay | mean latency |
|---|---|---|---|
| no delay | 57,079 | — | 141.9 ms |
| 1 follower @200ms | 55,672 | −2.5% | 146.0 ms |
| leader @200ms | 63,610 | **+11.4%** | 127.6 ms |
| 2 followers @200ms | 62,595 | **+9.7%** | 129.4 ms |
| 3 followers @200ms | 65,568 | **+14.9%** | 123.9 ms |

Adding 200ms of delay to three of four machines raises throughput ~15%
and *lowers* mean commit latency ~13%.

## Leader-delay vs follower-delay is robust

The clearest contrast — leader alone vs one follower alone — holds at
all four ladder values, in both baselines, with no overlap:

bs=3200 / ma=8000:

| delay | leader alone | 1 follower alone | gap |
|---|---|---|---|
| 50 ms | 62,289 | 55,723 | +11.8% |
| 100 ms | 62,704 | 55,099 | +13.8% |
| 150 ms | 64,132 | 53,484 | +19.9% |
| 200 ms | 63,610 | 55,672 | +14.3% |

bs=200 / ma=400 reproduces the same direction (leader ~54.2–57.8k vs
one follower ~45.2–47.7k). 4/4 consistent in each block, ~12–20%
separation against a p90 noise floor of 5.7% — this is a real effect,
not sampling noise.

Critically, **this contrast is not confounded by the mid-sweep
reservation change**: in each baseline block, `leaderonly` and `f0only`
were both collected on the *same* reservation.

## Monotonic in the number of delayed followers

bs=3200/ma=8000, each delayed node at 200ms:

    1 follower  → 55,672 tps / 146.0 ms   (worst)
    2 followers → 62,595 tps / 129.4 ms
    3 followers → 65,568 tps / 123.9 ms   (best)

More delayed nodes is monotonically *better*. This inverts the naive
quorum prediction.

## Why the naive quorum explanation fails

With N=4, f=1, a quorum is 3 votes (leader + 2 of 3 followers). The
intuitive model says:

- delay 1 follower → leader forms quorums from the 2 fast followers,
  the delayed one is simply excluded → **no effect expected**
- delay all 3 followers → every quorum must wait the full RTT →
  **worst case expected**

The measurements are the exact opposite of both predictions. The naive
quorum model is therefore wrong for this system, and any explanation
resting on "which votes form the quorum" needs to be discarded.

## Working hypothesis — NOT yet verified

Earlier in this study we established by direct syscall counting that
this deployment is CPU-bound, and that `sendto` volume scales with
*committed commands*, not with consensus rounds. Under that constraint
a plausible reading is that `netem` delay acts as a **pacer**: it
smooths arrival bursts at the CPU-saturated leader, reducing contention
on the send path, so effective throughput rises. Delaying exactly one
follower would then be the worst case because it maximises asymmetry
(two followers still hammering at full rate) while providing the least
smoothing.

**This is a hypothesis, not a finding.** It is consistent with the data
but has not been tested.

### Proposed falsification test

If pacing is the mechanism, the benefit must depend on saturation.
Re-run the ladder at a *low* `max_async` (e.g. 10 or 175), where the
system is far from saturated:

- delay still helps → pacing hypothesis is **wrong**
- delay hurts, as ordinary intuition expects → pacing **supported**

This is cheap (a few dozen runs) and sharply discriminating.

## Data validity

**Leaked-SSH-connection contamination: ruled out.** An orchestrator bug
accumulated ~2 idle SSH connections per host per row (peaking at 478/host)
before being fixed. Tested for measurement bias using protocol symmetry —
node0/2/3 are interchangeable followers, so runs sharing
`(block_size, max_async, leader_lat, sorted[follower_lats])` must be
statistically identical, yet ran at different leak doses:

| test | result |
|---|---|
| within-class centered tps vs leak dose | r = **−0.008** (n=284, 98 classes) |
| within-class centered latency vs leak dose | r = −0.007 |
| paired sign test (higher-leak worse?) | 48.0% (50% = null) |
| rows run during worst stall (leak 440–470) | tps **+0.7%**, latency −1.0% |

Mechanism agrees: all 959 leaked `sshd` processes consumed **1 second**
of CPU total over 12 hours; memory 5.5/128 GB; load 0.08; and the SSH
control path is on a **different physical NIC** (`enp1s0f0np0`) than
consensus traffic (`enp65s0f0np0`), which is also the only interface
`tc` touches.

**Noise floor** (within protocol-equivalent classes, same reservation,
n=98): median 2.35%, p90 5.72%, max 8.30%. Treat differences below
~2.5% as indistinguishable.

### Open confound — mid-sweep reservation change

75 of 384 rows were collected on an earlier reservation before it
expired. Only 2 equivalence classes span both reservations; they show
−3.5% and −6.8% tps on reservation 2, right at the p90 noise level —
too weak (n=2) to separate a real hardware offset from noise.

Affected cells:

| block | status |
|---|---|
| bs=3200 / ma=8000, all 7 shapes (192 rows) | **clean** — single reservation |
| bs=200/ma=400 `f0_f2`, `f0only`, `leader_f0`, `leaderonly` | res-1 only, internally consistent |
| bs=200/ma=400 `all4distinct`, `f0_f2_f3` | res-2 only, internally consistent |
| bs=200/ma=400 `leader_f0_f2` | **SPLIT 35/29 — contaminated** |

All headline findings above are drawn from uncontaminated comparisons.
Cross-shape comparisons *within* bs=200/ma=400 that straddle the
boundary should be treated as provisional, as should the split
`leader_f0_f2` cell.

**Remedy** (~85 min): re-run the 75 reservation-1 rows on the current
reservation under distinct run_ids, making the whole dataset
single-reservation.

## Caveats

- Ladder cells at a single latency value are frequently n=1. The
  *aggregate* patterns (4/4 consistency, 12–20% gaps) are solid; any
  individual cell value is not.
- The 1→2→3 follower monotonic trend is n=1 per point. Endpoints differ
  by 18%, well above noise, but this specific ladder deserves
  replication before being quoted as a precise magnitude.
- Single client node throughout; results are for a client-saturated,
  CPU-bound regime and should not be extrapolated to network-bound
  deployments.
