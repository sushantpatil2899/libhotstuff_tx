#!/usr/bin/env python3
"""Stage O: block_size and max_async under leader delay.

3 reps, so verdicts use the rep-spread rule (section 1 of
BASELINE_ANALYSIS.md). Reports:
  1. delay verification from rtt.json
  2. axis A: block_size 800-6400 at clients 8, max_async 4000
  3. axis B: max_async 4000-32000 at block_size 3200, clients 8
  4. throughput x latency against outstanding (clients x max_async), the
     arithmetic relation that held within 5.5% across Stage N's collapsed
     cells
"""
import glob
import json
import os
import re
import statistics as st
from collections import defaultdict

PAT = re.compile(r'O_bs(\d+)_ma(\d+)_(ctl|lead100|lead200)_r(\d+)')
COND = ('ctl', 'lead100', 'lead200')
LABEL = {'ctl': 'no delay', 'lead100': 'leader 100ms',
         'lead200': 'leader 200ms'}

runs = defaultdict(list)
rtt_ok = rtt_bad = 0
bad_detail = []
for d in sorted(glob.glob('results/run_logs/O_*')):
    m = PAT.match(os.path.basename(d))
    if not m:
        continue
    mp = os.path.join(d, 'metrics.json')
    if os.path.exists(mp):
        runs[(int(m[1]), int(m[2]), m[3])].append(json.load(open(mp)))
    rp = os.path.join(d, 'rtt.json')
    rtt = json.load(open(rp)) if os.path.exists(rp) else {}
    pairs = rtt.get('pairs')
    if not pairs:
        rtt_bad += 1
        bad_detail.append(f'{os.path.basename(d)}: no usable probe')
        continue
    f = [p for p in pairs
         if p['avg'] is None or p['loss_pct']
         or abs(p['avg'] - p['expected_added_ms'])
         > max(1.0, 0.02 * p['expected_added_ms'])]
    if f:
        rtt_bad += 1
        bad_detail.append(f'{os.path.basename(d)}: {f[:2]}')
    else:
        rtt_ok += 1


def agg(v):
    tps = [x['tps'] for x in v]
    return dict(tps=st.median(tps),
                lat=st.median(x['latency_ms_mean'] for x in v),
                p99=st.median(x['latency_ms_p99'] for x in v),
                spread=(max(tps) - min(tps)) / st.mean(tps) * 100,
                n=len(v))


C = {k: agg(v) for k, v in runs.items()}
print(f'Stage O: {sum(len(v) for v in runs.values())} runs, {len(C)} cells')
print(f'\n=== 1. delay verification === passing: {rtt_ok}  failing: {rtt_bad}')
for x in bad_detail[:10]:
    print(f'    {x}')


def table(title, cells, axis_name):
    print(f'\n=== {title} ===')
    for cond in COND:
        got = [(lbl, C[k]) for lbl, k in cells if (k[0], k[1], cond) in C
               for k in [(k[0], k[1], cond)]]
        if len(got) < 2:
            continue
        print(f'  --- {LABEL[cond]} ---')
        print(f'     {axis_name:>9}{"tps":>11}{"vs first":>10}{"lat ms":>10}'
              f'{"p99":>10}{"spread":>8}')
        first = got[0][1]['tps']
        for lbl, x in got:
            print(f'     {lbl:>9}{x["tps"]:>11,.0f}'
                  f'{(x["tps"] - first) / first * 100:>9.1f}%'
                  f'{x["lat"]:>10.1f}{x["p99"]:>10.1f}{x["spread"]:>7.1f}%')
        vals = [x['tps'] for _, x in got]
        sep = (max(vals) - min(vals)) / st.mean(vals) * 100
        worst = max(x['spread'] for _, x in got)
        print(f'     separation {sep:.1f}% vs worst spread {worst:.1f}%'
              f'  -> {"RESOLVABLE" if sep > worst else "not resolvable"}')


table('2. axis A: block_size at clients 8, max_async 4000',
      [(str(bs), (bs, 4000)) for bs in (800, 1600, 3200, 6400)], 'block_size')
table('3. axis B: max_async at block_size 3200, clients 8',
      [(str(ma), (3200, ma)) for ma in (4000, 8000, 16000, 32000)],
      'max_async')

print('\n=== 4. throughput x latency vs outstanding (clients x max_async) ===')
print(f'  {"cell":<26}{"tps":>10}{"lat s":>9}{"product":>11}'
      f'{"outstanding":>13}{"diff":>8}')
for k in sorted(C):
    x = C[k]
    out = 8 * k[1]
    prod = x['tps'] * x['lat'] / 1000
    print(f'  bs{k[0]} ma{k[1]} {k[2]:<10}{x["tps"]:>10,.0f}'
          f'{x["lat"] / 1000:>9.3f}{prod:>11,.0f}{out:>13,}'
          f'{(prod - out) / out * 100:>7.1f}%')
