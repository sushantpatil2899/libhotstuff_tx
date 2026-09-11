# Baseline characterisation — block_size, max_async, clients, threads, SmallBank

All numbers here were produced on the corrected measurement path
(commit `b622edc`). Every throughput or latency figure from before that
commit is void; see `INVESTIGATION_RECORD.md` for why.

Reservation: CloudLab Utah Exp-3, `d6515`. 4 replicas (node1 = fixed
proposer), 1 dedicated client host (node4, 64 cores), node5 as
orchestrator. 60s runs, no injected network latency.

Totals: 923 runs across nine sweeps. Stage F lost 7 rows to a full
orchestrator disk; they were re-run. 20 Stage F parses failed for the
same reason and were re-parsed from intact logs. Stage G logged two
transient orchestrator SSH errors: one status-poll connection and one
pre-run cleanup that succeeded on retry. Both rows completed, and each
matched its sibling reps. No other run errors or parse failures.

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

**Finding:** the Stage G result did not hold at 7 reps. Excluding the
collapsed run, its throughput ranged 377,778-499,719. That matches its
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

**Write ratio.** In every one of the 35 comparisons where neither median
is itself a collapsed run, 10% writes measured higher than 90%, by
+1.0% to +12.4%. 16 of the 35 are resolvable. This extends section 9.2
to every Stage G configuration; the adopted setting remains 90%
(section 10b).

### 11.4 Overlap with Stage D3

6 of the 7 bs3200 cells at the adopted settings came within +/-3.8% of
their Stage D3 medians. The seventh, 16 clients / `ma`=16,000, came in at
+7.9%; its Stage G spread is 12.8%.

### 11.5 Variance and latency observations -- no explanation established

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

## 12. Pending

**Carry-over:** the network-latency work predates the measurement fix
and was run entirely single-client, in the regime now known to be
client-limited. It will need re-running at one or more of the section 2b
baselines.

**Measured at 3 reps only:** thread count at B1, B2 and B4; write ratio
and skew at B3 other than the B3 skew comparison in 9.3; all Stage G
comparisons except the two re-tested in Stage H.

---

## 13. Data

| file | contents |
|---|---|
| `results/stage_a_results.csv` | 45 runs, OFAT screen |
| `results/stage_b_results.csv` | 75 runs, bs x ma grid |
| `results/stage_c_results.csv` | 48 runs, ma extension to 256k |
| `results/stage_d3_results.csv` | 261 runs, bs x clients x ma |
| `results/rerun_noisy_results.csv` | 63 runs, section 8 re-run |
| `results/stage_e_results.csv` | 96 runs, threads / skew / write ratio at B1-B4 |
| `results/stage_f_results.csv` | 91 runs, 7-rep confirmation of Stage E |
| `results/stage_g_results.csv` | 216 runs, block_size 6400 extension |
| `results/stage_h_results.csv` | 28 runs, 7-rep check of Stage G |
| `results/stage_g_analysis.txt`, `results/stage_h_analysis.txt` | analysis output as run |
| `results/run_logs/` | per-run logs on node5, not in git. Since commit `d0666db`, raw client logs are replaced by `summaries.txt` once parsed |
| `../exp3_full_results.tgz` | pre-prune archive of every run log up to the first 20 Stage F runs, 5.25 GB, not in git |
| `analyse_stage_a.py` … `analyse_stage_h.py` | analysis scripts |
| `make_stage_*.py` | grid generators |
