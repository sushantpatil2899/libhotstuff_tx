#!/usr/bin/env python3
"""Stage Q: slow Stage O/P cells re-measured on the fixed window.

Per cell (3 reps): fixed-window throughput and latency medians, how many
runs stalled, and, for comparison, the same cell from Stage O or P as it
was published (first-to-last-commit tps) and as commits over the 60 s run.
Anchor cells were measured cleanly by 60 s runs, so for them the new and
old numbers should agree; that agreement is what lets the corrected slow
cells be set beside the old clean ones.

Also reports delay verification from rtt.json.
"""
import csv
import glob
import json
import os
import re
import statistics as st
from collections import defaultdict

PAT = re.compile(r'Q_(O|P)_bs(\d+)_ma(\d+)_lead(\d+)_(slow|anchor)_r(\d+)')

runs = defaultdict(list)
rtt_ok = rtt_bad = 0
for d in sorted(glob.glob('results/run_logs/Q_*')):
    m = PAT.match(os.path.basename(d))
    if not m:
        continue
    mp = os.path.join(d, 'metrics.json')
    if os.path.exists(mp):
        runs[m.groups()[:5]].append(json.load(open(mp)))
    rp = os.path.join(d, 'rtt.json')
    pairs = (json.load(open(rp)) if os.path.exists(rp) else {}).get('pairs')
    if not pairs or [p for p in pairs if p['avg'] is None or p['loss_pct']
                    or abs(p['avg'] - p['expected_added_ms'])
                    > max(1.0, 0.02 * p['expected_added_ms'])]:
        rtt_bad += 1
    else:
        rtt_ok += 1

old = defaultdict(list)
for stage, pat in (('stage_o', r'O_bs(\d+)_ma(\d+)_lead(\d+)_r'),
                   ('stage_p', r'P_bs(\d+)_lead(\d+)_r')):
    path = f'results/{stage}_results.csv'
    if not os.path.exists(path):
        continue
    for r in csv.DictReader(open(path)):
        mm = re.match(pat, r['run_id'])
        if not mm:
            continue
        if stage == 'stage_o':
            key = ('O', mm[1], mm[2], mm[3])
        else:
            key = ('P', mm[1], '16000', mm[2])
        old[key].append((float(r['tps']), int(r['n_committed']) / 60))

n = sum(len(v) for v in runs.values())
print(f'Stage Q: {n} runs, {len(runs)} cells')
print(f'delay verification: {rtt_ok} passing, {rtt_bad} failing\n')
print(f'{"cell":<34}{"n":>2}{"stalled":>8}{"tps steady":>12}{"spread":>8}'
      f'{"lat s":>8}{"| old published":>16}{"old commits/60s":>17}')
for k in sorted(runs, key=lambda k: (k[4], k[0], int(k[1]), int(k[2]),
                                     int(k[3]))):
    v = runs[k]
    t = [x.get('tps_steady', 0) for x in v]
    stalls = sum(bool(x.get('stalled')) for x in v)
    sp = (max(t) - min(t)) / st.mean(t) * 100 if st.mean(t) else 0
    lt = st.median(x.get('latency_ms_mean_steady', 0) for x in v) / 1000
    o = old.get(k[:4], [])
    op = f'{st.median(x[0] for x in o):>15,.0f}' if o else f'{"-":>15}'
    oc = f'{st.median(x[1] for x in o):>17,.0f}' if o else f'{"-":>17}'
    name = f'{k[0]} bs{k[1]} ma{k[2]} lead{k[3]} {k[4]}'
    print(f'{name:<34}{len(v):>2}{stalls:>8}{st.median(t):>12,.0f}'
          f'{sp:>7.1f}%{lt:>8.2f} |{op}{oc}')

print('\nper run: tps_steady, clients committing, last commit s, '
      'longest zero-commit stretch s')
for k in sorted(runs):
    for x in runs[k]:
        print(f'  {k[0]} bs{k[1]} ma{k[2]} lead{k[3]} {k[4]:<6} '
              f'{x.get("tps_steady", 0):>10,.0f}  clients '
              f'{x.get("clients_committing")}  last {x.get("last_commit_s")}'
              f'  zero {x.get("longest_zero_commit_s")}'
              f'{"  STALLED" if x.get("stalled") else ""}')
