# Investigation Record — how the network-latency result was reached, and how it went wrong first

This supersedes `NETEM_ANALYSIS.md` and `NETEM_FACTORIAL_ANALYSIS.md`, both
of which carry retraction headers. It is written as a record rather than a
report: every claim made along the way is kept, with what killed it, because
the sequence of errors is the most useful thing here. Several of them were
mutually reinforcing, and each one looked well-supported at the time.

---

## 1. The result

**Injected network latency degrades consensus exactly as textbook HotStuff
predicts. Throughput collapses 174x. The quorum model is correct.**

N=4, f=1, quorum = leader + 2 of 3 followers. node1 is the fixed proposer
(`dummy` pacemaker, `opt_fixed_proposer=1`). 200ms one-way injected per the
`max(lat_a, lat_b)` rule, `block_size=200`, `max_async=400`, 60s runs.

| shape | delayed nodes | rounds/60s | **true tps** | client-reported tps |
|---|---|---:|---:|---:|
| baseline | none | 26,463 | **87,125** | 44,070 |
| foll1 | node0 | 27,724 | **88,707** | 42,855 |
| leader | node1 | 153 | **501** | 48,915 |
| foll2 | node0,2 | 153 | **500** | 47,578 |
| foll3 | node0,2,3 | 153 | **500** | 47,290 |
| all4 | all | 152 | **498** | 50,012 |

`foll1` is untouched because delaying a *single* follower leaves the leader
two fast followers to form a quorum from. Delay two or more, or the leader
itself, and every quorum must wait a 400ms round trip. That is precisely the
naive prediction — which this study spent days believing it had disproven.

**The client-reported column reports a 174x collapse as a 10% improvement.**
It is not noisy. It is inverted.

### 1.1 Three independent instruments agree

None of them route through the client metric.

**Vote timing, on the leader's own clock** (no cross-machine comparison, so
no NTP assumption):

```
propose <block 6012d227ec>        11.196988
got <vote rid=1 blk=6012d227ec>   11.197188    +0.2ms    <- leader's self-vote
got <vote rid=3 blk=6012d227ec>   11.598357  +401.4ms
got <vote rid=2 blk=6012d227ec>   11.598527  +401.5ms
```

**Round counts**: 26,463 -> 153 when the leader's quorum path is delayed.

**`tc` packet counters** on the leader, sampled every 30s during the runs:
the three `netem ... delay 200ms` bands carry traffic (230/232/230 pkt,
matching ~150 rounds), the undelayed default band carries client traffic
(297,454 pkt), and `dropped 0, overlimits 0` throughout -- so `limit 1000`
never overflowed, contrary to an earlier worry.

---

## 2. What actually broke the measurement

Two defects in the client, neither of which is Heena's code -- both are
upstream libhotstuff.

### 2.1 The dominant one: the shutdown dump races SIGKILL

`examples/hotstuff_client.cpp`, after `ec.dispatch()` returns on SIGTERM:

```cpp
#ifdef HOTSTUFF_ENABLE_BENCHMARK
    for (const auto &e: elapsed) {
        localtime(...); strftime(...); fprintf(stderr, ...);   // per record
    }
#endif
```

The harness sends SIGTERM, `sleep 2`, then SIGKILL
(`CommandMaker.kill()`). The dump is a single-threaded
`localtime`+`strftime`+`fprintf` per record and simply writes what it can
in two seconds.

Evidence: **every client log in the study is ~21.6 MB / ~416k records**
(21,558,935 to 21,684,411 bytes, within 0.6%) across a 16x range of block
size, with and without netem, delayed and undelayed. That is a fixed cap,
not a workload-dependent quantity.

Consequences, and they apply to **every run in the entire study**:

- `n_committed` is a truncated prefix, not a total.
- `duration_s` is derived from the dumped records' timestamp span, so it
  covers only the first ~9 seconds of a 60s run -- startup transient
  included.
- `tps` and `latency_ms_*` are therefore computed over an early, biased
  window.

The arithmetic that proves it independently: in `P1_bs200_ma8000` the
leader proposed 28,853 blocks x 200 cmds = **5.77M commands**, and a leader
can only propose commands the client actually sent. So the client completed
on the order of 5.77M, and 415,205 records survived.

### 2.2 Use-after-end in the response handler

`examples/hotstuff_client.cpp`:

```cpp
auto it = waiting.find(cmd_hash);
auto &et = it->second.et;         // dereferenced HERE
if (it == waiting.end()) return;  // guard comes AFTER
```

Introduced upstream in `cf3f1c3b` (Determinant / Ted Yin, 2018-08-20) while
hoisting `et` into a local reference; the hoist landed one line above the
guard instead of below. Still present in HEAD. The file is 29 commits by
Determinant and 4 by HeenaNagda, all four of hers SmallBank-related -- she
never touched this function.

It fires reliably: the client broadcasts each command to all 4 replicas but
erases after f+1 = 2 acks, so acks 3 and 4 always arrive for a hash no
longer in `waiting`.

Related weaknesses in the same handler, found while tracing the flow:

- `confirmed` counts *responses*, not distinct replicas.
- `fin.decision` is never checked, so a `decision=0` reply counts as a
  confirmation. `src/hotstuff.cpp:454` sends exactly such a reply
  immediately when a command hash is already pending -- meaning a single
  replica could in principle supply both acks that satisfy f+1. Not
  demonstrated firing here.
- `et.stop()` runs on every ack, including stale ones via the UB path.

**Impact of 2.2 is unproven.** 2.1 is confirmed by direct measurement; 2.2
is an unambiguous defect whose contribution has not been isolated.

---

## 3. The historical record

Kept deliberately. Each claim was believed on evidence at the time.

| # | Claim | Status | What settled it |
|---|---|---|---|
| 1 | Scaled threads give +5.2% at high load | **Noise** | 96-run replicated sweep; no consistent direction or magnitude |
| 2 | The leader is single-thread CPU bound | **False** | Misread `ps -eo %cpu` (process aggregate). Per-thread `ps -eLo` showed work across 12 threads, none near saturation |
| 3 | Per-command crypto verification is the cost | **False** | Client commands carry no signature at all; crypto is per-round QC verification |
| 4 | `sendto` scales with commits, not rounds | **Holds** | Direct `strace -c -f` syscall counts across 5 configurations |
| 5 | netem mechanism "verified" by ping | **Incomplete** | Ping proved ICMP shaping only. True but insufficient |
| 6 | Delaying the leader doesn't hurt, often helps | **Artifact** | Client metric truncation + inversion |
| 7 | Delay is monotonically *better* with more delayed followers | **Artifact** | Same cause. Real behaviour is a step function on quorum reachability |
| 8 | "The naive quorum model is dead" | **False** | The quorum model is exactly right; `foll1` fast, everything else collapsed |
| 9 | Pipelining absorbs per-link delay | **Reasoning error** | Pipelining hides delay from *throughput*, never from *per-command latency*. Conflating them turned an impossible 3.11ms measurement into an apparent explanation |
| 10 | The delay never reached application traffic | **False** | Inter-replica TCP handshakes measured 400.22ms on delayed links vs 10.98ms undelayed |
| 11 | `discover_iface`'s raw ssh call caused the connection leak | **False** | The leak was `kill()`'s unclosed `Group(*hosts)`, 2/host/row x 235 rows = 470, measured 478 |
| 12 | Leak fix verified | **Invalid test** | Connections were counted *after* the process exited, when they die regardless. Re-measuring during a run showed it still climbing (3 -> 33 by row 7) |
| 13 | `block_size` may not be honoured at runtime | **False** | `ncmds=` equals the configured value in every block across ~28,000 blocks, single distinct value per run |
| 14 | `block_size` does not change throughput | **Holds** | True on the clean replica-side measure: 92.5k / 95.6k / 87.8k across a 16x range |

### 3.1 Why claims 6-8 were so convincing

They were not a single bad sample. They were 384 runs, replicated, with a
measured noise floor (2.35% median, 5.72% p90) and consistent 4/4
directional agreement across a ladder. Every statistical check passed
because the corruption was systematic, not random -- the client reported
~416k commits at ~8ms whether consensus was running 26,463 rounds or 153.

The lesson is that replication and effect-size discipline do not protect
against a broken instrument. Only an independent instrument does.

### 3.2 The signal that was visible the whole time

`NETEM_ANALYSIS.md` reported leader+50ms at **p50 = 3.11ms**. A 50ms
one-way delay implies roughly 300ms of round trips on the commit path. That
number was impossible from the moment it was written, and claim 9 was
constructed to explain it instead of doubting it.

---

## 4. What survives

- **`sendto` scales per-command** (claim 4) -- from `strace` counts, never
  touched the client metric.
- **`block_size` is honoured exactly** (claim 13) -- from replica proto
  logs.
- **`block_size` does not change throughput** (claim 14) -- and now with a
  mechanism: rounds scale inversely and near-exactly (28,853 -> 7,450 ->
  1,709 for 200/800/3200, i.e. 3.87x and 4.35x for 4x block sizes), so
  commands/second is invariant. Consistent with a per-command bottleneck.
- **The harness, parser, and run_logs.** The raw logs are sound; only the
  client-side derived metrics are affected.

Absolute throughput was understated roughly 2x throughout: true baseline is
~87-95k tps, not the ~44-48k reported.

---

## 5. Open questions

1. **The clean 2x gap.** True-vs-reported tps came out at 1.94 / 1.98 /
   2.03 / 1.98 across Phase 1. Truncation alone should give a
   workload-dependent ratio, not a constant near 2. Something structural is
   still unaccounted for, and no fix should be trusted until it is
   explained.
2. **Contribution of the use-after-end bug** (2.2), unseparated from 2.1.
3. **The logs-on/off A/B is unusable as run.** Both passes truncate at the
   same cap, so it compared two truncated prefixes; and the logs-off pass
   has no proto logs, so no clean measure exists for it. A future pass
   needs `proto_log` at least on the leader, or a longer grace period.

### Suggested next steps

- Raise the SIGKILL grace period (`CommandMaker.kill()`, `sleep 2`) and
  re-run one config. If `n_committed` rises toward `rounds x ncmds`, 2.1 is
  confirmed as dominant and the metric becomes usable.
- Only then fix 2.2, and measure whether anything further changes.
- Re-run the network-latency sweep on the corrected measurement path. The
  384-run factorial needs redoing regardless; its reservation confound is
  now moot.

---

## 6. Data

| file | contents |
|---|---|
| `results/phase1_batchsize_results.csv` | 4 rows, block-size ladder, `proto_log=ON` |
| `results/phase2_log_results.csv` | 18 rows, 6 shapes x 3 reps, `proto_log=ON` |
| `results/phase2_nolog_results.csv` | 18 rows, same shapes, `proto_log=OFF` |
| `results/run_logs/P1_*`, `P2L_*`, `P2N_*` | per-run raw logs, 40 dirs |
| `results/netem_factorial_results.csv` | the 384-run sweep (superseded; tps/latency invalid) |

The `tps` and `latency_ms_*` columns in every CSV above are subject to
section 2.1. Use `rounds x ncmds / span` from the replica proto logs
instead, which is what the tables in section 1 report.

Reservation: CloudLab Utah Exp-3, `d6515`. node0 amd026, node1 amd006
(leader), node2 amd004, node3 amd016, node4 amd024 (client), node5 amd023
(orchestrator, excluded from the manifest).
