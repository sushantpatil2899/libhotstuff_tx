#!/usr/bin/env python3
"""Stage P: batching trend at 8 clients x max_async 16000 (128,000
outstanding), against the same trend from Stage O at 32,000 outstanding.

3 reps, so verdicts use the rep-spread rule. Reports:
  1. delay verification from rtt.json
  2. the trend at this load, per condition, with the step ratio from one
     block size to the next
  3. the same step ratios from Stage O's load, side by side
  4. the Stage O repeat check (block_size 3200 at this exact load)
  5. throughput x latency against outstanding
"""
import csv
import glob
import json
import os
import re
import statistics as st
from collections import defaultdict

PAT = re.compile(r'P_bs(\d+)_(ctl|lead100|lead200)_r(\d+)')
COND = ('ctl', 'lead100', 'lead200')
LABEL = {'ctl': 'no delay', 'lead100': 'leader 100ms',
         'lead200': 'leader 200ms'}
OUTSTANDING = 8 * 16000

runs = defaultdict(list)
rtt_ok = rtt_bad = 0
for d in sorted(glob.glob('results/run_logs/P_*')):
    m = PAT.match(os.path.basename(d))
    if not m:
        continue
    mp = os.path.join(d, 'metrics.json')
    if os.path.exists(mp):
        runs[(int(m[1]), m[2])].append(json.load(open(mp)))
    rp = os.path.join(d, 'rtt.json')
    pairs = (json.load(open(rp)) if os.path.exists(rp) else {}).get('pairs')
    if not pairs or [p for p in pairs
                    if p['avg'] is None or p['loss_pct']
                    or abs(p['avg'] - p['expected_added_ms'])
                    > max(1.0, 0.02 * p['expected_added_ms'])]:
        rtt_bad += 1
    else:
        rtt_ok += 1


def agg(v):
    tps = [x['tps'] for x in v]
    return dict(tps=st.median(tps),
                lat=st.median(x['latency_ms_mean'] for x in v),
                spread=(max(tps) - min(tps)) / st.mean(tps) * 100, n=len(v))


C = {k: agg(v) for k, v in runs.items()}
print(f'Stage P: {sum(len(v) for v in runs.values())} runs, {len(C)} cells')
print(f'\n=== 1. delay verification === passing: {rtt_ok}  failing: {rtt_bad}')

# Stage O cells for comparison: (block_size, max_async) -> condition medians
O = defaultdict(list)
if os.path.exists('results/stage_o_results.csv'):
    for r in csv.DictReader(open('results/stage_o_results.csv')):
        m = re.match(r'O_bs(\d+)_ma(\d+)_(ctl|lead100|lead200)_r', r['run_id'])
        if m and r['tps']:
            O[(int(m[1]), int(m[2]), m[3])].append(
                (float(r['tps']), float(r['latency_ms_mean'])))
Omed = {k: st.median(x[0] for x in v) for k, v in O.items()}

print('\n=== 2. trend at 128,000 outstanding (8 clients x ma 16,000) ===')
for cond in COND:
    got = [(bs, C[(bs, cond)]) for bs in (800, 1600, 3200, 6400, 12800, 25600)
           if (bs, cond) in C]
    if not got:
        continue
    print(f'  --- {LABEL[cond]} ---')
    print(f'     {"block_size":>10}{"tps":>11}{"lat ms":>10}{"spread":>8}'
          f'{"x previous":>12}')
    prev = None
    for bs, x in got:
        step = f'{x["tps"] / prev:>11.2f}x' if prev else f'{"-":>12}'
        print(f'     {bs:>10}{x["tps"]:>11,.0f}{x["lat"]:>10.1f}'
              f'{x["spread"]:>7.1f}%{step}')
        prev = x['tps']
    vals = [x['tps'] for _, x in got]
    sep = (max(vals) - min(vals)) / st.mean(vals) * 100
    worst = max(x['spread'] for _, x in got)
    print(f'     separation {sep:.1f}% vs worst spread {worst:.1f}%'
          f'  -> {"RESOLVABLE" if sep > worst else "not resolvable"}')

print('\n=== 3. step ratios: this load vs Stage O (32,000 outstanding) ===')
print(f'  {"step":<16}{"condition":<14}{"P (128k)":>11}{"O (32k)":>11}')
for cond in COND:
    for lo, hi in ((800, 1600), (1600, 3200), (3200, 6400),
                   (6400, 12800), (12800, 25600)):
        p = (C[(hi, cond)]['tps'] / C[(lo, cond)]['tps']
             if (hi, cond) in C and (lo, cond) in C else None)
        o = (Omed[(hi, 4000, cond)] / Omed[(lo, 4000, cond)]
             if (hi, 4000, cond) in Omed and (lo, 4000, cond) in Omed
             else None)
        if p is None and o is None:
            continue
        print(f'  {f"{lo}->{hi}":<16}{LABEL[cond]:<14}'
              f'{f"{p:.2f}x" if p else "-":>11}'
              f'{f"{o:.2f}x" if o else "-":>11}')

print('\n=== 4. repeat check: block_size 3200 at this load, P vs Stage O ===')
for cond in COND:
    p, o = C.get((3200, cond)), Omed.get((3200, 16000, cond))
    if p and o:
        print(f'  {LABEL[cond]:<14}P {p["tps"]:>10,.0f}   O {o:>10,.0f}   '
              f'{(p["tps"] - o) / o * 100:+.1f}%')

print('\n=== 5. throughput x latency vs outstanding ===')
for k in sorted(C):
    x = C[k]
    prod = x['tps'] * x['lat'] / 1000
    print(f'  bs{k[0]:<6} {k[1]:<9}{x["tps"]:>10,.0f}{x["lat"] / 1000:>9.3f} s'
          f'{prod:>12,.0f} vs {OUTSTANDING:,}  '
          f'{(prod - OUTSTANDING) / OUTSTANDING * 100:+.1f}%')
