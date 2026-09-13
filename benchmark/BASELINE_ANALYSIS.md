# Baseline characterisation — block_size, max_async, clients, threads, SmallBank

All numbers here were produced on the corrected measurement path
(commit `b622edc`). Every throughput or latency figure from before that
commit is void; see `INVESTIGATION_RECORD.md` for why.

Reservation: CloudLab Utah Exp-3, `d6515`. 4 replicas (node1 = fixed
proposer), 1 dedicated client host (node4, 64 cores), node5 as
orchestrator. 60s runs. Stages A-H ran with no injected network
latency; Stage N (section 12) injects it.

Totals: 1,445 runs across fifteen sweeps (Stages A-H, N, O, P, Q, R, the
section 8 re-run and the `rr` shakedown). Stage F lost 7 rows to a full
orchestrator disk; they were re-run. 20 Stage F parses failed for the
same reason and were re-parsed from intact logs. Stage G logged two
transient orchestrator SSH errors: one status-poll connection and one
pre-run cleanup that succeeded on retry. Both rows completed, and each
matched its sibling reps. Stages N, O, P, Q, R and the `rr` shakedown ran
without errors. No other run errors or parse failures. Separately from
errors, 29 runs stalled (section 13).

---

## 1. How to read these numbers: rep spread

Every configuration was run 3 times with identical settings. **Rep
spread** is `(max - min) / mean` over those repeats. It measures how
much the *same* configuration disagrees with itself, and it is the
resolution floor: a difference between two configurations that is
smaller than the spread of those configurations cannot be
distinguished from run-to-run variation.

Two real examples from Stage D3:

    bs=400  c=4  ma=4000    reps [281,757, 282,228, 282,500]  spread   0.3%
    bs=3200 c=8  ma=64000   reps [ 96,707, 298,717, 391,505]  spread 112.4%

The first cell's mean of 282,162 is a reliable number. The second
cell's mean of 262,310 is not: the gap between its highest and lowest
run is larger than its own average, and a fourth run is not predicted
by it. Where a cell is flagged as unreliable below, this is what is
meant — the arithmetic mean is correct, but it does not describe a
repeatable measurement.

Distribution of rep spread over the 87 Stage D3 cells: **median 3.8%,
p90 15.1%, max 112.4%**. Most of the surface is tight; a tail of nine
cells is not.

> **Correction (section 13).** Both runs pulling the second example down
> were **stalled runs**: commits stopped early and the run sat idle, which
> the throughput formula could not see. With stalled runs excluded, that
> cell's one clean run is 391,505, and the D3 spread distribution is
> **median 3.3%, p90 9.7%, max 30.6%**, with 5 cells above 15% instead of 9.

### 1b. Comparing two configurations at 7 reps

The rep-spread rule above (a difference must exceed the spread of the
cells compared) was used for every 3-rep comparison in Stages A-E. It
is not used for 7-rep verdicts, because the spread is a range, and the
range of a sample widens as samples are added. Measured directly: B3 at
its baseline settings had a spread of **3.0% over 3 reps and 9.8% over
7**. Under that rule, adding reps makes a difference *harder* to
confirm, and 3-rep and 7-rep verdicts are not comparable.

Stage F verdicts therefore use an exact two-sided Mann-Whitney rank
test. It pools the 14 runs of the two cells and counts, over all 3,432
ways of dividing them into two groups of 7, how often the division is
at least as lopsided as the one measured. That fraction is `p`. Stage F
made 13 comparisons, so a comparison is **confirmed only at
p < 0.05 / 13 = 0.0038**. Both the range-rule and rank-test results are
printed by `analyse_stage_f.py`.

Throughout sections 9 and 10, **median** is the middle value of the
reps of a cell, and latency figures are medians over reps of each run's
mean, p95 and p99 commit latency.

---

## 2. Headline result

**Peak measured: 459,342 tps** at `block_size=3200, clients=8,
max_async=4000`, mean latency 69.6 ms, rep spread 1.3%. That is at 90%
writes, the write ratio of the whole Stage D3 grid. At the same
configuration with 10% writes, Stage F measured **492,320 tps** at
65.0 ms (7-rep median, section 9.4).

That is **5.0x** the best single-client figure ever recorded here
(90,770). Stages A, B and C measured a single client across 41 cells,
`max_async` spanning 512x and `block_size` 16x, and never exceeded
90,770 tps. The apparent plateau at ~90k was a property of running one
client process, not of the system.

> **Later measurements (sections 13.6 and 14).** At 90% writes, the highest
> throughputs measured since are 481,140 tps at 66.6 ms (bs6400 / 8
> clients / `max_async` 4,000, section 14.2) and a 485,201 tps median at
> 33.0 ms (bs3200 / 16 clients / `max_async` 1,000, section 13.6, with a
> 34.5% spread). The baselines are unchanged.

---

## 2b. Baselines

These four are the throughput/latency frontier of the Stage D3 grid: no
other cell has both higher throughput and lower latency. Medians, 7
reps where re-run, 3 otherwise.

| | block_size | clients | max_async | tps | latency | spread |
|---|---|---|---|---|---|---|
| **B1** lowest latency | 200 | 2 | 1,000 | 167,191 | 12.0 ms | 3.8% |
| **B2** mid | 800 | 4 | 1,000 | 310,922 | 12.9 ms | 4.6% |
| **B3** recommended | 1600 | 8 | 1,000 | **446,133** | **18.0 ms** | **0.9%** |
| **B4** max throughput | 3200 | 8 | 4,000 | 459,963 | 69.5 ms | 1.3% |

> **Correction (section 13.4).** "No other cell has both higher throughput
> and lower latency" holds only among cells with rep spread <= 15%. Without
> that filter, bs3200 / 16 clients / `max_async` 1,000 (7-rep median
> 480,905 tps at 33.4 ms, spread 30.7%) has both. Its spread is not from
> stalled runs: it had none in Stage D3 or the section 8 re-run, and its
> low runs ran the full minute.
>
> **Resolved (section 13.6): B4 is retained.** That cell is recorded as a
> measured lower-latency alternative, not a baseline.

These four were selected from Stage D3, which ran only at threads=4,
`skew`=0.1, `mtx`=0.9. Stage F re-measured each at those settings over 7
reps: B1 165,125 tps / 12.1 ms, B2 301,718 / 13.3 ms, B3 444,759 /
18.0 ms, B4 459,790 / 69.6 ms. The thread count and write ratio that
measured best at each baseline are in section 10.

**Every frontier cell sits at `max_async = 1,000` except B4** -- the
lowest level tested. Raising `max_async` past that costs latency without
adding throughput.

B3 carries the tightest rep spread of any cell in the dataset (0.9%).
B4 buys 3.1% more throughput than B3 for 3.9x the latency.

Best throughput per latency band, restricted to cells with spread <=15%
and no collapsed run:

| band | config | tps | latency |
|---|---|---|---|
| <25 ms | bs1600 / c8 / ma1000 | 446,133 | 18.0 |
| 25-50 ms | bs1600 / c16 / ma1000 | 435,609 | 35.8 |
| 50-100 ms | bs3200 / c8 / ma4000 | 459,963 | 69.5 |
| 100-200 ms | bs3200 / c16 / ma4000 | 416,446 | 153.1 |
| 200+ ms | bs3200 / c8 / ma16000 | 405,707 | 273.6 |

> **Correction (section 13).** Two of these cells contained a stalled run.
> Excluded: 25-50 ms becomes 440,813 at 36.3 ms, and 200+ ms becomes
> 403,308 at 285.1 ms. The cell chosen in each band is unchanged.

Throughput varies 405k-460k across the bands while latency spans 18 ms
to 274 ms.

A pattern in the frontier, recorded as an observation with no mechanism
established: block size and client count rise together -- 200/2, 800/4,
1600/8, 3200/16 -- with throughput tracking their product.

---

## 3. What each parameter does

### 3.1 Parameters with no resolvable effect

Measured in Stage A at `bs=200, max_async=2000, threads=4`, 3 reps,
against a median rep spread of 4.5%:

| parameter | levels tested | separation |
|---|---|---|
| `sb_users` | 1e3, 1e6, 1e7 | 0.8% |
| threads (`nworker`/`repnworker`/`clinworker`) | 2, 4, 8, 16 | 1.8% |
| `sb_prob_choose_mtx` (write ratio) | 0.1, 0.5, 0.9 | 2.2% |

All three moved throughput less than repeating the same configuration
did.

**This bounds the effect; it does not establish absence of one.** Two
limits apply. First, 3 reps against a 4.5% spread cannot resolve
effects below roughly 4-5%. Second, each was varied at one operating
point only — `bs=200, ma=2000, threads=4`, single client, no injected
latency. Their behaviour elsewhere is untested.

`sb_skew_factor` (0.1, 0.5, 0.9) gave an 8.3% separation,
non-monotonic, against a 9.3% worst-case spread — not resolvable
either way.

**Superseded at the baselines.** Stages E and F re-measured threads,
skew and write ratio at B1-B4 (section 9). There, threads have a
confirmed effect at B3 and write ratio a confirmed effect at B2. The
Stage A bounds above hold only for the single-client point they were
measured at.

### 3.2 `block_size`

Single-client, `block_size` never raised throughput. Stage B varied it
independently of `max_async` across six columns; every column was flat
or negative: -1.8, -3.0, -6.7, -1.2, -1.6, -6.2%.

With multiple clients it does. At `max_async=4000`:

| block_size | 1 client | 4 clients | 8 clients |
|---|---|---|---|
| 200 | 86,673 | 187,227 | 180,991 |
| 800 | 81,190 | 328,967 | 350,334 |
| 3200 | — | 328,093 | **459,342** |

At 1 client the column is flat. At 8 clients, `bs=3200` is 2.5x
`bs=200`.

### 3.3 `max_async`

Stage B: gains are confined to the low end. At `bs=100`, throughput
rose 18.7% from `ma=500` to `ma=32,000`, but 15.6 of those points came
below `ma=4000`. At `bs=1600` the whole row was flat (-0.1%).

Stage C extended to 256,000. An **8x increase beyond 32,000 produced
no gain** at any block size: -4.6, -1.9, -4.6, -2.2%. The Stage B and
Stage C overlap cells at `ma=32,000` agreed within +/-1.4%.

### 3.4 Client count

| clients | bs=200, ma=4000 | bs=800, ma=8000 |
|---|---|---|
| 1 | 91,138 | 87,429 |
| 2 | 174,669 | 172,102 |
| 4 | 177,001 | **329,642** |
| 8 | 169,903 | 328,448 |
| 16 | 176,160 | — |

Means of 3 runs, Stage MC; no run stalled (section 13).

Both rows roughly double from 1 to 2 clients. `bs=200` then flattens;
`bs=800` continues to 4 clients and then flattens. The saturation
point differs by block size.

Client-host CPU: one client process drew ~163% of 6400% available
(64 cores). Peak observed across the multi-client sweep was 1,435%.
At 16 clients that is below 16 x 163%; per-process CPU fell. **No
explanation established.**

---

## 4. The surface (Stage D3)

87 legal cells, `block_size` x `clients` x `max_async`, 3 reps, 261
runs. Cells require `clients x max_async >= 5 x block_size` (see
section 6). Other parameters pinned at threads=4, `sb_users`=1e6,
`mtx`=0.9, `skew`=0.1.

### tps at max_async = 1,000 per client

    bs \ c        1         2         4         8        16
    200      81,221   165,513   198,443   185,142   186,878
    400           .   159,772   299,210   294,124   274,123
    800           .         .   308,783   398,364   361,614
    1600          .         .         .   447,053   425,107
    3200          .         .         .         .   438,340

### tps at max_async = 4,000 per client

    bs \ c        1         2         4         8        16
    200      86,673   170,473   187,227   180,991   175,191
    400      85,617   166,967   282,162   255,526   255,897
    800      81,190   171,742   328,967   350,334   329,398
    1600          .   167,891   339,476   408,037   379,780
    3200          .         .   328,093   459,342   420,392

### tps at max_async = 16,000 per client

    bs \ c        1         2         4         8        16
    200      93,680   172,981   174,719   174,726   169,549
    400      85,342   173,116   257,479   248,269   244,542
    800      87,003   165,706   334,422   326,180   308,311
    1600     84,218   171,928   331,454   373,732   366,499
    3200     87,478   174,976   349,503   413,660   379,093

### tps at max_async = 64,000 per client

    bs \ c        1         2         4         8        16
    200      84,796   165,004   171,563   167,972   166,095
    400      89,096   161,235   245,851   239,951   238,558
    800      84,888   166,468   329,547   307,600   275,316
    1600     87,625   175,891   337,985   308,526   354,829
    3200     86,389   169,166   354,788   262,310   372,251

### Top cells

| bs | clients | max_async | tps | lat ms | spread |
|---|---|---|---|---|---|
| 3200 | 8 | 4,000 | **459,342** | 69.6 | 1.3% |
| 1600 | 8 | 1,000 | 447,053 | 17.9 | 0.9% |
| 3200 | 16 | 1,000 | 438,340 | 35.1 | **30.6%** |
| 1600 | 16 | 1,000 | 425,107 | 35.0 | **12.3%** |
| 3200 | 16 | 4,000 | 420,392 | 151.7 | 3.0% |
| 3200 | 8 | 16,000 | 413,660 | 253.8 | 8.1% |
| 1600 | 8 | 4,000 | 408,037 | 78.3 | 4.3% |
| 800 | 8 | 1,000 | 398,364 | 20.1 | 1.1% |

Two of the top cells carry spreads of 30.6% and 12.3% and are not
reliable point estimates.

---

## 5. Edge check — which axes are still rising

Rule: for each axis, compare the top level against the level below it
**at identical other coordinates**. If the gain exceeds the rep spread
of the two cells compared, that edge has not saturated *at those
coordinates*. Applied per slice rather than to the grid average,
because saturation was already observed to depend on location
(section 3.4).

| axis | comparison | result |
|---|---|---|
| `block_size` | 3200 vs 1600 | **4 rising / 10 flat** |
| `clients` | 16 vs 8 | 0 rising / 19 flat |
| `max_async` | 64,000 vs 16,000 | 1 rising / 24 flat |

`block_size` is still rising at:

    (8 clients, ma=4000)    +12.6%  (spread 4.3%)
    (16 clients, ma=4000)   +10.7%  (spread 6.0%)
    (8 clients, ma=16000)   +10.7%  (spread 8.1%)
    (16 clients, ma=64000)   +4.9%  (spread 3.3%)

**Implication: extend `block_size` to 6400, at high client counts with
modest `max_async`. `clients` and `max_async` do not warrant
extension** on this data.

> **Correction (section 13).** With stalled runs excluded, `block_size`
> is rising at **6 slices, not 4**; (8 clients, `ma`=64,000) and
> (16 clients, `ma`=16,000) are added. `clients` (0/19) and `max_async`
> (1/24) are unchanged.

**Done in Stages G and H (section 11).** 6400 raised throughput at some
high-client slices, confirmed at 7 reps at 16 clients / `ma`=4,000
(+5.8%). No 6400 configuration displaced a baseline.

### Qualification on the `clients` verdict

The largest observed 16-vs-8 gain was **+41.9%**, at `bs=3200,
ma=64,000`, yet the rule classified it flat:

     8 clients: [ 96,707, 298,717, 391,505]  mean 262,310  spread 112.4%
    16 clients: [367,750, 373,573, 375,430]  mean 372,251  spread   2.1%

The 16-client cell is tight. The 8-client cell is the noisiest in the
sweep, and its mean is dragged down by a single run of 96,707 — its
other two runs bracket the 16-client result. The comparison is
therefore **unusable rather than proven flat**: a 42% difference cannot
be resolved by a measurement that varies by 112%.

The other 18 client comparisons were flat on tighter data.

**Resolved by re-run (7 reps, section 8).** That 8-client cell's median
is 393,547 with a spread of 7.6%; its old 3-rep mean of 262,310 had been
pulled down by the single 96,707 run. Recomputed on medians, 16 clients
versus 8 gives **-5.1% against a 7.6% spread -> flat**. The apparent
+41.9% was entirely an artifact of that one run. The `clients` verdict
now rests on clean data.

---

## 6. Constraints established

**`clients x max_async >= ~5 x block_size`.** `src/consensus.cpp`
commits a block only once three certified blocks sit directly above it.
Measured single-client at `block_size=200`: `max_async=400` produced 2
proposals and 0 commits; `max_async=600` produced 3 and 0;
`max_async=1000` committed 27,536 blocks. Configurations below this
ratio stall with no commits and return no metrics.

Every `max_async=400` result from before this was identified is void —
those runs only proceeded because a since-fixed client bug returned
acknowledgements without commits.

**`sb_skew_factor` must lie strictly in (0, 1).**
`cpp_random_distributions/zipfian_int_distribution.h` asserts
`theta > 0.0 && theta < 1.0`; Release builds define `NDEBUG`, so 0
would not fail loudly.

**`block_size` is honoured exactly.** Verified from replica protocol
logs: `ncmds` equalled the configured value in every block across
~28,000 blocks, a single distinct value per run.

---

## 7. Open — no explanation established

1. What sets the throughput levels observed. No mechanism has been
   measured for the peak, for the shape of the surface, or for why
   several of the highest cells occur at `max_async=1000`.
2. Why `block_size` raises latency but not throughput at 1 client,
   while raising both at higher client counts.
3. Why per-process client CPU falls at 16 clients (1,435% observed
   against 16 x 163% expected).
4. Why nine cells exhibit rep spreads above 15%, up to 112.4%, while
   the median is 3.8%.
   *Correction (section 13): with stalled runs excluded, five cells
   exceed 15%, at most 30.6%.*
5. What causes the collapsed runs described in section 8 -- individual
   repetitions landing at a fraction of the other runs of the same
   configuration, in cells that are otherwise tight. More repetitions
   exposed more of them rather than reducing them. None occurred in
   Stages E and F: across 187 runs the lowest run was 0.93x the median
   of its cell. They reappeared in Stage G (6 of 216 runs) and Stage H
   (1 of 28), every one at 16 clients (section 11.5).
6. Why 2 threads costs 8.2% throughput at B3, while no thread effect was
   detected at B1, B2 or B4 (3 reps there; section 9.1). In Stage G it
   cost 14-23% in some configurations and nothing in others (section
   11.3).
7. The latency observations in section 11.5: the two latency groups at
   16 clients / `ma`=16,000, mean latency below median at 4 clients /
   `ma`=16,000, and single runs at half the latency of their siblings.

---

## 8. Re-run of the nine high-variance cells (7 reps)

63 runs, 0 errors. Medians against the original 3-rep means:

| cell | old mean | old spread | new median | new spread | median vs old |
|---|---|---|---|---|---|
| bs200 c2 ma64000 | 165,004 | 16.7% | 173,922 | 6.4% | +5.4% |
| bs200 c8 ma1000 | 185,142 | 18.0% | 194,406 | **2.0%** | +5.0% |
| bs400 c2 ma64000 | 161,235 | 24.7% | 166,951 | 11.9% | +3.5% |
| bs400 c8 ma4000 | 255,526 | 15.1% | 263,036 | 15.9% | +2.9% |
| bs800 c16 ma64000 | 275,316 | 29.9% | 304,300 | **86.9%** | +10.5% |
| bs1600 c8 ma64000 | 308,526 | 43.6% | 355,921 | **52.1%** | +15.4% |
| bs3200 c8 ma64000 | 262,310 | 112.4% | 393,547 | **7.6%** | **+50.0%** |
| bs3200 c16 ma1000 | 438,340 | 30.6% | 480,905 | 30.7% | +9.7% |
| bs3200 c16 ma16000 | 379,093 | 15.7% | 396,260 | 34.1% | +4.5% |

**Every median came in above its old mean**, by 2.9% to 50.0%. The
original 3-rep grid understated these nine cells.

**The variance is not broad noise -- it is occasional collapsed runs.**
The raw reps show most runs clustering tightly with one or two far
below:

    bs800 c16 ma64000:  [ 73,351, 301,526, 303,642, 304,300,
                          304,584, 304,807, 309,473]
    bs1600 c8 ma64000:  [190,489, 309,593, 344,635, 355,921,
                          356,841, 358,076, 359,773]
    bs3200 c16 ma16000: [284,748, 387,012, 395,381, 396,260,
                          399,048, 402,890, 415,517]

In the first, six runs fall within 2.6% of each other and one is a
quarter of the rest. Three cells got *worse* on spread at 7 reps
(86.9%, 52.1%, 34.1%) because more reps exposed more collapses rather
than averaging them away.

Consequence: the **median** is the correct statistic for these cells.

> **Correction (section 13.3).** "Collapsed runs" were two different things.
> Of the three examples above, the 190,489 and 284,748 runs were **stalled
> runs**: their commits stopped after 11.9 s and 0.8 s. The 73,351 run is a
> **full-length low run**: it committed for the whole 62.3 s at a low rate.
> Excluding stalled runs, bs1600 c8 ma64000 spreads 4.3% (not 52.1%) and
> bs3200 c16 ma16000 spreads 7.1% (not 34.1%). bs800 c16 ma64000 had no
> stalled run and keeps its 86.9%.
No cause for the collapses is established. They occur at
`max_async=64,000` in two of the three worst cases, which is a statement
about where they were observed, not a mechanism.

---

## 9. Threads, skew and write ratio at the baselines (Stages E and F)

**Stage E:** 32 configs x 3 reps = 96 runs. At each baseline, one
factor at a time was varied away from threads=4, `skew`=0.1, `mtx`=0.9:
threads 2/4/8/16, skew 0.1/0.5/0.9, `mtx` 0.1/0.5/0.9. `mtx` is the
probability that a transaction is a modifying one, so 0.1 = 10% writes
and 0.9 = 90% writes. Verdicts by the rep-spread rule (section 1).

**Stage F:** 13 configs x 7 reps = 91 runs. It covered every comparison
Stage E found resolvable, plus B4 write ratio. Verdicts by the rank test
(section 1b).

### 9.1 Threads

Stage E, tps median of 3 reps, `skew`=0.1, `mtx`=0.9:

| | 2 | 4 | 8 | 16 | separation vs worst spread |
|---|---|---|---|---|---|
| B1 | 167,832 | 163,305 | 165,343 | 167,143 | 2.7% vs 5.1% -- not resolvable |
| B2 | 316,446 | 304,673 | 315,449 | 304,996 | 3.8% vs 6.5% -- not resolvable |
| B3 | 405,067 | 441,427 | 441,296 | 438,750 | 8.4% vs 6.4% -- resolvable |
| B4 | 457,039 | 462,033 | 456,388 | 460,776 | 1.2% vs 10.3% -- not resolvable |

Stage F, B3, 7 reps each:

| threads | runs (tps, sorted) | median | mean lat | p95 | p99 |
|---|---|---|---|---|---|
| 2 | 392,181 398,332 401,017 408,146 409,193 409,575 413,105 | 408,146 | 19.6 | 22.4 | 25.0 |
| 4 | 416,915 431,922 432,474 444,759 446,757 449,159 460,137 | 444,759 | 18.0 | 21.5 | 26.0 |
| 8 | 430,104 434,606 435,502 440,369 440,552 446,972 451,924 | 440,369 | 18.2 | 21.7 | 27.1 |

Rank test: 2 vs 4 p = 0.0006, 2 vs 8 p = 0.0006 -- **confirmed**; no
run at 2 threads reached the lowest run at 4 or 8. 4 vs 8 p = 1.00.

**Finding:** at B3, 2 threads gives 8.2% lower throughput and 1.6 ms
higher mean latency than 4. 4 and 8 are indistinguishable, and 16
matched them in Stage E. At B1, B2 and B4, no thread effect was
detected over 2-16. Those three were measured at 3 reps only; this is
not a demonstration that no effect exists there.

### 9.2 Write ratio

tps median, threads=4, `skew`=0.1:

| | Stage E: 10% / 50% / 90% writes | Stage F: 10% / 50% / 90% writes |
|---|---|---|
| B1 | 173,801 / 169,479 / 163,305 | 171,070 / 168,766 / 165,125 |
| B2 | 322,705 / 299,811 / 304,673 | 320,475 / 311,710 / 301,718 |
| B3 | 446,900 / 442,503 / 441,427 | not re-run |
| B4 | 477,501 / 483,766 / 462,033 | 492,320 / 471,657 / 459,790 |

Stage F latency, 10% -> 90% writes: B1 mean 11.7 -> 12.1 ms, B2
12.5 -> 13.3 ms, B4 65.0 -> 69.6 ms (p95 72.5 -> 76.2, p99
86.2 -> 93.1).

Stage F rank tests, 10% vs 90% writes: B1 p = 0.053, **B2 p = 0.0023
(confirmed)**, B4 p = 0.011. At B4, 5 of the 7 runs at 90% writes fall
below every run at 10% writes; the remaining two (480,156 and 498,825)
fall inside the 10% range.

**Finding:** at B1, B2 and B4, the 10%-write configuration had the
higher median throughput in all six comparisons across both stages, by
3.3-7.1%, with lower mean latency in every Stage F case. This is
confirmed at B2 only: +6.2% throughput, -0.8 ms mean latency. At B1 and
B4 the difference does not clear the confirmation threshold. At B3 no
difference was resolved (1.2% separation against an 8.7% spread,
3 reps).

B2's Stage E ordering was non-monotonic (50% below 90%). At 7 reps it
is monotonic: 320,475 > 311,710 > 301,718.

> **Correction (section 13).** Two of B4's seven 90%-write runs in Stage F
> were stalled runs (the 480,156 and 498,825 runs). Excluded, B4 10% vs 90%
> writes is **492,320 vs 458,388, p = 0.0025 -- confirmed**. So the
> write-ratio effect is confirmed at **B2 and B4**. In Stage E, B4's write
> ratio becomes resolvable too (4.8% separation against a 4.4% spread).

### 9.3 Skew

No skew comparison was resolvable at any baseline. Stage E separations:
B1 4.1% vs 7.6%, B2 2.0% vs 10.0%, B4 1.3% vs 8.3%. B3 cleared the
rule by half a point in Stage E (+3.1%, 3.9% vs 3.4%). In Stage F it
measured +1.3% (444,759 vs 450,539), rank test p = 0.13 -- **not
confirmed**.

### 9.4 Stage E against Stage F

All 13 Stage F medians fall within +/-4.0% of the Stage E value for
the same configuration. The single largest Stage E figure, 483,766 tps
(B4, 50% writes), measured 471,657 over 7 reps. The highest Stage F
cell is B4 at 10% writes: **492,320 tps, 65.0 ms mean latency**.

---

## 10. Best-measured thread count and write ratio per baseline

Selection rule: for each baseline, take the level with the highest
median throughput. Where no level is resolvably better, keep threads=4,
the level with the most runs (7 in Stage F) at every baseline. The
**basis** column states which of these applies.

| | config | threads | write ratio | tps | mean lat | p95 | p99 | basis |
|---|---|---|---|---|---|---|---|---|
| **B1** | bs200 c2 ma1000 | 4 | 10% | 171,070 | 11.7 | 14.1 | 15.8 | threads: no effect detected. 10% writes: highest median in both stages, not confirmed (p = 0.053) |
| **B2** | bs800 c4 ma1000 | 4 | 10% | 320,475 | 12.5 | 14.7 | 17.4 | threads: no effect detected. 10% writes: **confirmed** (p = 0.0023) |
| **B3** | bs1600 c8 ma1000 | 4 (or 8) | 10% | 446,900 | 17.9 | 21.6 | 26.2 | threads: **2 confirmed worse**, 4 = 8. Write ratio: no difference resolved; 10% highest median, 3 reps only |
| **B4** | bs3200 c8 ma4000 | 4 | 10% | 492,320 | 65.0 | 72.5 | 86.2 | threads: no effect detected. 10% writes: highest median in both stages, not confirmed (p = 0.011) |

B1, B2 and B4 figures are Stage F 7-rep medians. B3's is a Stage E 3-rep
median, because B3 at 10% writes was not in Stage F. B3 at 90% writes,
7 reps: 444,759 tps, 18.0 / 21.5 / 26.0 ms.

In the data behind this table (Stage F for B1, B2, B4; Stage E for B3),
the 10%-write row was also the lowest in mean latency among the write
ratios measured at every baseline. The one exception anywhere is Stage E
at B4, where 50% writes measured 66.1 ms against 67.0 ms. Throughput and latency
did not trade off along this axis.

**Scope.** The four baselines were selected in Stage D3 at 90% writes.
Whether the same four cells form the throughput/latency frontier at 10%
writes is untested.

### 10b. Adopted settings

Decision: **threads = 4 and 90% writes (`mtx` = 0.9) at all four
baselines**, with `skew` = 0.1 and `sb_users` = 1e6 unchanged. 10%
writes measured faster, but it was not adopted, because:

- write ratio defines the workload being benchmarked; it is not a
  system setting;
- 0.9 is the default in `hotstuff_app.cpp`, `hotstuff_client.cpp` and
  the harness `config.py`;
- every Stage D3 figure, and the frontier the baselines were selected
  from, is at 0.9. The frontier at 0.1 is untested.

Adopted baselines, Stage F 7-rep medians:

| | block_size | clients | max_async | threads | writes | tps | mean lat | p95 | p99 |
|---|---|---|---|---|---|---|---|---|---|
| **B1** | 200 | 2 | 1,000 | 4 | 90% | 165,125 | 12.1 | 14.4 | 16.2 |
| **B2** | 800 | 4 | 1,000 | 4 | 90% | 301,718 | 13.3 | 15.5 | 17.3 |
| **B3** | 1600 | 8 | 1,000 | 4 | 90% | 444,759 | 18.0 | 21.5 | 26.0 |
| **B4** | 3200 | 8 | 4,000 | 4 | 90% | 459,790 | 69.6 | 76.2 | 93.1 |

These are the settings future experiments, including the
network-latency re-run, start from.

> **Correction (section 13).** B4's 90%-write cell above includes two
> stalled runs. Its 5 clean runs give **458,388 tps, 69.8 ms mean, p95
> 75.4, p99 90.3** (all-run figures: 459,790 / 69.6 / 76.2 / 93.1). B1, B2
> and B3 had no stalled runs in any stage. Across Stages E-H, B4's
> configuration stalled in 8 runs.

---

## 11. Block size extension to 6400 (Stages G and H)

**Stage G:** `block_size` 3200/6400 x clients 4/8/16 x `max_async`
1,000/4,000/16,000 x threads 2/4/8 x writes 10%/90%, skew 0.1. Only
cells with `clients x max_async >= 5 x block_size` were run: 7 at 3200
and 5 at 6400. At 6400, `max_async`=1,000 is illegal at every client
count tested. 72 configs x 3 reps = 216 runs, in rep-major order,
shuffled with a fixed seed. Verdicts by the rep-spread rule (section 1).

**Stage H:** 7-rep check of the two Stage G results worth confirming.
4 cells x 7 reps = 28 runs at the adopted settings (threads 4, 90%
writes). Verdicts by the rank test; four tests, so confirmed at
p < 0.05 / 4 = 0.0125.

### 11.1 6400 against 3200

Stage G, 30 pairs at identical clients, `max_async`, threads and write
ratio:

| result | pairs | where |
|---|---|---|
| 6400 higher | 11 | only at 8 and 16 clients, +4.4% to +11.8% |
| 6400 lower | 2 | 8 clients, `ma`=4,000, 2 threads: -14.3%, -8.7% |
| not resolvable | 17 | including all 6 pairs at 4 clients |

> **Correction (section 13).** Excluding stalled runs: **13 higher, 2
> lower, 15 not resolvable**. The two added are 16 clients / `ma`=16,000
> at 4 threads / 90% writes, and 8 threads / 10% writes. In Stage H, 6400's
> lower latency at 16 clients / `ma`=4,000 becomes **confirmed**: 143.1 vs
> 151.2 ms, p = 0.0012.

At the adopted settings (threads 4, 90% writes), Stage G medians:

| clients / `max_async` | bs3200 | bs6400 | change | mean latency 3200 -> 6400 |
|---|---|---|---|---|
| 4 / 16,000 | 359,856 | 349,405 | -2.9%, not resolvable | 107.9 -> 178.5 ms |
| 8 / 4,000 | 474,923 | 477,340 | +0.5%, not resolvable | 67.3 -> 67.1 ms |
| 8 / 16,000 | 421,071 | 444,945 | +5.7%, not resolvable | 303.5 -> 274.6 ms |
| 16 / 4,000 | 415,681 | 454,309 | **+9.3%, resolvable** | 153.4 -> 140.6 ms |
| 16 / 16,000 | 413,330 | 428,238 | +3.6%, not resolvable | 429.8 -> 502.0 ms |

Stage H, 16 clients / `ma`=4,000, 7 reps:

| | runs (tps, sorted) | median | mean lat | p99 |
|---|---|---|---|---|
| bs6400 | 431,705 439,829 443,125 446,653 454,408 457,068 457,989 | **446,653** | 143.1 | 150.9 |
| bs3200 | 404,370 411,180 420,945 422,144 422,207 423,522 424,730 | 422,144 | 151.0 | 168.9 |

Throughput +5.8%, p = 0.0006 -- **confirmed**. Every 6400 run exceeded
every 3200 run. Mean latency 143.1 vs 151.0 ms, p = 0.026 -- not
confirmed.

**Finding:** at 16 clients / `ma`=4,000, 6400 gives 5.8% more
throughput than 3200. B4, measured in the same stage, has both higher
throughput and lower latency than that configuration: 461,222 tps at
69.3 ms against 446,653 at 143.1 ms. At the adopted settings, no 6400
configuration in Stage G exceeded the highest 3200 configuration
(section 11.2).

### 11.2 bs3200 / 16 clients / `ma`=1,000 against B4

Stage G ranked this configuration highest at the adopted settings:
482,211 tps at 33.3 ms, runs 474,820 / 482,211 / 491,391 (spread 3.4%),
against B4 at 474,923 and 67.3 ms. Stage H, 7 reps:

| | runs (tps / mean latency ms, sorted) | median |
|---|---|---|
| bs3200 c16 ma1000 | 82,600/211.1  377,778/37.2  407,147/35.2  443,671/50.2  476,782/33.7  487,397/32.7  499,719/32.1 | 443,671 / 35.2 ms |
| B4: bs3200 c8 ma4000 | 453,545/70.5  453,786/70.5  456,595/70.0  461,222/69.3  461,438/69.3  470,468/68.0  500,229/61.5 | 461,222 / 69.3 ms |

Throughput -3.8%, p = 0.46 -- not confirmed. Mean latency 35.2 vs
69.3 ms, p = 0.026 -- not confirmed. Six of its 7 runs had lower
latency (32.1-50.2 ms) than every B4 run (61.5-70.5 ms); the seventh
collapsed to 82,600 tps at 211.1 ms.

**Finding:** the Stage G result did not hold at 7 reps.

> **Correction (section 13.4) -- this finding is reversed.** Two of the
> candidate's seven Stage H runs were stalled runs, including its reported
> median (443,671, whose commits stopped after 0.5 s). One of B4's was too
> (500,229). On clean runs:
>
> | | clean runs | tps median | mean latency |
> |---|---|---|---|
> | bs3200 / 16 clients / `ma` 1,000 | 5 of 7 | 476,782 | **33.7 ms** |
> | B4: bs3200 / 8 clients / `ma` 4,000 | 6 of 7 | 458,909 | 69.7 ms |
> | rank test | | p = 0.66, not different | **p = 0.0043, confirmed** |
>
> **The candidate delivers the same throughput at half B4's latency.** It
> stalled in 2 of 7 runs against B4's 1 of 7, and its clean runs range
> 377,778-499,719. **Re-measured on the fixed window in Stage R (section
> 13.6); B4 retained.**
>
> The original text follows.

Excluding the collapsed run, its throughput ranged 377,778-499,719. That matches its
earlier record: a 30.6% spread in Stage D3 and 30.7% in the section 8
re-run. **B4 is retained.** B4's Stage H median is within 0.3% of its
Stage F median (459,790 at 69.6 ms).

### 11.3 Threads and write ratio in Stage G (3 reps)

**Threads.** 2 threads measured far lower in some configurations:

- bs3200 / 16 clients / `ma`=1,000, 90% writes: 371,442 against 482,211
  at 4 threads (-23%). The runs at each thread count are within 3.8%
  of each other. The range rule did not resolve this because the
  8-thread cell of the same comparison contains a collapsed run.
- bs6400 / 8 clients / `ma`=4,000: -17.4% (10% writes) and -14.3% (90%
  writes) against 4 threads. Both resolvable.

In others it did not: at bs3200 / 8 clients / `ma`=4,000 / 10% writes,
2 threads measured highest (501,998; not resolvable). The 4- and
8-thread medians were within 5.3% of each other in all 24 cells.

> **Correction (section 13).** The -23% at bs3200 / 16 clients / `ma`=1,000
> was not resolvable only because a stalled run sat in its 8-thread cell.
> Excluding it, 2 threads is **resolvably lower at both write ratios**:
> 380,935 vs 536,975 (-29.1%, 10% writes) and 371,442 vs 482,211 (-23.0%,
> 90% writes). At bs6400 / 16 clients / `ma`=16,000 / 10% writes, the
> thread comparison is no longer resolvable.

**Write ratio.** In every one of the 35 comparisons where neither median
is itself a collapsed run, 10% writes measured higher than 90%, by
+1.0% to +12.4%. 16 of the 35 are resolvable. This extends section 9.2
to every Stage G configuration; the adopted setting remains 90%
(section 10b).

> **Correction (section 13).** Excluding stalled runs, all **36**
> comparisons have 10% writes higher, and **19** are resolvable.

### 11.4 Overlap with Stage D3

6 of the 7 bs3200 cells at the adopted settings came within +/-3.8% of
their Stage D3 medians. The seventh, 16 clients / `ma`=16,000, came in at
+7.9%; its Stage G spread is 12.8%.

### 11.5 Variance and latency observations -- no explanation established

> **Correction (section 13.3).** Several items below were stalled runs:
> - of the 6 Stage G "collapsed runs", **3 were stalled runs** (244,051;
>   247,447; 173,657) and **3 were full-length low runs** (84,180; 63,459;
>   74,517). Stage G had 5 further stalled runs that looked normal or high.
> - the Stage H "collapsed run" (82,600) was a stalled run.
> - at 16 clients / `ma`=16,000, **2 of the 4 runs in the lower latency
>   group were stalled runs** (225.1 and 225.5 ms). The remaining two ran
>   the full minute (295.7 and 353.8 ms).
> - the Stage H run at 74.5 ms was a stalled run. The Stage G run at
>   63.4 ms was not: it ran the full 62.9 s.
> - the observation that mean latency is below median at 4 clients /
>   `ma`=16,000 involves no stalled runs.
>
> The original text follows.

- **Collapsed runs, Stage G: 6 of 216, all at 16 clients.**
  - `ma`=1,000, 8 threads: 244,051 tps (10% writes) and 247,447 (90%),
    at 378.3 and 446.5 ms, against siblings of 478k-539k at ~30-34 ms.
  - `ma`=16,000, 2 threads: 84,180 (bs3200, 10% writes), 173,657
    (bs6400, 90%), and **two of the three runs** of bs3200 / 90% writes
    (63,459 and 74,517, against 390,383). That cell's median is itself
    a collapsed run.
- **Collapsed runs, Stage H: 1 of 28**, bs3200 / 16 clients / `ma`=1,000
  (82,600 tps).
- **At 16 clients / `ma`=16,000, mean latency falls into two groups.**
  Of the 32 runs that did not collapse, 4 measured 225-354 ms and 28
  measured 413-644 ms.
- **At 4 clients / `ma`=16,000, mean latency is below median latency**
  in 18 of 18 bs3200 runs and 14 of 18 bs6400 runs.
- **Single runs at about half their siblings' latency, at normal
  throughput:** bs3200 / 8 clients / `ma`=16,000 / 8 threads / 10% writes
  measured 63.4 ms against 285.5 and 297.0 ms in its other two runs. In
  Stage H, one bs3200 / 16 clients / `ma`=4,000 run measured 74.5 ms
  against 150.1-157.7 ms in the other six.

---

## 12. Injected network latency at the baselines (Stage N)

4 scenarios x 4 delays x B1-B4, plus a 0 ms control per baseline, 5 reps
= 340 runs, 0 errors. Every run at threads 4, 90% writes, skew 0.1, the
adopted settings. Delay per replica via `tc`; a link gets
max(lat_a, lat_b) in both directions, so a delayed link's round trip is
2 x its delay value. Client traffic is never shaped. Replica 1 is the
fixed proposer.

    lead   leader delayed            lat_node1 = d           6 of 12 links
    f1     one follower delayed      lat_node0 = d           6 of 12 links
    f2     two followers delayed     lat_node0,2 = d        10 of 12 links
    f3     three followers delayed   lat_node0,2,3 = d      12 of 12 links

"All four nodes delayed" is not a distinct case: under the max rule every
link has a follower end, so it produces f3's rules exactly.

This supersedes `NETEM_ANALYSIS.md` and `NETEM_FACTORIAL_ANALYSIS.md`
entirely: both predate the measurement fix and ran single-client.

### 12.1 The delay is verified in every run

Each run pings, after `tc` is applied and before the replicas boot, from
every replica to every other replica and from the client host to every
replica, and stores the result as `rtt.json` beside its logs
(`RemoteBench._probe_rtt`). Over all 340 runs, 5,440 measured pairs:

| expected added round trip | pairs | measured median | measured range |
|---|---|---|---|
| 0 ms (undelayed and client links) | 2,720 | 0.10 ms | 0.06 - 0.24 |
| 100 ms | 680 | 100.14 ms | 100.11 - 100.19 |
| 200 ms | 680 | 200.14 ms | 200.11 - 200.18 |
| 300 ms | 680 | 300.14 ms | 300.12 - 300.16 |
| 400 ms | 680 | 400.14 ms | 400.11 - 400.16 |

0% packet loss throughout. No run had a failing or missing probe. The
earlier netem work could not establish this, which is why its
conclusions were retracted.

### 12.2 One delayed follower

Medians of 5 reps, tps / mean latency ms:

| | control | 50 ms | 100 ms | 150 ms | 200 ms | verdict |
|---|---|---|---|---|---|---|
| **B1** | 165,681 / 12.1 | 160,911 / 12.0 | 164,695 / 12.1 | 162,796 / 12.3 | 165,285 / 12.1 | -0.2% to -2.9%, not resolvable |
| **B2** | 303,619 / 13.2 | 310,474 / 12.9 | 305,494 / 13.1 | 305,572 / 13.1 | 313,500 / 12.8 | +0.6% to +3.3%, not resolvable |
| **B3** | 446,626 / 17.9 | 397,534 / 20.2 | 412,624 / 19.4 | 408,408 / 19.6 | 404,071 / 19.8 | **-7.6% to -11.0%, resolvable** |
| **B4** | 455,198 / 70.3 | 404,197 / 79.1 | 401,783 / 79.6 | 410,183 / 78.0 | 403,543 / 79.3 | **-9.9% to -11.7%, resolvable** |

**Finding:** one delayed follower costs nothing resolvable at B1 and B2,
and 8-12% throughput with 8-13% higher mean latency at B3 and B4. **The
cost does not grow with the delay**: at B3 and B4, 200 ms costs the same
as 50 ms, within the spread.

### 12.3 Delayed leader, two followers, three followers

Medians of 5 reps, tps / mean latency ms. Every cell below is resolvable
against its control:

| | scenario | 50 ms | 100 ms | 150 ms | 200 ms |
|---|---|---|---|---|---|
| **B1** | leader | 1,971 / 1,018 | 993 / 2,008 | 665 / 2,991 | 501 / 3,967 |
| | two followers | 1,975 / 1,017 | 996 / 2,004 | 665 / 2,984 | 501 / 3,954 |
| | three followers | 1,971 / 1,018 | 993 / 2,008 | 665 / 2,991 | 501 / 3,968 |
| **B2** | leader | 7,789 / 516 | 3,978 / 1,019 | 2,653 / 1,525 | 1,998 / 2,033 |
| | two followers | 7,813 / 515 | 3,994 / 1,017 | 2,667 / 1,521 | 1,998 / 2,026 |
| | three followers | 7,795 / 516 | 3,979 / 1,019 | 2,653 / 1,525 | 1,998 / 2,033 |
| **B3** | leader | 15,402 / 522 | 7,867 / 1,027 | 5,287 / 1,537 | 4,067 / 2,050 |
| | two followers | 15,441 / 521 | 7,871 / 1,025 | 5,290 / 1,532 | 3,986 / 2,043 |
| | three followers | 15,406 / 521 | 7,867 / 1,027 | 5,286 / 1,537 | 4,067 / 2,051 |
| **B4** | leader | 30,022 / 1,068 | 15,727 / 2,077 | 10,753 / 3,092 | 8,197 / 4,113 |
| | two followers | 30,248 / 1,062 | 15,800 / 2,072 | 10,808 / 3,084 | 8,234 / 4,099 |
| | three followers | 30,445 / 1,068 | 15,717 / 2,079 | 10,749 / 3,093 | 8,196 / 4,114 |

As a share of each baseline's control: **-93.3% to -99.7%**. Mean latency
rises from 12-70 ms to 0.5-4.1 s.

**Findings:**

1. **The three scenarios measure the same**, at every baseline and every
   delay, although they delay 6, 10 and 12 of the 12 replica links.
   Largest disagreement among the three at any point: 2.0% (B3, 200 ms).
2. **Doubling the delay halves throughput and doubles latency**, across
   all four baselines and all three scenarios.
3. **In all 48 collapsed cells, median throughput x median latency equals
   `clients x max_async` within 5.5%** (B1 -1.0% to +0.4%, B2 +0.4% to
   +1.6%, B3 +0.4% to +4.2%, B4 +0.2% to +5.5%). This is arithmetic on
   the measurements; it says nothing about what sets the latency.
4. The collapsed level tracks the baseline's in-flight budget: at 200 ms,
   B1 (2,000 outstanding) 501 tps, B2 (4,000) 1,998, B3 (8,000) 4,067,
   B4 (32,000) 8,197.

### 12.4 Where the boundary falls

With 4 replicas, f = 1 and a quorum is 3. With one replica delayed, three
undelayed replicas remain, which is a full quorum containing no delayed
member; with two delayed, every 3-replica quorum contains a delayed
member. The measured boundary -- f1 absorbed, f2 collapsed -- coincides
with that arithmetic.

**This is a correspondence between the measurements and the
configuration's quorum arithmetic, not a demonstrated mechanism.** The
test that would establish it needs 7 replicas (f = 2, quorum 5), where
two delayed replicas still leave a clean quorum and three do not. That
needs 9 nodes; the current reservation has 6.

### 12.5 Variance

The tightest data in the project. **No collapsed runs:** the lowest run
in any of the 68 cells is 0.954x its cell median. Delayed cells carry
spreads of 0.0-1.5%; the four controls, 2.7-6.5%.

### 12.6 Not established

- What sets the throughput and latency levels in the collapsed regime.
- Why one delayed follower costs 8-12% at B3 and B4 and nothing
  resolvable at B1 and B2.
- Why that cost is flat in the delay from 50 to 200 ms.
- Whether batching or in-flight load changes the collapsed level. Stage N
  cannot attribute it, because its baselines vary `block_size`, clients
  and `max_async` together. **Measured in section 14:** `block_size`
  changes it and `max_async` does not.

---

## 13. Stalled runs: audit and corrections

### 13.1 What was wrong

Throughput was computed as commits / (last commit - first commit). That
window cannot see idle time after the last commit. **In 29 of 1,392 runs,
commits stopped early** -- in some within 0.01 s -- and the run sat idle
for the rest of its 60 s, yet still printed a plausible, sometimes high,
throughput.

Example, Stage G `bs3200_c16_ma1000_t8_mtx0.1_r1`: 10 of 16 clients each
committed exactly 1,000 commands (their `max_async`) within 0.01 s, the
other 6 committed nothing, and there were no further commits in 60 s.
Reported: 244,051 tps. Commits over the run: 9,600, about 160 tps.

A smoke run of B4 on the fixed measurement (13.5) stalled on its first
attempt: all 8 clients' last commit fell within 0.68 s of starting. The
old formula printed 463,433 tps for it.

**Why commits stop is not established.** Replica logs of the stalled B4
run in Stage E contain no warnings or errors.

### 13.2 How runs were classified

A run is **stalled** when its first-to-last-commit window plus its mean
latency is under 55 s. A short window that slow commits cannot explain
means commits stopped. Old runs cannot be re-measured over a fixed window
(their raw client logs were truncated, then pruned), but every run can be
classified from its results CSV.

`audit_stalls.py` re-runs each stage's comparisons with its original
method twice: with every run, which **reproduces every published figure
exactly** (e.g. D3's 4/10 edge check, Stage F's p = 0.0111, all four
Stage H p-values), and with stalled runs excluded. Output:
`results/stall_audit.txt`.

| stages | stalled runs |
|---|---|
| A, B, C, MC (section 3.4), N, O | 0 |
| D3 | 8, in 6 cells |
| section 8 re-run | 3, in 2 cells |
| E | 4, all at B4 |
| F | 2, both at B4 |
| G | 8, in 8 cells |
| H | 4, in 3 cells (including B4) |
| P | 0 (see below) |

**B1, B2 and B3 never stalled in any stage.** B4's configuration stalled
in 8 runs across Stages E-H.

**Misclassified by this rule:** the 3 Stage P runs at block_size 800 /
leader 200 ms, first counted as stalled. Re-measured over 180 s on the
fixed window (Stage Q, section 14), that cell commits steadily, with no
zero-commit second, at 1,984 tps. Its mean latency is **62.4 s, longer
than a 60 s run**, which is what shrank its window. The rule cannot tell
a stall from a latency that exceeds the run. It does not affect D3-H,
where every flagged run has a mean latency under 3 s.

### 13.3 Two kinds of low run

What sections 8 and 11.5 called "collapsed runs" were two things:

- **stalled runs**, whose commits stop early. The reported tps is
  meaningless: it can land low, plausible or high.
- **full-length low runs**, which commit for the whole minute at a low
  rate. These are real measurements. Four are documented: 73,351 (re-run
  bs800 c16 ma64000), 63,459 and 74,517 (G bs3200 c16 ma16000 t2 90%
  writes), and 84,180 (G bs3200 c16 ma16000 t2 10% writes).

Of 11 collapsed runs listed in this document, 7 were stalled runs and 4
were full-length low runs.

### 13.4 Conclusions that change

| where | as published | with stalled runs excluded |
|---|---|---|
| 1 | D3 spread median 3.8%, p90 15.1%, max 112.4%, 9 cells > 15% | median 3.3%, p90 9.7%, max 30.6%, 5 cells > 15% |
| 2b | frontier: B1-B4 | unchanged with the <= 15% spread filter; without it, bs3200/c16/ma1000 (480,905 @ 33.4 ms) dominates B4. Unaffected by stalls. |
| 5 | block_size rising at 4 slices | rising at 6 |
| 8 | variance = occasional collapsed runs | stalled runs plus full-length low runs (13.3) |
| 9.2 / F | write ratio confirmed at B2 only | confirmed at **B2 and B4** (B4 p = 0.0025) |
| 10b | B4 459,790 tps, 69.6 ms | 458,388 tps, 69.8 ms (5 clean runs) |
| 11.1 / G | 6400 higher in 11 of 30 pairs | 13 of 30 |
| 11.1 / H | 6400 latency lower not confirmed | confirmed, p = 0.0012 |
| **11.2 / H** | **bs3200/c16/ma1000 did not beat B4; B4 retained** | **same throughput (p = 0.66) at half the latency (33.7 vs 69.7 ms, p = 0.0043); stalled 2/7 vs B4 1/7. Re-measured in Stage R (13.6): B4 retained, candidate noted.** |
| 11.3 / G | 2 threads at bs3200/c16/ma1000 not resolvable | resolvably lower at both write ratios (-29.1%, -23.0%) |
| 11.3 / G | write ratio: 10% higher in 35, 16 resolvable | 10% higher in all 36, 19 resolvable |
| 11.5 | four latency observations | two were stalled runs (see the note in 11.5) |

No conclusion from Stages A, B, C, N or O changes.

### 13.5 The fix

Commit `2c3224d`. At shutdown every client now emits, even with zero
commits:

- `[hotstuff steady]`: commits and latency inside a fixed window
  `[meas_warmup, run - meas_cooldown]`, plus first and last commit times;
- `[hotstuff buckets]`: commits per whole second since start.

The parser adds `tps_steady`, `latency_ms_mean_steady`,
`n_committed_steady`, `clients_committing`, `last_commit_s`,
`longest_zero_commit_s` and `stalled` (5 or more consecutive seconds with
zero commits across all clients). Existing fields are unchanged. Checked
on synthetic logs: a run committing for 1 s and then stopping reads
200,000 tps on the old formula, and 0 tps with `stalled` true on the new
one.

The smoke run of the Stage P cell block_size 800 / leader 100 ms (180 s)
showed commits arriving in **bursts**. Each client committed about 16,000
commands (its `max_async`) over roughly 4 s, then none for about 28 s,
repeating about every 32 s. Every command took 32.5 s: p50 and max were
within 6 ms of each other. Fixed-window throughput was 3,944 tps, against
6,205 on the old formula.

---

### 13.6 B4 against bs3200 / 16 clients / `max_async` 1,000 (Stage R)

Section 13.4 reopened this comparison. Stage R repeated it on the fixed
window: 10 runs each, interleaved, no delay, threads 4, 90% writes, skew
0.1, 60 s runs with a 10 s warm-up and 2 s cool-down. The verdicts were
fixed in advance: exact Mann-Whitney over non-stalled runs, on throughput
and on mean latency, each confirmed at p < 0.025.

| run | B4 (8 clients, `max_async` 4,000) | candidate (16 clients, `max_async` 1,000) |
|---|---|---|
| r1 | 451,260 / 70.9 ms | 505,544 / 31.6 ms |
| r2 | 454,003 / 70.5 ms | 410,258 / 35.1 ms |
| r3 | 440,794 / 72.6 ms | 357,217 / 38.5 ms |
| r4 | 462,337 / 69.1 ms | 516,400 / 31.0 ms |
| r5 | 460,549 / 69.5 ms | 502,810 / 31.8 ms |
| r6 | 452,225 / 70.8 ms | **stalled**: 0 tps, 50 s without a commit (old formula: 459,496) |
| r7 | 448,257 / 71.4 ms | 498,106 / 32.1 ms |
| r8 | 451,457 / 70.9 ms | 484,632 / 33.0 ms |
| r9 | 446,772 / 71.6 ms | 398,405 / 35.8 ms |
| r10 | 451,790 / 70.8 ms | 485,201 / 33.0 ms |
| stalled | 0 of 10 | 1 of 10 |
| clean median | **451,624 tps / 70.8 ms** | **485,201 tps / 33.0 ms** |
| spread | **4.8%** | **34.5%** |
| worst client p99 | 85.0-174.2 ms | 36.1-45.2 ms |

- **Throughput: not confirmed** (p = 0.24). Of the candidate's 9 clean
  runs, 6 exceed B4's highest and 3 fall below B4's lowest.
- **Latency: confirmed** (p = 0.00002). All 9 of the candidate's clean runs
  (31.0-38.5 ms) are below all 10 of B4's (69.1-72.6 ms).
- Stalls at these exact settings across Stages D3, the section 8 re-run,
  E, F, G, H and R: **candidate 3 of 30, B4 5 of 33**.

**Decision: B4 is retained as the baseline.** The candidate is recorded
here as a measured alternative with less than half B4's latency and the
same median throughput, but a 34.5% run-to-run throughput spread against
B4's 4.8%.

## 14. Batching and in-flight load under leader delay (Stages O, P, Q)

Section 12 found that the collapsed throughput tracks each baseline's
in-flight budget, but the baselines vary `block_size`, clients and
`max_async` together. These stages separate the two candidate knobs.
Every run: 8 clients, threads 4, 90% writes, skew 0.1, fixed proposer.
Conditions: no delay, leader (replica 1) delayed 100 ms, leader delayed
200 ms. Every run's injected delay verified from `rtt.json` (O 63/63,
P 54/54, Q 33/33).

| stage | design | runs |
|---|---|---|
| O | A: `block_size` 800-6400 at `max_async` 4,000 (32,000 outstanding); B: `max_async` 4,000-32,000 at `block_size` 3200 | 63, 60 s |
| P | `block_size` 800-25,600 at `max_async` 16,000 (128,000 outstanding) | 54, 60 s |
| Q | the 9 O/P cells with mean latency >= 14 s, plus 2 anchor cells | 33, 180 s |

### 14.1 Measurement

With mean latency of 14 s or more, a 60 s run's first-to-last-commit
window shrinks and its throughput is inflated -- by up to 4.6x in the
worst cell. Those 9 cells were re-measured in Stage Q: 180 s runs, fixed
window from 40 s to 2 s before the end (section 13.5), raw logs kept.

The anchor cells were measured cleanly by 60 s runs. They show the two
methods agree:

| anchor | 60 s, first-to-last | Q, fixed window | difference |
|---|---|---|---|
| bs3200 / ma4000 / leader 100 ms | 15,677 tps, 2.08 s | 15,453 tps, 2.07 s | -1.4% |
| bs6400 / ma16000 / leader 100 ms | 30,388 tps, 4.23 s | 29,953 tps, 4.28 s | -1.4% |

Below, cells marked **Q** are Stage Q medians; all others are the 60 s
medians. Differences under ~2% between a Q cell and a 60 s cell are within
the method difference. All 33 Q runs had spread 0.0-0.3% and none stalled.

Corrected slow cells, old against new:

| cell | published (60 s) | Q throughput | Q mean latency |
|---|---|---|---|
| O bs800 / ma4000 / 200 ms | 2,417 | 1,986 | 16.1 s |
| O bs3200 / ma16000 / 200 ms | 8,943 | 7,830 | 16.3 s |
| O bs3200 / ma32000 / 100 ms | 17,228 | 15,325 | 16.7 s |
| O bs3200 / ma32000 / 200 ms | 10,882 | 7,829 | 32.7 s |
| P bs800 / 100 ms | 6,205 | 3,939 | 32.5 s |
| P bs800 / 200 ms | 9,076 | 1,984 | 62.4 s |
| P bs1600 / 100 ms | 9,259 | 7,798 | 16.4 s |
| P bs1600 / 200 ms | 6,111 | 3,947 | 32.4 s |
| P bs3200 / 200 ms | 9,085 | 7,831 | 16.3 s |

### 14.2 `block_size` at fixed load

tps / mean latency, 8 clients x `max_async` 4,000 (Stage O):

| block_size | no delay | leader 100 ms | leader 200 ms |
|---|---|---|---|
| 800 | 349,827 / 91.2 ms | 4,215 / 7.68 s | **Q** 1,986 / 16.1 s |
| 1,600 | 412,231 / 77.0 ms | 7,850 / 4.01 s | 4,179 / 7.80 s |
| 3,200 | 459,225 / 69.6 ms | 15,677 / 2.08 s | 8,191 / 4.12 s |
| 6,400 | 481,140 / 66.6 ms | 30,411 / 1.08 s | 15,871 / 2.13 s |

8 clients x `max_async` 16,000 (Stage P):

| block_size | no delay | leader 100 ms | leader 200 ms |
|---|---|---|---|
| 800 | 325,119 / 376 ms | **Q** 3,939 / 32.5 s | **Q** 1,984 / 62.4 s |
| 1,600 | 384,297 / 282 ms | **Q** 7,798 / 16.4 s | **Q** 3,947 / 32.4 s |
| 3,200 | 428,225 / 256 ms | 15,862 / 7.94 s | **Q** 7,831 / 16.3 s |
| 6,400 | 435,085 / 288 ms | 30,388 / 4.23 s | 15,556 / 8.15 s |
| 12,800 | 455,382 / 281 ms | 58,178 / 2.28 s | 31,391 / 4.36 s |
| 25,600 | 467,040 / 275 ms | 104,333 / 1.27 s | 57,636 / 2.35 s |

Throughput ratio from each block size to the next:

| step | no delay (O / P) | leader 100 ms (O / P) | leader 200 ms (O / P) |
|---|---|---|---|
| 800 -> 1,600 | 1.18 / 1.18 | 1.86 / 1.98 | 2.10 / 1.99 |
| 1,600 -> 3,200 | 1.11 / 1.11 | 2.00 / 2.03 | 1.96 / 1.98 |
| 3,200 -> 6,400 | 1.05 / 1.02 | 1.94 / 1.92 | 1.94 / 1.99 |
| 6,400 -> 12,800 | - / 1.05 | - / 1.91 | - / 2.02 |
| 12,800 -> 25,600 | - / 1.03 | - / 1.79 | - / 1.84 |

**Findings:**

1. **Under leader delay, each doubling of `block_size` roughly doubles
   throughput and halves mean latency, at both loads.** From 800 to
   25,600 at 100 ms: 3,939 to 104,333 tps (26x), 32.5 s to 1.27 s. The
   step ratio falls to 1.79-1.84 at the last doubling.
2. **With no delay, the same shape appears at both loads:** +18%, +11%,
   then +2-5% per doubling from 3,200 up.
3. **No `block_size` restores normal service under delay.** The best
   delayed cell, 104,333 tps at 25,600 / 100 ms, is 22% of the same
   configuration's 467,040 tps with no delay.
4. At 90% writes, the highest no-delay throughput measured in this
   document is **481,140 tps at 66.6 ms** (bs6400 / 8 clients /
   `max_async` 4,000, 3 reps; Stage G measured the same cell at 477,340).

### 14.3 In-flight load at fixed `block_size`

tps / mean latency, `block_size` 3200, 8 clients (Stage O; **Q** where
re-measured):

| max_async | no delay | leader 100 ms | leader 200 ms |
|---|---|---|---|
| 4,000 | 459,225 / 69.6 ms | 15,677 / 2.08 s | 8,191 / 4.12 s |
| 8,000 | 415,623 / 153.7 ms | 16,145 / 4.10 s | 8,127 / 7.96 s |
| 16,000 | 414,527 / 257.2 ms | 15,852 / 7.94 s | **Q** 7,830 / 16.3 s |
| 32,000 | 401,480 / 374.4 ms | **Q** 15,325 / 16.7 s | **Q** 7,829 / 32.7 s |

**Findings:**

1. **Under leader delay, `max_async` does not change throughput.** Across
   8x the in-flight load, 100 ms stays within 15,325-16,145 tps and 200 ms
   within 7,829-8,191, with no consistent direction. **Latency doubles
   with each doubling of `max_async`.**
2. **With no delay, raising `max_async` costs throughput:** -12.6% from
   4,000 to 32,000, while mean latency rises 5.4x.
3. The same holds across stages on the fixed window. At `block_size` 3200
   and 200 ms: 7,830 tps (O, `max_async` 16,000), 7,829 (O, 32,000) and
   7,831 (P, 16,000). At 800 and 200 ms: 1,986 (O, 4,000) and 1,984 (P,
   16,000). An 8x difference in load changes throughput by under 0.2%.

### 14.4 Arithmetic on the delayed cells

Recorded as arithmetic on the measurements, not as a mechanism:

- In all 11 Stage Q cells, **throughput x mean latency equals
  clients x `max_async` within 0.2%**, except bs800 / 16,000 / 200 ms
  at -3.2%.
- **Blocks committed per second** (throughput / `block_size`) are
  4.68-4.92 at 100 ms and 2.45-2.48 at 200 ms in Stage Q, at every block
  size and load. These correspond to one block per injected round trip
  (5.0 and 2.5 per second), falling slightly as blocks grow. The 60 s
  commit counts show the same: at 100 ms, 304 blocks per run at block
  size 800, 292-295 at 3,200 and 244 at 25,600; at 200 ms, 151, 146-147
  and 130.
- In the smoke run of bs800 / 16,000 / 100 ms, commits arrived in bursts
  of about `max_async` per client every ~32 s, and every command took
  32.5 s (section 13.5).

### 14.5 Not established

- Why blocks per second under delay track the injected round trip.
- Why the per-doubling gain falls at the largest block sizes.
- Why raising `max_async` costs throughput with no delay.

---

## 15. Rotating pacemaker shakedown (`rr`)

B3 (bs1600 / 8 clients / `max_async` 1,000), 4 cases x 3 reps = 12 runs,
built with protocol logging on, so the pacemaker's rotation lines are in
the replica logs. Numbers are therefore compared with the logged
fixed-proposer case, not with unlogged runs.

| case | pacemaker | delayed | tps median | mean latency |
|---|---|---|---|---|
| `dummyctl` | fixed proposer | none | 433,220 | 18.5 ms |
| `rrctl` | `rr` | none | 430,815 | 18.6 ms |
| `rrlead200` | `rr` | replica 1, 200 ms | 395,604 | 20.3 ms |
| `rrfoll200` | `rr` | replica 0, 200 ms | 4,065 | 2,051.7 ms |

**Findings:**

1. `rr` with no delay matches the fixed proposer (-0.6%).
2. **`rr` never rotated.** Across all 9 `rr` runs, the replica logs
   contain zero "rotate to" lines. All four replicas log "stop rotation
   at 0". `rr` settles on **replica 0** at startup and stays there,
   including when replica 0 is delayed 200 ms.
3. Under `rr`, delaying replica 1 behaves like Stage N's one delayed
   follower (B3: 404,071 tps, 19.8 ms), and delaying replica 0 like its
   delayed leader (4,067 tps, 2,050.4 ms, within 0.05%).
4. Protocol logging: the logged fixed-proposer run measured 433,220 tps,
   against 446,626 for Stage N's unlogged B3 control -- 3.0% lower, from
   different sweeps.

In the code, `rr` rotates only when a timeout fires, and every commit
resets it (`on_consensus` in `include/hotstuff/liveness.h`;
`reset_imp_timer` in `examples/hotstuff_app.cpp`). **Forced rotation, by
tuning that timeout, was not measured and is not pursued** (section 16).

---

## 16. Pending

**Measured at 3 reps only:** thread count at B1, B2 and B4; write ratio
and skew at B3 other than the B3 skew comparison in 9.3; all Stage G
comparisons except the two re-tested in Stage H.

**Decided, not pursued: forced leader rotation.** The `rr` shakedown
found that `rr` settled on replica 0 and did not rotate once in 9 runs,
including with replica 0 delayed 200 ms. `rr` rotates only when a timeout
fires, and every commit resets it (`include/hotstuff/liveness.h`
`on_consensus`; `examples/hotstuff_app.cpp` `reset_imp_timer`). Forcing
rotation would mean tuning that timeout by hand. What that would do was
not measured. Re-running Stage N under `rr` as configured would reproduce
Stage N with the leader relabelled, so that sweep is dropped too.

**Planned after this document is closed, in order:**
1. reduced computational capacity on one node;
2. failure injection: the leader failing mid-run, then a follower.

---

## 17. Data

| file | contents |
|---|---|
| `results/stage_a_results.csv` | 45 runs, OFAT screen |
| `results/stage_b_results.csv` | 75 runs, bs x ma grid |
| `results/stage_c_results.csv` | 48 runs, ma extension to 256k |
| `results/stage_d3_results.csv` | 261 runs, bs x clients x ma |
| `results/stage_mc_results.csv` | 27 runs, client count (section 3.4, whose figures are means of 3) |
| `results/rerun_noisy_results.csv` | 63 runs, section 8 re-run |
| `results/stage_e_results.csv` | 96 runs, threads / skew / write ratio at B1-B4 |
| `results/stage_f_results.csv` | 91 runs, 7-rep confirmation of Stage E |
| `results/stage_g_results.csv` | 216 runs, block_size 6400 extension |
| `results/stage_h_results.csv` | 28 runs, 7-rep check of Stage G |
| `results/stage_n_results.csv` | 340 runs, injected network latency at B1-B4 |
| `results/stage_o_results.csv` | 63 runs, block_size and max_async under leader delay |
| `results/stage_p_results.csv` | 54 runs, block_size to 25,600 under leader delay |
| `results/stage_q_results.csv` | 33 runs, slow O/P cells on the fixed window (180 s) |
| `results/stage_r_results.csv` | 20 runs, B4 vs bs3200/c16/ma1000 on the fixed window |
| `results/stage_rr_results.csv` | 12 runs, `rr` pacemaker shakedown (protocol logging on) |
| `results/stall_audit.txt` | every stage's comparisons with and without stalled runs |
| `results/stage_g_analysis.txt`, `results/stage_h_analysis.txt`, `results/stage_n_analysis.txt`, `results/stage_{o,p,q,r,rr}_analysis.txt` | analysis output as run |
| `results/run_logs/<run_id>/rtt.json` | per-run measured round trips, every pair, since commit `e01221a` |
| `results/run_logs/` | per-run logs on node5, not in git. Since commit `d0666db`, raw client logs are replaced by `summaries.txt` once parsed |
| `../exp3_full_results.tgz` | pre-prune archive of every run log up to the first 20 Stage F runs, 5.25 GB, not in git |
| `analyse_stage_a.py` … `analyse_stage_rr.py`, `audit_stalls.py` | analysis scripts |
| `make_stage_*.py` | grid generators |
