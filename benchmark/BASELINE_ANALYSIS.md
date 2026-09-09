# Baseline characterisation — block_size, max_async, clients, threads, SmallBank

All numbers here were produced on the corrected measurement path
(commit `b622edc`). Every throughput or latency figure from before that
commit is void; see `INVESTIGATION_RECORD.md` for why.

Reservation: CloudLab Utah Exp-3, `d6515`. 4 replicas (node1 = fixed
proposer), 1 dedicated client host (node4, 64 cores), node5 as
orchestrator. 60s runs, no injected network latency.

Totals: 492 runs across five sweeps, 0 run errors, 0 parse failures.

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

---

## 2. Headline result

**Peak measured: 459,342 tps** at `block_size=3200, clients=8,
max_async=4000`, mean latency 69.6 ms, rep spread 1.3%.

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
   exposed more of them rather than reducing them.

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

## 9. Pending

**Stage E (running):** threads, `sb_skew_factor` and
`sb_prob_choose_mtx` re-tested at each of the four baselines in section
2b. Stage A bounded all three below ~4.5% but measured them only at
`bs=200, ma=2000`, single client, ~85k tps. The baselines run
167k-460k with 2-8 clients, so that bound does not carry over.
32 configs x 3 reps = 96 runs, `stage_e.csv`, results to
`results/stage_e_results.csv`.

**Not yet run:** `block_size` extension to 6400 at 8 and 16 clients with
`max_async` 4,000-16,000, which is what section 5 indicates.

**Carry-over:** the network-latency work predates the measurement fix
and was run entirely single-client, in the regime now known to be
client-limited. It will need re-running at one or more of the section 2b
baselines.

---

## 10. Data

| file | contents |
|---|---|
| `results/stage_a_results.csv` | 45 runs, OFAT screen |
| `results/stage_b_results.csv` | 75 runs, bs x ma grid |
| `results/stage_c_results.csv` | 48 runs, ma extension to 256k |
| `results/stage_d3_results.csv` | 261 runs, bs x clients x ma |
| `results/run_logs/` | per-run logs, 36 GB, not in git |
| `analyse_stage_a.py` … `analyse_stage_d3.py` | analysis scripts |
| `make_stage_*.py` | grid generators |
