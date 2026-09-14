# Compute restriction -- fewer cores per replica

Phase 2 of the study. The measurement conventions and baselines are those of
`BASELINE_ANALYSIS.md`:

- throughput and latency are **fixed-window** figures (`tps_steady`,
  `latency_ms_mean_steady`), never the legacy first-to-last-commit `tps`
  (`BASELINE_ANALYSIS.md` section 13);
- **stalled runs** are counted per cell and excluded from medians;
- the injected condition is **verified in every run**, here from each
  replica's allowed-CPU list;
- baselines B1-B4 at threads 4, 90% writes, skew 0.1, fixed proposer
  (replica 1), no injected delay.

Reservation: CloudLab Utah Exp-3, `d6515` nodes (AMD EPYC 7452, 32 physical
cores / 64 hardware threads, 1 socket, 125 GB), expiring 2026-09-19.

Totals: 750 runs in two sweeps (Stage U 10, Stage K 740), 0 run errors,
0 parse failures.

**Only findings are recorded. No mechanism is proposed for any of them.**

---

## 1. What can be measured and restricted on these nodes

Checked on a replica host:

| capability | available |
|---|---|
| cgroups v2 with `cpuset` and `cpu` controllers | yes |
| per-host CPU pressure (`/proc/pressure/cpu`) | yes |
| `pidstat`, `perf`, `mpstat` | yes |
| RAPL package energy | yes; 49-50 W idle, stable over repeated 1 s readings |
| CPU frequency scaling | **no** (`/sys/.../cpufreq` absent) |
| `stress-ng` | not installed |

Logical CPUs 0-31 are distinct physical cores; 32-63 are their SMT
siblings (`lscpu -e`).

Knobs considered: fewer cores (tested here), a CPU-time quota (deferred),
slower cores (not possible, no cpufreq) and competing load (not tested).

---

## 2. Instrument: `benchmark/compute_sampler.py`

With `sample_compute=true`, a sampler runs as root on every replica and
client host, starting when the replicas boot. Once a second it records raw
cumulative counters as JSON lines: per tracked process, CPU ticks,
voluntary and involuntary context switches, RSS, allowed-CPU list, and
per-thread ticks and allowed-CPU lists; host `/proc/stat`; CPU pressure
totals; RAPL energy; and its own ticks. Rates are derived afterwards over
the steady window t = 15-55 s.

---

## 3. Stage U -- B3 unrestricted

5 sampled and 5 unsampled runs, interleaved, 60 s, no stalls.

**Sampler overhead.** Sampled median 441,448 tps at 18.1 ms (range
424,520-457,167); unsampled 438,678 tps at 18.2 ms (range 423,872-453,913).
The sampler itself used 0.016-0.022 cores per host.

Medians of the 5 sampled runs:

| | leader (replica 1) | follower 0 | follower 2 | follower 3 | client host |
|---|---|---|---|---|---|
| CPU used, cores | 4.63 | 4.49 | 4.50 | **5.48** | 11.29 |
| busiest thread, % of a core | 85 | 87 | 86 | 95 | 92 |
| threads above 5% / total | 8 / 30 | 7 / 30 | 8 / 30 | 9 / 30 | 16 / 32 |
| host CPU pressure | 1.87% | 1.94% | 2.06% | 1.16% | 0.70% |
| voluntary context switches /s | 31,050 | 35,621 | 36,480 | 12,245 | 29,954 |
| involuntary context switches /s | 1 | 2 | 3 | 2 | 9 |
| RSS | 4.2 GB | 4.2 GB | 4.2 GB | 4.6 GB | 1.8 GB |
| whole-host CPU, cores | 4.66 | 4.48 | 4.50 | 5.55 | 11.62 |
| package power (idle ~50 W) | 69.0 W | 70.2 W | 68.0 W | 58.2 W | 90.7 W |

Per-thread utilisation, % of one core, ranked (median by rank):

| host | threads above 1% |
|---|---|
| leader | 85 78 58 57 54 53 53 6 5 3 3 2 2 1 |
| follower 0 | 87 79 58 54 53 52 51 5 4 3 |
| follower 2 | 86 79 58 55 53 53 52 7 4 |
| follower 3 | 95 92 77 70 69 66 64 6 5 4 |
| client host | 92 92 92 91 91 90 90 89 52 52 51 51 51 50 50 49 |

**Findings:**

1. Each replica used 4.5-5.5 of its 64 logical CPUs, across 7-9 threads
   doing measurable work. The two busiest ran at 78-95% of a core.
2. **Follower 3 used the most CPU, in all 5 runs** (5.26-5.63 cores), with
   35-39% of the other replicas' voluntary context switches and the
   lowest power draw of the four replicas.
3. Host CPU pressure was 1.2-2.1% on the replicas and 0.7% on the client
   host, which used 11.3 of 64 cores.
4. Replica CPU tracked throughput across runs: 4.21-5.26 cores at 424,520
   tps, 4.63-5.63 at 457,167.

---

## 4. Stage K -- design

| factor | levels |
|---|---|
| physical cores on each pinned replica | 8, 6, 4, 3, 2, 1 |
| pinned replicas | leader; follower 0; follower 3; leader + follower 0; leader + follower 3; leader + followers 0 and 3 |
| baselines | B1, B2, B3, B4 |
| control | nothing pinned, one per baseline |

4 x (6 x 6 + 1) = 148 configurations x 5 reps = 740 runs, in rep-major
order, shuffled with a fixed seed. 60 s runs, 10 s warm-up, 2 s cool-down,
sampler on in every run. Verdicts use the rep-spread rule
(`BASELINE_ANALYSIS.md` section 1) over non-stalled runs.

**Mechanism.** A pinned replica is launched under `taskset -c 1-N`: N
physical cores, CPU 0 left out. No code in `src`, `include`, `examples`
or `salticidae` sets CPU affinity, so every thread inherits the mask.

**Verification: 740 of 740 runs pass.** In every sampled second of the
window, each pinned replica's process and every one of its threads were
allowed exactly CPUs `1-N` (`1` for one core), and each unpinned replica
all 64.

No cell reached a mean latency of 8 s, so the 10 s warm-up in a 60 s run
was long enough throughout.

---

## 5. Stage K -- results

Medians over non-stalled runs. **Bold** = resolvable against the control
(separation exceeds the worse of the two rep spreads).

#### B1: control 170,806 tps at 11.7 ms (spread 3.8%, stalled 0/5)

Throughput change against control:

| pinned | 8 cores | 6 cores | 4 cores | 3 cores | 2 cores | 1 core |
|---|---|---|---|---|---|---|
| leader | -3.9% | -3.4% | -1.3% | -1.5% | **-7.0%** | **-23.6%** |
| follower 0 | -2.8% | -1.8% | -3.3% | -3.8% | +2.4% | -3.2% |
| follower 3 | -4.1% | -4.0% | -0.8% | -0.8% | -1.4% | **+4.9%** |
| leader + follower 0 | -4.0% | -1.0% | -4.8% | -1.5% | **-8.9%** | **-23.4%** |
| leader + follower 3 | -3.0% | -1.4% | -1.1% | -0.7% | **-9.7%** | **-26.2%** |
| leader + followers 0, 3 | +0.2% | -2.9% | -1.5% | -1.7% | -11.1% | **-22.7%** |

Mean latency, ms (change against control):

| pinned | 8 cores | 6 cores | 4 cores | 3 cores | 2 cores | 1 core |
|---|---|---|---|---|---|---|
| leader | 12.2 (+4%) | 12.1 (+3%) | 11.9 (+1%) | 11.9 (+2%) | 12.6 (+8%) | 15.3 (+31%) |
| follower 0 | 12.0 (+3%) | 11.9 (+2%) | 12.1 (+3%) | 12.2 (+4%) | 11.4 (-2%) | 12.1 (+3%) |
| follower 3 | 12.2 (+4%) | 12.2 (+4%) | 11.8 (+1%) | 11.8 (+1%) | 11.9 (+1%) | 9.9 (-15%) |
| leader + follower 0 | 12.2 (+4%) | 11.8 (+1%) | 12.3 (+5%) | 11.9 (+2%) | 12.9 (+10%) | 15.3 (+31%) |
| leader + follower 3 | 12.1 (+3%) | 11.9 (+1%) | 11.8 (+1%) | 11.8 (+1%) | 13.0 (+11%) | 15.7 (+34%) |
| leader + followers 0, 3 | 11.7 (+0%) | 12.1 (+3%) | 11.9 (+2%) | 11.9 (+2%) | 13.2 (+12%) | 15.1 (+29%) |

On the pinned replicas: cores used / host CPU pressure %:

| pinned | 8 cores | 6 cores | 4 cores | 3 cores | 2 cores | 1 core |
|---|---|---|---|---|---|---|
| leader | r1 1.82 / 2.6 | r1 1.79 / 4.7 | r1 1.72 / 15.3 | r1 1.49 / 20.8 | r1 1.43 / 48.2 | r1 1.00 / 97.4 |
| follower 0 | r0 1.76 / 1.6 | r0 1.67 / 2.2 | r0 1.53 / 9.4 | r0 1.36 / 15.4 | r0 1.31 / 40.1 | r0 1.00 / 95.5 |
| follower 3 | r3 2.37 / 1.8 | r3 2.50 / 3.0 | r3 2.22 / 16.7 | r3 1.90 / 23.3 | r3 1.89 / 73.5 | r3 1.00 / 97.8 |
| leader + follower 0 | r1 1.89 / 3.0<br>r0 1.69 / 1.9 | r1 1.76 / 4.7<br>r0 1.66 / 2.0 | r1 1.65 / 13.2<br>r0 1.51 / 8.5 | r1 1.51 / 20.5<br>r0 1.38 / 14.3 | r1 1.41 / 47.4<br>r0 1.28 / 37.6 | r1 1.00 / 97.0<br>r0 0.98 / 93.7 |
| leader + follower 3 | r1 1.84 / 2.3<br>r3 2.46 / 1.6 | r1 1.75 / 4.5<br>r3 2.30 / 2.9 | r1 1.72 / 14.2<br>r3 2.17 / 16.1 | r1 1.53 / 19.4<br>r3 1.96 / 24.5 | r1 1.43 / 46.0<br>r3 1.82 / 69.9 | r1 0.99 / 96.4<br>r3 1.00 / 97.3 |
| leader + followers 0, 3 | r1 1.85 / 2.0<br>r0 1.75 / 1.5<br>r3 2.42 / 1.8 | r1 1.77 / 3.9<br>r0 1.68 / 2.0<br>r3 2.34 / 3.0 | r1 1.70 / 12.9<br>r0 1.58 / 8.9<br>r3 2.24 / 15.7 | r1 1.48 / 18.9<br>r0 1.39 / 14.3<br>r3 2.01 / 26.9 | r1 1.39 / 46.0<br>r0 1.27 / 37.2<br>r3 1.78 / 65.1 | r1 0.99 / 95.4<br>r0 0.97 / 92.9<br>r3 1.00 / 96.9 |

#### B2: control 308,603 tps at 13.0 ms (spread 8.3%, stalled 0/5)

Throughput change against control:

| pinned | 8 cores | 6 cores | 4 cores | 3 cores | 2 cores | 1 core |
|---|---|---|---|---|---|---|
| leader | -0.5% | +0.0% | -3.1% | -1.0% | **-10.3%** | **-40.5%** |
| follower 0 | -2.0% | -1.2% | +1.0% | -0.4% | +3.4% | **-8.6%** |
| follower 3 | +1.1% | -0.8% | -0.6% | +0.6% | **-11.7%** | +0.7% |
| leader + follower 0 | -0.7% | -2.1% | -1.9% | -2.1% | **-10.5%** | **-41.2%** |
| leader + follower 3 | +0.6% | -1.7% | -1.9% | -2.6% | **-23.6%** | **-47.5%** |
| leader + followers 0, 3 | -1.4% | +0.9% | -2.0% | -2.6% | **-20.8%** | **-48.9%** |

Mean latency, ms (change against control):

| pinned | 8 cores | 6 cores | 4 cores | 3 cores | 2 cores | 1 core |
|---|---|---|---|---|---|---|
| leader | 13.0 (+0%) | 13.0 (+0%) | 13.4 (+3%) | 13.1 (+1%) | 14.4 (+11%) | 21.8 (+68%) |
| follower 0 | 13.2 (+2%) | 13.1 (+1%) | 12.8 (-1%) | 13.0 (+0%) | 12.5 (-3%) | 14.2 (+9%) |
| follower 3 | 12.8 (-1%) | 13.1 (+1%) | 13.0 (+1%) | 12.9 (-1%) | 14.6 (+12%) | 12.9 (+0%) |
| leader + follower 0 | 13.0 (+1%) | 13.2 (+2%) | 13.2 (+2%) | 13.2 (+2%) | 14.5 (+12%) | 22.1 (+70%) |
| leader + follower 3 | 12.9 (-1%) | 13.2 (+2%) | 13.2 (+2%) | 13.3 (+3%) | 16.9 (+31%) | 24.7 (+90%) |
| leader + followers 0, 3 | 13.1 (+1%) | 12.8 (-1%) | 13.2 (+2%) | 13.3 (+3%) | 16.4 (+26%) | 25.4 (+96%) |

On the pinned replicas: cores used / host CPU pressure %:

| pinned | 8 cores | 6 cores | 4 cores | 3 cores | 2 cores | 1 core |
|---|---|---|---|---|---|---|
| leader | r1 2.99 / 4.0 | r1 2.86 / 8.4 | r1 2.57 / 27.8 | r1 2.14 / 38.7 | r1 1.81 / 73.4 | r1 1.00 / 97.4 |
| follower 0 | r0 2.92 / 3.0 | r0 2.73 / 6.3 | r0 2.51 / 24.7 | r0 2.00 / 31.5 | r0 1.88 / 76.3 | r0 1.00 / 98.4 |
| follower 3 | r3 4.19 / 4.1 | r3 3.84 / 9.9 | r3 3.21 / 42.9 | r3 2.89 / 71.9 | r3 2.00 / 98.6 | r3 1.00 / 97.8 |
| leader + follower 0 | r1 2.99 / 3.9<br>r0 2.91 / 3.3 | r1 2.81 / 7.8<br>r0 2.70 / 6.3 | r1 2.54 / 25.3<br>r0 2.43 / 23.5 | r1 2.17 / 39.8<br>r0 2.04 / 32.7 | r1 1.82 / 74.5<br>r0 1.79 / 71.5 | r1 1.00 / 97.5<br>r0 1.00 / 96.6 |
| leader + follower 3 | r1 3.04 / 3.9<br>r3 4.30 / 3.2 | r1 2.85 / 8.3<br>r3 3.74 / 10.4 | r1 2.55 / 26.9<br>r3 3.17 / 40.0 | r1 2.19 / 41.1<br>r3 2.66 / 55.2 | r1 1.65 / 68.2<br>r3 2.00 / 98.5 | r1 0.91 / 88.8<br>r3 1.00 / 97.8 |
| leader + followers 0, 3 | r1 2.96 / 3.5<br>r0 2.87 / 3.3<br>r3 4.14 / 3.1 | r1 2.89 / 8.4<br>r0 2.72 / 6.3<br>r3 4.01 / 10.9 | r1 2.55 / 27.5<br>r0 2.48 / 23.4<br>r3 3.31 / 42.7 | r1 2.14 / 38.6<br>r0 2.07 / 32.5<br>r3 2.87 / 68.3 | r1 1.70 / 69.2<br>r0 1.63 / 63.5<br>r3 2.00 / 97.4 | r1 0.92 / 89.2<br>r0 0.91 / 87.3<br>r3 1.00 / 97.8 |

#### B3: control 441,805 tps at 18.1 ms (spread 4.6%, stalled 1/5)

Throughput change against control:

| pinned | 8 cores | 6 cores | 4 cores | 3 cores | 2 cores | 1 core |
|---|---|---|---|---|---|---|
| leader | -1.1% | -4.3% | **-11.6%** | **-11.7%** | **-26.7%** | **-56.8%** |
| follower 0 | +0.4% | -0.7% | -4.8% | -4.1% | -13.6% | **-11.7%** |
| follower 3 | +0.4% | +0.7% | -3.6% | **-7.6%** | **-6.3%** | -0.7% |
| leader + follower 0 | -1.0% | **-6.5%** | **-14.2%** | **-14.5%** | **-27.9%** | **-56.4%** |
| leader + follower 3 | -0.6% | **-6.0%** | **-14.5%** | **-15.7%** | **-31.6%** | **-54.9%** |
| leader + followers 0, 3 | -0.1% | **-6.3%** | **-15.6%** | **-19.7%** | **-35.9%** | **-57.5%** |

Mean latency, ms (change against control):

| pinned | 8 cores | 6 cores | 4 cores | 3 cores | 2 cores | 1 core |
|---|---|---|---|---|---|---|
| leader | 18.3 (+1%) | 18.9 (+4%) | 20.5 (+13%) | 20.5 (+13%) | 24.7 (+36%) | 41.9 (+131%) |
| follower 0 | 18.0 (+0%) | 18.2 (+1%) | 19.0 (+5%) | 18.9 (+4%) | 20.7 (+14%) | 20.3 (+12%) |
| follower 3 | 18.0 (+0%) | 18.0 (-1%) | 18.8 (+4%) | 19.5 (+8%) | 19.3 (+7%) | 18.2 (+1%) |
| leader + follower 0 | 18.3 (+1%) | 19.4 (+7%) | 21.1 (+17%) | 21.2 (+17%) | 25.1 (+39%) | 41.6 (+130%) |
| leader + follower 3 | 18.2 (+0%) | 19.3 (+6%) | 21.2 (+17%) | 21.5 (+19%) | 26.5 (+46%) | 40.1 (+122%) |
| leader + followers 0, 3 | 18.1 (+0%) | 19.3 (+7%) | 21.4 (+18%) | 22.5 (+25%) | 28.2 (+56%) | 42.6 (+135%) |

On the pinned replicas: cores used / host CPU pressure %:

| pinned | 8 cores | 6 cores | 4 cores | 3 cores | 2 cores | 1 core |
|---|---|---|---|---|---|---|
| leader | r1 4.28 / 5.7 | r1 3.78 / 15.0 | r1 3.09 / 41.0 | r1 2.58 / 56.5 | r1 1.92 / 82.5 | r1 1.00 / 97.4 |
| follower 0 | r0 4.11 / 3.1 | r0 3.80 / 12.7 | r0 3.09 / 38.0 | r0 2.54 / 51.0 | r0 2.00 / 98.6 | r0 1.00 / 98.4 |
| follower 3 | r3 4.83 / 3.8 | r3 5.02 / 17.9 | r3 3.97 / 50.0 | r3 3.00 / 95.0 | r3 2.00 / 98.7 | r3 1.00 / 97.8 |
| leader + follower 0 | r1 4.11 / 5.8<br>r0 4.10 / 4.2 | r1 3.76 / 14.7<br>r0 3.60 / 11.1 | r1 3.05 / 39.5<br>r0 2.89 / 34.4 | r1 2.49 / 54.0<br>r0 2.39 / 45.8 | r1 1.93 / 83.8<br>r0 1.86 / 78.3 | r1 1.00 / 97.5<br>r0 0.98 / 94.9 |
| leader + follower 3 | r1 4.35 / 5.6<br>r3 5.57 / 6.3 | r1 3.75 / 14.2<br>r3 4.89 / 17.6 | r1 3.05 / 39.7<br>r3 3.56 / 48.7 | r1 2.53 / 55.6<br>r3 2.99 / 90.2 | r1 1.90 / 81.5<br>r3 2.00 / 98.6 | r1 1.00 / 97.5<br>r3 1.00 / 97.7 |
| leader + followers 0, 3 | r1 4.25 / 5.2<br>r0 4.13 / 3.2<br>r3 5.14 / 4.5 | r1 3.73 / 14.4<br>r0 3.62 / 11.2<br>r3 4.76 / 17.3 | r1 3.01 / 38.0<br>r0 2.86 / 33.4<br>r3 3.60 / 52.2 | r1 2.42 / 51.0<br>r0 2.30 / 43.8<br>r3 2.98 / 90.3 | r1 1.84 / 76.2<br>r0 1.71 / 68.9<br>r3 2.00 / 98.5 | r1 1.00 / 97.5<br>r0 0.99 / 95.5<br>r3 1.00 / 97.8 |

#### B4: control 455,631 tps at 70.2 ms (spread 4.1%, stalled 2/5)

Throughput change against control:

| pinned | 8 cores | 6 cores | 4 cores | 3 cores | 2 cores | 1 core |
|---|---|---|---|---|---|---|
| leader | -4.2% | -5.3% | **-11.8%** | **-9.7%** | **-25.1%** | **-55.9%** |
| follower 0 | +0.8% | +1.1% | **-5.1%** | **-7.5%** | **-12.0%** | **-12.3%** |
| follower 3 | +0.8% | -0.7% | -0.1% | -1.9% | -4.2% | -0.6% |
| leader + follower 0 | -1.5% | **-6.0%** | **-15.0%** | **-11.6%** | **-26.8%** | **-57.6%** |
| leader + follower 3 | -1.4% | -3.2% | **-15.1%** | **-12.2%** | **-25.7%** | **-56.8%** |
| leader + followers 0, 3 | -0.0% | **-5.6%** | **-17.4%** | **-17.5%** | **-32.3%** | **-57.5%** |

Mean latency, ms (change against control):

| pinned | 8 cores | 6 cores | 4 cores | 3 cores | 2 cores | 1 core |
|---|---|---|---|---|---|---|
| leader | 73.3 (+4%) | 74.2 (+6%) | 79.6 (+13%) | 77.8 (+11%) | 93.8 (+34%) | 159.2 (+127%) |
| follower 0 | 69.7 (-1%) | 69.5 (-1%) | 74.0 (+5%) | 75.9 (+8%) | 78.2 (+11%) | 78.1 (+11%) |
| follower 3 | 69.3 (-1%) | 70.7 (+1%) | 70.3 (+0%) | 71.4 (+2%) | 73.4 (+4%) | 70.6 (+1%) |
| leader + follower 0 | 71.3 (+2%) | 74.7 (+6%) | 82.7 (+18%) | 79.4 (+13%) | 95.9 (+37%) | 165.5 (+136%) |
| leader + follower 3 | 71.2 (+1%) | 72.6 (+3%) | 82.7 (+18%) | 80.0 (+14%) | 94.5 (+35%) | 162.4 (+131%) |
| leader + followers 0, 3 | 70.2 (+0%) | 74.4 (+6%) | 85.0 (+21%) | 85.2 (+21%) | 103.7 (+48%) | 165.4 (+136%) |

On the pinned replicas: cores used / host CPU pressure %:

| pinned | 8 cores | 6 cores | 4 cores | 3 cores | 2 cores | 1 core |
|---|---|---|---|---|---|---|
| leader | r1 4.05 / 4.4 | r1 3.77 / 12.6 | r1 3.06 / 37.7 | r1 2.59 / 55.1 | r1 1.95 / 86.7 | r1 1.00 / 97.9 |
| follower 0 | r0 4.02 / 3.6 | r0 3.81 / 10.7 | r0 3.08 / 38.1 | r0 2.56 / 50.5 | r0 2.00 / 99.0 | r0 1.00 / 98.4 |
| follower 3 | r3 5.59 / 4.1 | r3 5.19 / 15.9 | r3 3.95 / 45.0 | r3 3.00 / 94.7 | r3 2.00 / 98.7 | r3 1.00 / 97.8 |
| leader + follower 0 | r1 4.21 / 3.8<br>r0 4.06 / 3.5 | r1 3.72 / 11.8<br>r0 3.62 / 9.8 | r1 3.01 / 35.8<br>r0 2.87 / 33.8 | r1 2.55 / 52.8<br>r0 2.40 / 45.3 | r1 1.95 / 86.9<br>r0 1.85 / 75.7 | r1 1.00 / 98.0<br>r0 0.99 / 96.0 |
| leader + follower 3 | r1 4.26 / 4.2<br>r3 5.08 / 6.7 | r1 3.78 / 12.2<br>r3 4.83 / 14.6 | r1 3.00 / 37.0<br>r3 3.61 / 50.3 | r1 2.59 / 55.0<br>r3 3.00 / 95.4 | r1 1.95 / 86.4<br>r3 2.00 / 98.6 | r1 1.00 / 97.9<br>r3 1.00 / 97.7 |
| leader + followers 0, 3 | r1 4.12 / 4.0<br>r0 4.14 / 3.2<br>r3 5.57 / 3.0 | r1 3.74 / 12.0<br>r0 3.63 / 10.9<br>r3 4.88 / 15.0 | r1 2.92 / 35.0<br>r0 2.76 / 31.0<br>r3 3.60 / 49.0 | r1 2.46 / 47.6<br>r0 2.33 / 44.7<br>r3 2.98 / 89.4 | r1 1.87 / 77.5<br>r0 1.76 / 70.8<br>r3 2.00 / 98.7 | r1 1.00 / 97.7<br>r0 0.98 / 94.6<br>r3 1.00 / 97.8 |


Eight cells have a rep spread above 15% on non-stalled runs: B1 leader at
6 cores (15.2%), B1 all three at 2 cores (32.0%), B3 follower 0 at 8, 4 and
2 cores (34.8%, 24.0%, 15.8%), B3 follower 3 at 8 and 4 cores (25.9%,
21.9%), and B4 follower 3 at 8 cores (25.9%).

---

## 6. Findings

1. **8 cores changed nothing resolvable, in any of the 24 cells.** At 8
   cores the pinned replicas used at most 5.59 cores, with host CPU
   pressure at most 6.7%.

2. **Pinning the leader reduced throughput at every baseline, more as
   cores fell.**

   | | B1 | B2 | B3 | B4 |
   |---|---|---|---|---|
   | leader's use at 8 cores | 1.82 | 2.99 | 4.28 | 4.05 |
   | first resolvable loss | 2 cores (-7.0%) | 2 cores (-10.3%) | 4 cores (-11.6%) | 4 cores (-11.8%) |
   | loss at 1 core | -23.6% | -40.5% | -56.8% | -55.9% |
   | mean latency at 1 core | 15.3 ms (+31%) | 21.8 ms (+68%) | 41.9 ms (+131%) | 159.2 ms (+127%) |

3. **At 1 core, a single pinned follower cost far less than the pinned
   leader at every baseline, and followers 0 and 3 differed.** The one
   cell where a single follower lost more than the leader is B2 at 2
   cores: follower 3 -11.7%, leader -10.3%.
   - Follower 0 at 1 core: not resolvable at B1 (-3.2%); -8.6%, -11.7%,
     -12.3% at B2, B3, B4.
   - Follower 3 at 1 core: +4.9% at B1 (resolvable); -0.6% to +0.7% at
     B2-B4, not resolvable.
   - **Follower 3 was not monotonic in cores.** B2: -11.7% at 2 cores,
     +0.7% at 1. B3: -7.6% at 3 cores and -6.3% at 2, -0.7% at 1.

4. **Adding pinned followers to a pinned leader.** Leader alone against
   leader + followers 0 and 3:

   | | 4 cores | 3 cores | 2 cores | 1 core |
   |---|---|---|---|---|
   | B1 | -1.3% / -1.5% | -1.5% / -1.7% | **-7.0%** / -11.1% | **-23.6%** / **-22.7%** |
   | B2 | -3.1% / -2.0% | -1.0% / -2.6% | **-10.3%** / **-20.8%** | **-40.5%** / **-48.9%** |
   | B3 | **-11.6%** / **-15.6%** | **-11.7%** / **-19.7%** | **-26.7%** / **-35.9%** | **-56.8%** / **-57.5%** |
   | B4 | **-11.8%** / **-17.4%** | **-9.7%** / **-17.5%** | **-25.1%** / **-32.3%** | **-55.9%** / **-57.5%** |

   - At B3 and B4, pinning all three lost more than the leader alone at
     2-4 cores, and about the same at 1 core.
   - At B2, all three lost more at 2 and 1 cores; at 3-4 cores neither
     set's loss is resolvable.
   - At 1 core at B1, B3 and B4, the four leader sets lie within 3.5
     points of each other. At B2 they range from -40.5% (leader) to
     -48.9% (all three).

5. **At 1 core, every pinned replica was CPU-bound:** 0.91-1.00 cores used,
   host CPU pressure 87.3-98.4%.

6. **At 6 cores, losses were resolvable only at B3 and B4, and only with
   more than one replica pinned** (-5.6% to -6.5%).

---

## 7. Stalls

**10 of 740 runs stalled:** B1 0/185, B2 0/185, **B3 3/185**, B4 7/185.
In every one, the last commit came 0.58-3.28 s after start, followed by 49 s
with no commits.

| run | pinned | cores |
|---|---|---|
| K_B3_ctl_c0_r4 | none (control) | - |
| K_B3_f0_c4_r4 | follower 0 | 4 |
| K_B3_lead_f0_f3_c8_r3 | leader + followers 0, 3 | 8 |
| K_B4_ctl_c0_r3, K_B4_ctl_c0_r5 | none (control) | - |
| K_B4_lead_c8_r2 | leader | 8 |
| K_B4_lead_f0_c8_r4 | leader + follower 0 | 8 |
| K_B4_lead_f0_f3_c8_r5 | leader + followers 0, 3 | 8 |
| K_B4_f0_c4_r1 | follower 0 | 4 |
| K_B4_f3_c2_r2 | follower 3 | 2 |

Stalls occurred in unrestricted controls and at 8, 4 and 2 cores. None
occurred at 6, 3 or 1 core, and none at B1 or B2. **B3 had not stalled
before this stage** (`BASELINE_ANALYSIS.md` 13.2, corrected there).

---

## 8. Not established

- Why follower 3 uses more CPU than the other followers unrestricted, and
  why pinning it costs nothing at 1 core but costs throughput at 2-3.
- Why pinning follower 0 costs more than pinning follower 3.
- Why adding pinned followers to a pinned leader adds loss at some core
  levels and baselines and not at others (section 6, item 4).
- What causes stalled runs (carried over from `BASELINE_ANALYSIS.md`).

---

## 9. Data

| file | contents |
|---|---|
| `results/stage_u_results.csv`, `results/stage_u_analysis.txt` | Stage U, 10 runs |
| `results/stage_k_results.csv`, `results/stage_k_analysis.txt` | Stage K, 740 runs |
| `results/run_logs/<run_id>/compute-*.jsonl` | per-second compute samples, on node5, not in git |
| `benchmark/compute_sampler.py` | the sampler |
| `make_stage_u_csv.py`, `analyse_stage_u.py` | Stage U generator and analysis |
| `make_stage_k_csv.py`, `analyse_stage_k.py` | Stage K generator and analysis |
