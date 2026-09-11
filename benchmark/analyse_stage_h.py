#!/usr/bin/env python3
"""Stage H: 7-rep check of bs3200 c16 ma1000 vs B4, and bs6400 vs bs3200
at c16 ma4000. threads=4, mtx=0.9, skew=0.1 throughout.

Verdicts: exact two-sided Mann-Whitney U over all C(14,7) splits, on
throughput and on mean latency for each of the two pairs. Four tests,
so a result is confirmed at p < 0.05 / 4 = 0.0125. The Stage G 3-rep
median for each cell is printed alongside.
"""
import csv
import glob
import json
import re
import statistics as st
from collections import defaultdict
from itertools import combinations

PAT = re.compile(r'H_bs(\d+)_c(\d+)_ma(\d+)_r(\d+)')
R = defaultdict(list)
for p in glob.glob('results/run_logs/H_*/metrics.json'):
    m = PAT.match(p.split('/')[-2])
    if m:
        R[(int(m[1]), int(m[2]), int(m[3]))].append(json.load(open(p)))

G = defaultdict(list)
try:
    for r in csv.DictReader(open('results/stage_g_results.csv')):
        if (r['status'] == 'OK' and r['tps'] and r['nworker'] == '4'
                and r['sb_prob_choose_mtx'] == '0.9'):
            G[(int(r['block_size']), int(r['num_clients']),
               int(r['max_async']))].append(float(r['tps']))
except FileNotFoundError:
    pass


def mann_whitney(a, b):
    """Exact two-sided Mann-Whitney U by full enumeration."""
    def u(x, y):
        return sum((i > j) + 0.5 * (i == j) for i in x for j in y)
    pool, n = a + b, len(a)
    mu = n * len(b) / 2
    obs = abs(u(a, b) - mu)
    hits = tot = 0
    for idx in combinations(range(len(pool)), n):
        chosen = set(idx)
        x = [pool[i] for i in idx]
        y = [pool[i] for i in range(len(pool)) if i not in chosen]
        tot += 1
        hits += abs(u(x, y) - mu) >= obs - 1e-9
    return hits / tot


def name(k):
    return f'bs{k[0]} c{k[1]} ma{k[2]}'


print(f'Stage H: {sum(len(v) for v in R.values())} runs, {len(R)} cells\n')
print(f'{"cell":<20}{"n":>3}{"tps med":>11}{"spread":>8}{"lat":>8}'
      f'{"p50":>8}{"p95":>8}{"p99":>8}{"G med":>11}')
for k in sorted(R):
    v = R[k]
    tps = [x['tps'] for x in v]
    g = f'{st.median(G[k]):>11,.0f}' if G.get(k) else f'{"-":>11}'
    print(f'{name(k):<20}{len(v):>3}{st.median(tps):>11,.0f}'
          f'{(max(tps) - min(tps)) / st.mean(tps) * 100:>7.1f}%'
          f'{st.median(x["latency_ms_mean"] for x in v):>8.1f}'
          f'{st.median(x["latency_ms_p50"] for x in v):>8.1f}'
          f'{st.median(x["latency_ms_p95"] for x in v):>8.1f}'
          f'{st.median(x["latency_ms_p99"] for x in v):>8.1f}{g}')

print('\nall runs (tps / mean latency ms), sorted by tps:')
for k in sorted(R):
    runs = sorted((x['tps'], x['latency_ms_mean']) for x in R[k])
    print(f'  {name(k):<20}' + '  '.join(f'{t:,.0f}/{l:.1f}' for t, l in runs))

PAIRS = [((3200, 16, 1000), (3200, 8, 4000)),
         ((6400, 16, 4000), (3200, 16, 4000))]
ALPHA = 0.05 / (2 * len(PAIRS))
print(f'\n=== rank tests, confirm at p < {ALPHA:.4f} ===')
for a, b in PAIRS:
    if a not in R or b not in R:
        print(f'  {name(a)} vs {name(b)}: missing data')
        continue
    for metric in ('tps', 'latency_ms_mean'):
        x = [r[metric] for r in R[a]]
        y = [r[metric] for r in R[b]]
        p = mann_whitney(x, y)
        diff = (st.median(x) - st.median(y)) / st.median(y) * 100
        ov = 'no' if min(x) > max(y) or min(y) > max(x) else 'yes'
        print(f'  {name(a)} vs {name(b)}  {metric:<16} '
              f'{st.median(x):>11,.1f} vs {st.median(y):>11,.1f} '
              f'({diff:+.1f}%)  p={p:.4f}  overlap={ov:<3} '
              f'{"CONFIRMED" if p < ALPHA else "not confirmed"}')

print('\n=== lowest run / cell median ===')
for k in sorted(R):
    tps = [x['tps'] for x in R[k]]
    print(f'  {name(k):<20}{min(tps) / st.median(tps):.3f}')
