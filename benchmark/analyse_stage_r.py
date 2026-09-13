#!/usr/bin/env python3
"""Stage R: B4 vs bs3200/c16/ma1000 on the fixed window (see
make_stage_r_csv.py for the pre-registered verdicts)."""
import glob
import json
import os
import re
import statistics as st
from itertools import combinations

ALPHA = 0.05 / 2


def mw(a, b):
    def u(x, y):
        return sum((i > j) + 0.5 * (i == j) for i in x for j in y)
    pool, n = a + b, len(a)
    mu = n * len(b) / 2
    obs = abs(u(a, b) - mu)
    hits = tot = 0
    for idx in combinations(range(len(pool)), n):
        s = set(idx)
        x = [pool[i] for i in idx]
        y = [pool[i] for i in range(len(pool)) if i not in s]
        tot += 1
        hits += abs(u(x, y) - mu) >= obs - 1e-9
    return hits / tot


R = {'B4': [], 'cand': []}
for d in sorted(glob.glob('results/run_logs/R_*')):
    m = re.match(r'R_(B4|cand)_.*_r(\d+)$', os.path.basename(d))
    mp = os.path.join(d, 'metrics.json')
    if m and os.path.exists(mp):
        x = json.load(open(mp))
        x['rep'] = int(m[2])
        R[m[1]].append(x)

label = {'B4': 'B4 (c8 ma4000)', 'cand': 'candidate (c16 ma1000)'}
for k, v in R.items():
    ok = [x for x in v if not x.get('stalled')]
    print(f'{label[k]}: {len(v)} runs, {len(v) - len(ok)} stalled')
    for x in sorted(v, key=lambda x: x['rep']):
        print(f'   r{x["rep"]:<3}{x.get("tps_steady", 0):>10,.0f} tps  '
              f'{x.get("latency_ms_mean_steady", 0):>7.1f} ms  p99 worst client '
              f'{x.get("latency_ms_p99_steady_worst_client", 0):>7.1f}  '
              f'zero-commit {x.get("longest_zero_commit_s")} s'
              f'{"  STALLED" if x.get("stalled") else ""}'
              f'   (old formula {x["tps"]:,.0f})')
    if ok:
        t = [x['tps_steady'] for x in ok]
        print(f'   clean median {st.median(t):,.0f} tps, '
              f'{st.median(x["latency_ms_mean_steady"] for x in ok):.1f} ms, '
              f'spread {(max(t) - min(t)) / st.mean(t) * 100:.1f}%')

a = [x for x in R['cand'] if not x.get('stalled')]
b = [x for x in R['B4'] if not x.get('stalled')]
if len(a) >= 2 and len(b) >= 2:
    print(f'\nrank tests on non-stalled runs, confirm at p < {ALPHA}:')
    for f in ('tps_steady', 'latency_ms_mean_steady'):
        p = mw([x[f] for x in a], [x[f] for x in b])
        print(f'   {f:<24} candidate {st.median(x[f] for x in a):,.1f} vs '
              f'B4 {st.median(x[f] for x in b):,.1f}  p={p:.4f}  '
              f'{"CONFIRMED" if p < ALPHA else "not confirmed"}')
