# Baseline characterisation — block_size, max_async, clients, threads, SmallBank

All numbers here were produced on the corrected measurement path
(commit `b622edc`). Every throughput or latency figure from before that
commit is void; see `INVESTIGATION_RECORD.md` for why.

Reservation: CloudLab Utah Exp-3, `d6515`. 4 replicas (node1 = fixed
proposer), 1 dedicated client host (node4, 64 cores), node5 as
orchestrator. 60s runs, no injected network latency.

Totals: 429 runs across four sweeps, 0 run errors, 0 parse failures.

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

The other 18 client comparisons were flat on tighter data, so the
verdict probably holds, but it rests in part on one un-callable cell.

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

---

## 8. Pending

A re-run of the nine cells with rep spread above 15%, at 7 reps
instead of 3 (`rerun_noisy.csv`, 63 runs), to establish whether their
values are reproducible and whether the `clients` edge verdict in
section 5 survives. Results will land in
`results/rerun_noisy_results.csv`.

Not yet run: `block_size` extension to 6400 at 8 and 16 clients with
`max_async` 4,000-16,000, which is what section 5 indicates.

---

## 9. Data

| file | contents |
|---|---|
| `results/stage_a_results.csv` | 45 runs, OFAT screen |
| `results/stage_b_results.csv` | 75 runs, bs x ma grid |
| `results/stage_c_results.csv` | 48 runs, ma extension to 256k |
| `results/stage_d3_results.csv` | 261 runs, bs x clients x ma |
| `results/run_logs/` | per-run logs, 36 GB, not in git |
| `analyse_stage_a.py` … `analyse_stage_d3.py` | analysis scripts |
| `make_stage_*.py` | grid generators |
