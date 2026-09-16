# Replica failure -- leader and follower, and the impeachment timeout

Phase 3 of the study. Measurement conventions and baselines are those of
`BASELINE_ANALYSIS.md`:

- throughput and latency are **fixed-window** figures (`tps_steady`,
  `latency_ms_mean_steady`), never the legacy first-to-last-commit `tps`
  (`BASELINE_ANALYSIS.md` section 13);
- the injected condition is **verified in every run**, here from the
  killed replica's own process state and from every replica's command
  line;
- baselines B1-B4 at threads 4, 90% writes, skew 0.1, no injected delay.

Reservation: CloudLab Utah Exp-3, `d6515` nodes (AMD EPYC 7452, 32 physical
cores / 64 hardware threads, 125 GB), 4 replicas + 1 client host.

Totals: **400 runs** in two sweeps (Stage L 100, Stage LT 300), 0 run
errors, 0 parse failures.

**Only findings are recorded. No mechanism is proposed for any of them.**

---

## 1. Design

Both sweeps share one design; Stage LT repeats it at three shorter
impeachment timeouts.

| factor | levels |
|---|---|
| failure situation | none (control); leader crash; leader freeze; follower crash; follower freeze |
| baselines | B1, B2, B3, B4 |
| impeachment timeout | 11 s (Stage L, the default), then 5 s, 2 s, 1 s (Stage LT) |

5 situations x 4 baselines x 5 reps = 100 runs per timeout, in rep-major
order, shuffled with a fixed seed.

Every run: **120 s**, 10 s measurement warm-up, 2 s cool-down, failure
injected at **t = 40 s** (median launch offset 0.26 s after the 40 s
mark), rotating pacemaker `rr`, protocol logging on, compute sampler on.

The baselines, unchanged from earlier phases:

| | clients | `max_async` | block size |
|---|---|---|---|
| B1 | 2 | 1,000 | 200 |
| B2 | 4 | 1,000 | 800 |
| B3 | 8 | 1,000 | 1,600 |
| B4 | 8 | 4,000 | 3,200 |

**Which replica fails.** Under `rr` all four replicas settle on **replica
0** at startup and stay there while commits keep arriving
(`BASELINE_ANALYSIS.md` section 15), so replica 0 is the leader. The
leader arm kills replica 0; the follower arm kills **replica 3**, which
Stage U found to be the replica using the most CPU
(`COMPUTE_ANALYSIS.md` section 3). Leader and follower failures are never
combined: each run injects exactly one failure.

**Pacemaker `rr`.** Rotation happens only when the impeachment timer
fires, and every commit resets that timer (`on_consensus` in
`include/hotstuff/liveness.h`, `reset_imp_timer` in
`examples/hotstuff_app.cpp`). The timeout is `--imp-timeout`, default 11
s. That is why a failure is needed to make `rr` rotate at all, and why
the timeout is the second factor here.

---

## 2. Mechanism: `benchmark/fail_inject.sh`

Launched on the target replica's host right after the clients boot, it
sleeps for the delay and then signals `hotstuff-app`:

- **crash** = `SIGKILL` -- the process ends and its connections close;
- **freeze** = `SIGSTOP` -- the process stays alive with its connections
  open, but runs nothing.

One second later it reads the process state and writes one JSON object
per run (`failure-replica-<i>.json`): the signal, the PID, the
wall-clock injection time, the kill return code, and that state --
`gone`/`Z` after a crash, `T` after a freeze. That file is the per-run
evidence that the failure landed, and its `injected_epoch` is the
reference time **T** used by every window below.

The impeachment timeout is passed as `--imp-timeout <t>` to every
replica, and the compute sampler records each replica's full command
line once a second, so the setting is checkable per run.

---

## 3. Verification

| | Stage L (11 s) | 5 s | 2 s | 1 s |
|---|---|---|---|---|
| runs | 100 | 100 | 100 | 100 |
| injections verified | 80 / 80 | 80 / 80 | 80 / 80 | 80 / 80 |
| timeout on all 4 replicas' command lines | not recorded | 100 / 100 | 100 / 100 | 100 / 100 |
| run errors, parse failures | 0 | 0 | 0 | 0 |

Stage L ran before the sampler recorded command lines, so its timeout is
the built-in default rather than a value read back from the runs.

---

## 4. What each number means

For every run, the clients' per-second commit counts and latency sums are
placed on one wall clock, and then, around the injection time T:

| name | definition |
|---|---|
| **before** | mean tx/s over [T-30, T) |
| **after** | mean tx/s over [T+40, T+76) |
| **outage** | longest run of seconds with zero commits in [T, T+40) |
| **zero seconds** | how many seconds in [T, T+40) had zero commits |
| **resumed at** | seconds after T at which commits started again and did not stop again inside the window |
| **first rotation** | seconds after T of the earliest "Pacemaker: rotate to" line in any replica log |
| **normal** | the same "after" window in that baseline's no-failure control runs |

A run counts as **never recovered** when its after window averaged below
10% of its own before window. Those runs are excluded from the medians
and counted separately in every table.

All figures below are **medians over the 5 reps** of a cell.

---

## 5. Stage L -- failure at the default 11 s timeout

Each table: that baseline's no-failure control first, then the four
failure situations.

#### B1 -- 2 clients, block 200

| situation | throughput | vs normal | latency | outage | never recovered |
|---|---|---|---|---|---|
| no failure | 162,694 | -- | 12.3 ms | 0 s | 0 / 5 |
| leader crash | 145,171 | -17,523 (-10.8%) | 13.8 ms | 11 s | 1 / 5 |
| leader freeze | 144,978 | -17,716 (-10.9%) | 12.6 ms | 11 s | 0 / 5 |
| follower crash | 168,084 | +5,389 (+3.3%) | 11.9 ms | 0 s | 0 / 5 |
| follower freeze | 168,596 | +5,901 (+3.6%) | 11.9 ms | 0 s | 0 / 5 |

#### B2 -- 4 clients, block 800

| situation | throughput | vs normal | latency | outage | never recovered |
|---|---|---|---|---|---|
| no failure | 300,438 | -- | 13.3 ms | 0 s | 0 / 5 |
| leader crash | 323,115 | **+22,676 (+7.5%)** | 12.4 ms | 11 s | 0 / 5 |
| leader freeze | 324,285 | **+23,847 (+7.9%)** | 12.3 ms | 11 s | 0 / 5 |
| follower crash | 356,982 | **+56,544 (+18.8%)** | 11.2 ms | 1 s | 0 / 5 |
| follower freeze | 357,709 | **+57,271 (+19.1%)** | 11.2 ms | 0 s | 0 / 5 |

#### B3 -- 8 clients, block 1,600

| situation | throughput | vs normal | latency | outage | never recovered |
|---|---|---|---|---|---|
| no failure | 430,719 | -- | 18.6 ms | 0 s | 0 / 5 |
| leader crash | 385,197 | -45,522 (-10.6%) | 20.8 ms | 11 s | 1 / 5 |
| leader freeze | 373,860 | -56,859 (-13.2%) | 21.4 ms | 11 s | 0 / 5 |
| follower crash | 425,303 | -5,416 (-1.3%) | 18.8 ms | 0 s | 0 / 5 |
| follower freeze | 421,446 | -9,273 (-2.2%) | 19.0 ms | 0 s | 0 / 5 |

#### B4 -- 8 clients, block 3,200, `max_async` 4,000

| situation | throughput | vs normal | latency | outage | never recovered |
|---|---|---|---|---|---|
| no failure | 434,083 | -- | 73.7 ms | 0 s | 0 / 5 |
| leader crash | 379,206 | -54,877 (-12.6%) | 76.0 ms | 11 s | 1 / 5 |
| leader freeze | 379,966 | -54,117 (-12.5%) | 79.7 ms | 10 s | 1 / 5 |
| follower crash | 421,468 | -12,615 (-2.9%) | 75.0 ms | 0 s | 0 / 5 |
| follower freeze | 413,678 | -20,405 (-4.7%) | 77.2 ms | 0 s | 0 / 5 |

### The pattern at 11 s

| | leader crash | leader freeze | follower crash | follower freeze |
|---|---|---|---|---|
| B1 | ~11% lower | ~11% lower | about the same | about the same |
| **B2** | **~8% higher** | **~8% higher** | **~19% higher** | **~19% higher** |
| B3 | ~11% lower | ~13% lower | about the same | about the same |
| B4 | ~13% lower | ~13% lower | ~3% lower | ~5% lower |

**Crash and freeze behaved the same** in every cell. A frozen leader keeps
its TCP connections open and a killed one does not, and that made no
measurable difference to the outage or to the throughput afterwards.

### One outage or two

The "outage" column is the longest single stretch of zero-commit seconds.
Counting **every** zero second in the 40 s after the failure separates the
baselines:

| | longest stretch | total zero seconds | commits resumed at |
|---|---|---|---|
| B1 | 11 s | 11 s | T + 12 s |
| B2 | 11 s | 11 s | T + 12 s |
| B3 | 11 s | 22 s | T + 24 s |
| B4 | 10.5 s | 20.5 s | T + 23.5 s |

At B3 and B4 the usual leader-failure run stops twice for about 11 s each:
commits return briefly, stop again, and only then continue. Of the 36
leader-failure runs that recovered at 11 s, 13 lost 10-11 s in total, 22
lost 20-22 s, and one lost 38 s.

---

## 6. Stage LT -- the same sweep at 5 s, 2 s and 1 s

`--imp-timeout` was lowered to 5, 2 and 1 second and the whole 100-run
design repeated at each. Every level has its own no-failure controls, so
each row is compared with normal throughput measured at that same
timeout.

### Leader failure

#### B1

| timeout | normal | after a crash | vs normal | after a freeze | vs normal |
|---|---|---|---|---|---|
| 11 s | 162,694 | 145,171 | -17,523 (-10.8%) | 144,978 | -17,716 (-10.9%) |
| 5 s | 165,805 | 145,439 | -20,367 (-12.3%) | 146,061 | -19,745 (-11.9%) |
| 2 s | 167,463 | 143,473 | -23,990 (-14.3%) | 144,174 | -23,289 (-13.9%) |
| 1 s | 164,943 | 145,273 | -19,671 (-11.9%) | 142,208 | -22,736 (-13.8%) |

#### B2

| timeout | normal | after a crash | vs normal | after a freeze | vs normal |
|---|---|---|---|---|---|
| 11 s | 300,438 | 323,115 | +22,676 (+7.5%) | 324,285 | +23,847 (+7.9%) |
| 5 s | 297,095 | 318,577 | +21,482 (+7.2%) | 318,824 | +21,729 (+7.3%) |
| 2 s | 292,353 | 317,842 | +25,489 (+8.7%) | 317,296 | +24,943 (+8.5%) |
| 1 s | 299,136 | 316,540 | +17,403 (+5.8%) | 317,039 | +17,903 (+6.0%) |

#### B3

| timeout | normal | after a crash | vs normal | after a freeze | vs normal |
|---|---|---|---|---|---|
| 11 s | 430,719 | 385,197 | -45,522 (-10.6%) | 373,860 | -56,859 (-13.2%) |
| 5 s | 430,966 | 342,796 | -88,169 (-20.5%) | 385,312 | -45,653 (-10.6%) |
| 2 s | 421,510 | 368,759 | -52,752 (-12.5%) | 374,841 | -46,669 (-11.1%) |
| 1 s | 415,166 | 378,812 | -36,353 (-8.8%) | 381,314 | -33,852 (-8.2%) |

The 5 s crash figure is the median of the **2 runs that recovered** out of
5; it is the thinnest cell in the study.

#### B4

| timeout | normal | after a crash | vs normal | after a freeze | vs normal |
|---|---|---|---|---|---|
| 11 s | 434,083 | 379,206 | -54,877 (-12.6%) | 379,966 | -54,117 (-12.5%) |
| 5 s | 433,081 | 363,805 | -69,276 (-16.0%) | 375,864 | -57,217 (-13.2%) |
| 2 s | 430,600 | 372,777 | -57,823 (-13.4%) | 375,482 | -55,118 (-12.8%) |
| 1 s | 424,661 | 376,735 | -47,926 (-11.3%) | 372,598 | -52,063 (-12.3%) |

### Follower failure

Difference from normal at the same timeout. No cell had an outage, and no
follower-failure run in any of the 400 runs failed to recover.

| | 11 s | 5 s | 2 s | 1 s |
|---|---|---|---|---|
| B1 crash | +3.3% | +2.2% | +0.5% | +2.1% |
| B1 freeze | +3.6% | +0.3% | -0.9% | +1.6% |
| **B2 crash** | **+18.8%** | **+20.3%** | **+20.0%** | **+18.5%** |
| **B2 freeze** | **+19.1%** | **+20.4%** | **+22.2%** | **+17.1%** |
| B3 crash | -1.3% | +0.8% | +2.4% | +1.6% |
| B3 freeze | -2.2% | -1.3% | +2.9% | +3.6% |
| B4 crash | -2.9% | -5.7% | -7.8% | -1.0% |
| B4 freeze | -4.7% | -2.8% | -5.7% | -1.9% |

---

## 7. How long commits stopped

Medians over the leader-failure runs that recovered. "Longest" is the
longest single stretch of zero-commit seconds; "total" counts every
zero-commit second in the 40 s after the failure; "resumed at" is when
commits started again and did not stop again inside that window.

| timeout | | B1 | B2 | B3 | B4 |
|---|---|---|---|---|---|
| **11 s** | longest | 11 s | 11 s | 11 s | 10.5 s |
| | total | 11 s | 11 s | 22 s | 20.5 s |
| | resumed at | T+12 s | T+12 s | T+24 s | T+23.5 s |
| **5 s** | longest | 5 s | 5 s | 5 s | 5 s |
| | total | 7.5 s | 5 s | 10 s | 10 s |
| | resumed at | T+9 s | T+6 s | T+12 s | T+12 s |
| **2 s** | longest | 2 s | 2 s | 2 s | 2 s |
| | total | 2 s | 3 s | 4 s | 4 s |
| | resumed at | T+3 s | T+5.5 s | T+6 s | T+6 s |
| **1 s** | longest | 1 s | 0.5 s | 1 s | 1 s |
| | total | 2 s | 0.5 s | 2 s | 2 s |
| | resumed at | T+4 s | T+3 s | T+4 s | T+4 s |

The longest single stretch equals the timeout at every level and every
baseline. The **total** is one timeout at B1 and B2 and two timeouts at
B3 and B4: those runs stop, commit briefly, and stop again for the same
length before continuing.

---

## 8. What the replica logs show

Protocol logging was on in all 400 runs, so every "Pacemaker: rotate to"
and "Pacemaker: stop rotation at" line is recorded with a timestamp.

| | 11 s | 5 s | 2 s | 1 s |
|---|---|---|---|---|
| leader at start | replica 0 in 40/40 | 40/40 | 40/40 | 40/40 |
| first rotation after the failure | 11.0 s | 5.0 s | 2.0 s | 1.0 s |
| rotate lines per recovered run (3 survivors, so 3 lines = one rotation step) | 6 (22 runs), 3 (13) | 6 (16), 3 (12) | 6 (25), 3 (10) | 6 (24), 3 (11) |
| leader they settled on | 2 (22 runs), 1 (14) | 2 (16), 1 (14), 3 (2) | 2 (25), 1 (10), 3 (2) | 2 (24), 1 (11), 3 (2) |

The first rotation lands one timeout after the failure, to the second, at
every level: across the 143 recovered runs the only values recorded are
11.0, 5.0, 2.0 and 1.0 s, plus two runs that had rotated near start,
before the failure.

A run that logs 3 rotate lines settles on replica 1 and a run that logs 6
settles on replica 2 -- in most runs the replicas rotated **past** the
first surviving replica to the second one, which is where the second
outage at B3 and B4 falls.

---

## 9. Runs that never recovered

17 of the 160 leader-failure runs never came back: their throughput over
[T+40, T+76) rounded to 0.0% of their own before value in all 17 (one of
them still committed a trickle, too small to show at one decimal).

| timeout | never recovered | where |
|---|---|---|
| 11 s | 4 / 40 | B1 crash 1, B3 crash 1, B4 crash 1, B4 freeze 1 |
| 5 s | 7 / 40 | B3 crash 3, B3 freeze 2, B4 crash 2 |
| 2 s | 3 / 40 | B3 crash 2, B4 crash 1 |
| 1 s | 3 / 40 | B2 crash 1, B2 freeze 1, B4 crash 1 |

They happen at every timeout, with no trend across timeouts. In these runs
the replicas kept rotating -- 15 to 41 rotate lines against the usual 3 or
6 -- and settled on replica 3, replica 1 or replica 0 rather than on the
usual replica 2.

**No follower-failure run and no no-failure run, at any timeout, failed to
recover.** All 17 are leader failures.

---

## 10. Leader changes without a failure

The no-failure controls show how often `rr` rotated on its own:

| timeout | controls with any leader change | of those, after the 40 s mark |
|---|---|---|
| 11 s | 1 / 20 | 1 |
| 5 s | 4 / 20 | 0 |
| 2 s | 0 / 20 | 0 |
| 1 s | 3 / 20 | 2 |

No control run had a single zero-commit second at any timeout, and none
lost throughput: the normal figures in section 6 are within the usual
run-to-run spread at every level.

---

## 11. Findings

1. **A leader failure stops commits for exactly one impeachment timeout at
   a time.** The longest zero-commit stretch equals the timeout at all
   four settings and all four baselines, and the first rotation is logged
   one timeout after the failure, to the second, in 141 of the 143
   recovered runs (the other 2 had already rotated seconds after start,
   before the failure).
2. **Shortening the timeout shortens the outage one for one.** 11 s of no
   commits at 11 s, 5 s at 5 s, 2 s at 2 s, 1 s at 1 s; total zero time
   at B3/B4 fell from ~21 s to ~2 s.
3. **Shortening the timeout does not change the throughput reached
   afterwards.** Across 11, 5, 2 and 1 s the after figure stayed at
   -11 to -14% of normal at B1, -8 to -13% at B3 (apart from one thin
   cell), -11 to -16% at B4, and +6 to +9% at B2.
4. **Crash and freeze were indistinguishable** in every cell, at every
   timeout, in throughput, latency and outage length.
5. **A follower failure caused no outage at any timeout.** In all 160
   follower-failure runs, no run failed to recover; throughput was within
   a few per cent of normal at B1, B3 and B4.
6. **B2 ran faster than normal after every failure, at every timeout:**
   +6 to +9% after a leader failure and +17 to +22% after a follower
   failure, with latency falling from ~13.4 ms to ~11.2-12.6 ms. B2 is
   the only baseline that does this. **No cause is established** (section
   12).
7. **17 of 160 leader-failure runs never recovered**, at every timeout
   (4, 7, 3, 3), with no trend across timeouts. They logged 15-41
   rotations against the usual 3 or 6 and settled on a different replica.
   **No cause is established.**
8. **Recovery is to a lower level, not to the previous one.** In 69 of
   143 recovered leader-failure runs throughput came back to within 10%
   of its own before value inside the 40 s window; in the other 74 it did
   not, and the after window in section 6 is what it settled at.
9. **Short timeouts did not disturb normal operation.** Of 20 no-failure
   controls per level, 1 / 4 / 0 / 3 logged any leader change, none had a
   single zero-commit second, and normal throughput at each timeout is
   within the usual run-to-run spread of the others.
10. **Most recovered runs rotated past the first surviving replica.** 87
    of 143 settled on replica 2 and 49 on replica 1 (6 settled on replica
    3, 1 split); 87 runs logged 6 rotate lines and 46 logged 3. Three
    replicas survive, so 3 lines is one rotation step and 6 is two. At B3
    and B4 that second step coincides with a second outage of the same
    length as the first. **No cause is established.**

---

## 12. Open questions

Recorded, with no mechanism proposed for any of them:

- **Why B2 is faster after a failure.** It holds for leader and follower
  failure, crash and freeze, and all four timeouts -- 20 of 20 B2 failure
  cells. Data to look at: per-replica CPU from `compute-*.jsonl`,
  per-second commits and latency, and the replica logs of the B2 runs.
- **Why 17 leader-failure runs never recovered**, and why they cluster at
  B3 and B4 crash.
- **Why the replicas usually rotate twice**, and why the second rotation
  costs a second outage at B3 and B4 but not at B1 and B2.
- **Why throughput settles below normal** after a leader failure at B1,
  B3 and B4 but not at B2.

---

## 13. Data

| file | what |
|---|---|
| `results/stage_l_results.csv` | Stage L, 100 runs, 11 s |
| `results/stage_lt_results.csv` | Stage LT, 300 runs, 5 / 2 / 1 s |
| `results/stage_l_analysis.txt` | full Stage L analysis, all five sections |
| `results/stage_lt5_analysis.txt`, `stage_lt2_analysis.txt`, `stage_lt1_analysis.txt` | the same at each shorter timeout |
| `analyse_stage_l.py` | the analysis; takes a run-id prefix (`L`, `LT5`, `LT2`, `LT1`) |
| `make_stage_l_csv.py`, `make_stage_lt_csv.py` | the sweep definitions |
| `benchmark/fail_inject.sh` | the injector |

Per-run evidence kept on the runs' host under `results/run_logs/<run id>/`:
`failure-replica-<i>.json` (the injection), `compute-*.jsonl` (command
lines, including `--imp-timeout`), the gzipped replica logs (pacemaker
lines) and the client logs (per-second commits and latency).
