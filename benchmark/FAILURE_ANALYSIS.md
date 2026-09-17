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

Totals: **454 runs** in three sweeps (Stage L 100, Stage LT 300, Stage M
54), 0 run errors, 0 parse failures.

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

## 12. How to read these throughput numbers

Added after the Stage LT results, from an audit of the measurement
itself. The audit found no error in the arithmetic, and two things that
change what the numbers mean.

### 12.1 The measurement is sound

| check | result |
|---|---|
| clients reporting in every run | 2/2, 4/4, 8/8; `clients_committing` matches |
| per-second histograms cover the whole after window | every run reaches T+83 or later; the window needs T+76 |
| client start stagger (buckets are placed by whole second) | median 0.23 s, maximum 0.35 s |
| window mean vs the run's own `tps_steady` | controls agree within 1% (B1 -0.1%, B2 +0.0%, B3 +0.5%, B4 -1.2%) |
| commit counting | a command is counted once, on the f+1'th `decision=1` reply, then erased; `decision=0` receipts are excluded |

The 15-23% gap between the after-window mean and `tps_steady` in
leader-failure runs is the outage, which `tps_steady` includes and the
after window excludes.

### 12.2 The load is fixed, so throughput and latency are one measurement

Each client keeps at most `max_async` requests outstanding and sends a new
one only when an old one returns. The offered load is therefore capped at
`clients x max_async`, and

    requests in flight = throughput x latency

holds in the data: in the no-failure controls the product is 1,999 /
3,999 / 7,998 / 31,999 against caps of 2,000 / 4,000 / 8,000 / 32,000.
Across all 80 cells of Stages L and LT it holds within 0.4% except where
section 13 applies.

So a throughput change at a fixed cap is a latency change restated. This
does **not** mean capacity was never measured: the `max_async` and
`block_size` sweeps of `BASELINE_ANALYSIS.md` section 4 raised the cap
directly, and throughput stopped rising -- the definition of saturation.
At B2's configuration (block 800, 4 clients):

| requests in flight | throughput |
|---|---|
| 4,000 | 308,783 |
| 16,000 | 328,967 |
| 64,000 | 334,422 |
| 256,000 | 329,547 |

64x the load bought 8%, then nothing. At B3's configuration it reverses:
447,053 at `max_async` 1,000 against 308,526 at 64,000.

Each baseline sits near the ceiling of its own configuration:

| | baseline here | best that configuration reached at any load | gap |
|---|---|---|---|
| B1 | 162,694 | 172,981 | 6% below |
| B2 | 300,438 | 334,422 | 10% below |
| B3 | 430,719 | 447,053 | 4% below |
| B4 | 434,083 | 459,342 | 5% below |

**B2 after a replica fails reaches 356,982 -- above the 334,422 that four
replicas reached at any load ever tested.** Its gain is therefore not the
system being given more work.

---

## 13. One block of work is lost when the leader fails

Requests in flight, measured per run as (commits in the after window) x
(their mean latency), then the cell median:

| | in flight after | cap | missing | as blocks |
|---|---|---|---|---|
| B1 leader freeze | 1,799 | 2,000 | 201 | **1.00** |
| B2 leader crash / freeze | 3,998 | 4,000 | 2 | 0.00 |
| B3 leader crash / freeze | 7,998 | 8,000 | 2 | 0.00 |
| B4 leader crash | 28,798 | 32,000 | 3,202 | **1.00** |

The shortfall is **exactly one block** wherever it occurs -- 200 at B1,
3,200 at B4 -- never a partial amount and never two. It holds at all four
timeouts:

| | 11 s | 5 s | 2 s | 1 s |
|---|---|---|---|---|
| B1 leader crash | 0 | 0 | 0 | 0 |
| B1 leader freeze | 1 block | 1 block | 1 block | 0 |
| B2, B3 (both arms) | 0 | 0 | 0 | 0 |
| B4 leader crash | 1 block | 1 block | 1 block | 1 block |
| B4 leader freeze | 0.5 | 1 block | 0 | 1 block |

It appears at the failure and stays flat for the rest of the run: at B4,
in flight reads 31,977 at T-20, 0 through the outage, then 28,807 at
T+10 and 28,793 at T+70.

**No follower-failure run and no control run, at any baseline or timeout,
lost anything** -- 160 follower-failure runs, all at the full cap.

Two facts bear on this:

- only the leader proposes blocks, so only a leader failure can destroy
  work that is in progress and held nowhere else;
- **the client never re-sends.** `examples/hotstuff_client.cpp` has no
  timer, no retry and no resend path: a command that does not collect
  f+1 `decision=1` replies stays in `waiting` for the rest of the run and
  its slot is never reused. (The replicas do support re-submission --
  `src/hotstuff.cpp` answers an already-pending hash with `decision=0` --
  but nothing ever uses it.)

**Consequence for the leader-failure figures in sections 5 and 6:** none,
as it turned out. Stage M ran healthy four-replica controls at exactly
this reduced load and they lost no throughput at all (section 15.1), so
the drop after a leader failure is the system, not the offered load. What
remains is that one block of client transactions is never committed and
never retried.

**Not established:** why B1 and B4 lose a block while B2 and B3 never do,
and why at B1 it happens on a freeze but not on a crash.

---

## 14. Where B2's extra time goes

B2 is the baseline that runs faster after a failure (finding 6). The gain
is a faster block pipeline, with blocks always full at 800 commands:

| B2 | blocks committed per second | time per block |
|---|---|---|
| before the failure | 372 | 2.59 ms |
| after follower 3 dies | 446 | 2.19 ms |

446 x 800 = 356,960, matching the 356,982 measured.

Splitting the leader's block cycle into three measured segments, from its
own log, puts the whole gain in one of them:

| baseline | window | quorum wait | "QC formed" (see 15.2) | next block | gap |
|---|---|---|---|---|---|
| B1 | before -> after | 0.98 -> 1.00 | 0.02 -> 0.02 | 0.16 -> 0.16 | 1.17 -> 1.18 |
| **B2** | before -> after | 1.58 -> 1.60 | **0.49 -> 0.02** | 0.53 -> 0.56 | **2.58 -> 2.19** |
| B3 | before -> after | 2.40 -> 2.49 | 0.03 -> 0.02 | 1.16 -> 1.20 | 3.66 -> 3.74 |
| B4 | before -> after | 4.53 -> 4.64 | 0.03 -> 0.03 | 2.76 -> 2.87 | 7.15 -> 7.60 |

All times in ms, medians over blocks then over runs. "Quorum wait" is
propose to the 2f+1'th vote for that block; "QC formed" is that vote to
the leader's "got QC" line; "next block" is that line to the next
propose.

B1, B3 and B4 spend 0.02-0.03 ms on the middle segment in every window.
**B2 spends 0.49 ms there with four replicas and 0.02 ms with three.**
The quorum wait barely moves, so the gain is not about waiting for votes.

Supporting measurements:

1. **Replica 3's vote always arrives last**, at every baseline: 1.43 vs
   0.97 ms (B1), 1.89 vs 1.53 (B2), 4.24 vs 2.34 (B3), 8.05 vs 4.27
   (B4), measured from the leader's propose. It is never part of the
   quorum, which is why removing it leaves the quorum wait unchanged.
2. **Nothing is CPU-saturated.** The leader's busiest thread runs at 67%
   of one core before and 75% after; replicas use 3-5 of 64 cores.
3. **The same per-block time appears in an earlier phase.** B2's
   configuration measured 308,783 tps in the Stage D3 grid, which is 2.59
   ms per block -- the same as the 2.52-2.59 ms measured here. Protocol
   logging was compiled out in every earlier stage, so the segment split
   cannot be checked there; the total can, and it matches.

**No cause is established** for the 0.45 ms.

---

## 15. Stage M -- what the lost block costs, and where B2's delay lives

54 runs, 18 configurations x 3 reps, 120 s each, protocol logging on, 0
errors. Four arms, never combined in one run. In the `map` arm follower 3
is killed at t = 40 s, so one run measures the same configuration with
four replicas (before) and three (after).

### 15.1 The lost block does not explain the leader-failure drop

A healthy four-replica system, no failure, run at exactly the load a
leader failure leaves behind:

| | requests in flight | throughput | latency |
|---|---|---|---|
| B4 normal (control, section 5) | 32,000 | 434,083 | 73.7 ms |
| **B4 healthy at the reduced load** | **28,799** | **439,438** | **65.5 ms** |
| B4 after a leader crash | 28,798 | 379,206 | 76.0 ms |
| B1 normal (control, section 5) | 2,000 | 162,694 | 12.3 ms |
| **B1 healthy at the reduced load** | **1,799** | **162,870** | **11.1 ms** |
| B1 after a leader freeze | 1,799 | 144,978 | 12.6 ms |

Taking 10% of the load away costs a healthy system nothing: B4 gives
439,438 against 434,083, B1 gives 162,870 against 162,694, both within
run-to-run spread, and latency falls as the queue shortens.

**So the throughput after a leader failure is not low because the clients
offer less work.** At the same 28,798 in flight, a healthy leader serves
439,438 and a replaced one serves 379,206 -- 60,000 tx/s apart. The
figures in sections 5 and 6 stand as measured: after a leader failure the
system itself is slower.

The lost block of section 13 remains real and unexplained, but it is a
correctness question -- one block of client transactions is never
committed and never retried -- not a measurement artefact.

### 15.2 What B2's delay is not

B2, four replicas, no failure, against its usual `repnworker` 4 and
`repburst` 1,000 (which measure 0.36 ms here):

| | throughput | quorum-to-QC |
|---|---|---|
| `repnworker` 1 | 299,592 | 0.36 ms |
| `repnworker` 2 | 313,752 | 0.35 ms |
| `repnworker` 8 | 303,634 | 0.39 ms |
| `repburst` 100 | 295,110 | 0.50 ms |
| `repburst` 10,000 | 311,695 | 0.32 ms |

Eight times the worker threads, and a hundredfold change in burst size,
leave it where it was. Blocks were full in every cell of the sweep --
median and minimum both equal to the configured block size, in 100% of
blocks.

> **Correction.** An earlier version of this section concluded from the
> full blocks that the delay "is not the leader waiting for enough
> commands to fill a block". The code does not support that inference.
> The leader proposes only once a full block of commands has arrived
> (`src/hotstuff.cpp`, `cmd_pending` handler: `beat()` is called when
> `cmd_pending_buffer.size() >= blk_size`), so blocks are full whether or
> not the leader waited for them. What the "got QC" line marks is the later
> of two events -- the previous block's QC, and a full block of commands
> being ready (`proposer_schedule_next` in
> `include/hotstuff/liveness.h`) -- and the segment called "QC formed"
> above cannot tell them apart. Stage MB logs the second event directly
> (section 15.5).

### 15.3 Where it appears

The delay is not a constant overhead; it is a wait on a share of blocks,
and that share tracks the configuration. Four replicas, before any
failure:

| configuration | clients | in flight | in flight / block | blocks delayed over 0.1 ms | median |
|---|---|---|---|---|---|
| bs400 c2 | 2 | 2,000 | 5 | **85.1%** | 0.84 ms |
| **bs800 c4 (B2)** | 4 | 4,000 | 5 | **74.0%** | 0.36 ms |
| bs1600 c8 (B3) | 8 | 8,000 | 5 | 34.7% | 0.03 ms |
| bs800 c4 ma2000 | 4 | 8,000 | 10 | 24.0% | 0.02 ms |
| bs800 c8 | 8 | 8,000 | 10 | 0.0% | 0.02 ms |
| bs200 c2 (B1), bs3200 c8 (B4) | | | 10 | ~0% | 0.02-0.03 ms |

More clients, or more outstanding work per block, reduces it. Removing a
replica reduces it too: 0.36 -> 0.02 ms at B2, 0.92 -> 0.42 ms at bs400
c2.

### 15.4 The configurations that gain from losing a replica

Throughput in the same run, four replicas then three:

| configuration | 4 replicas | 3 replicas | change |
|---|---|---|---|
| bs400 c2 | 158,392 | 207,521 | **+31.0%** |
| bs800 c4 (B2) | 314,600 | 348,600 | **+10.8%** |
| bs800 c4 ma2000 | 330,804 | 358,018 | +8.2% |
| bs800 c4 ma4000 | 328,517 | 347,158 | +5.7% |
| bs200 c2 (B1) | 166,724 | 169,366 | +1.6% |
| bs1600 c8 (B3) | 422,601 | 425,133 | +0.6% |
| bs400 c4 | 269,051 | 267,026 | -0.8% |
| bs400 c8 | 260,829 | 255,439 | -2.1% |
| bs800 c8 | 363,875 | 347,418 | -4.5% |
| bs1600 c8 ma2000 | 417,523 | 397,994 | -4.7% |
| bs3200 c8 ma4000 (B4) | 439,791 | 418,276 | -4.9% |

Every configuration that gains has 2 or 4 clients; every one that loses
has 8. The two largest gains, bs400 c2 and B2, are the two cells carrying
the largest quorum-to-QC delay. B2 is not unique after all -- it is the
second-worst case of a pattern, and bs400 c2 is a stronger one.

**No cause is established** for the delay, for its dependence on client
count, or for why removing a replica reduces it.

---

## 16. Open questions

Recorded, with no mechanism proposed for any of them:

- **What the quorum-to-QC delay is** (sections 14 and 15): a wait on a
  share of blocks, worst with few clients, unaffected by worker threads
  or burst size, and reduced by removing a replica. B2 is the
  second-worst case measured; bs400 c2 is worse.
- **Why the number of clients governs it**, when blocks are full in every
  configuration and no thread is saturated.
- **Why one block is lost at B1 and B4 but not B2 and B3** (section 13),
  and how much of the leader-failure throughput drop that accounts for.
- **Why 17 leader-failure runs never recovered**, and why they cluster at
  B3 and B4 crash.
- **Why the replicas usually rotate twice**, and why the second rotation
  costs a second outage at B3 and B4 but not at B1 and B2.
- **Why throughput settles below normal** after a leader failure at B1,
  B3 and B4 but not at B2 -- at B4 and at B1 under a freeze, part of this
  is the lost block of section 13, in a proportion not yet established.

---

## 17. Data

| file | what |
|---|---|
| `results/stage_l_results.csv` | Stage L, 100 runs, 11 s |
| `results/stage_lt_results.csv` | Stage LT, 300 runs, 5 / 2 / 1 s |
| `results/stage_l_analysis.txt` | full Stage L analysis, all five sections |
| `results/stage_lt5_analysis.txt`, `stage_lt2_analysis.txt`, `stage_lt1_analysis.txt` | the same at each shorter timeout |
| `analyse_stage_l.py` | the analysis; takes a run-id prefix (`L`, `LT5`, `LT2`, `LT1`) |
| `make_stage_l_csv.py`, `make_stage_lt_csv.py` | the sweep definitions |
| `benchmark/fail_inject.sh` | the injector |
| `results/stage_m_results.csv` | Stage M, 54 runs |
| `analyse_stage_m.py`, `make_stage_m_csv.py` | the Stage M analysis and sweep |
| `analyse_stage_l.py` sections 2-5 | the per-run figures behind sections 5-10 |

Per-run evidence kept on the runs' host under `results/run_logs/<run id>/`:
`failure-replica-<i>.json` (the injection), `compute-*.jsonl` (command
lines, including `--imp-timeout`), the gzipped replica logs (pacemaker
lines) and the client logs (per-second commits and latency).
