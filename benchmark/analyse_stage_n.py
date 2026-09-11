#!/usr/bin/env python3
"""Stage N: injected network latency at B1-B4.

Reports, in order:
  1. Delay verification from each run's rtt.json. A pair passes when it
     lost no packets and its mean round trip is within
     max(1 ms, 2%) of the round trip the tc rules should add
     (2 x max(lat_a, lat_b) between replicas, 0 from the client host).
     Runs with a missing or failed probe are listed.
  2. Per baseline, median throughput and mean latency for the control and
     every scenario x delay, the change against the control, and the
     rep-spread verdict (section 1 of BASELINE_ANALYSIS.md: a separation
     is resolvable only if it exceeds the worst spread of the two cells).
  3. Collapsed-run check: lowest run / cell median.

5 reps per cell, so this is a screen. Anything it resolves that needs
confirming goes to a 7-rep check, as with Stages E->F and G->H.
"""
import glob
import json
import os
import re
import statistics as st
from collections import defaultdict

PAT = re.compile(r'N_(B\d)_(ctl|lead|f1|f2|f3)_d(\d+)_r(\d+)')
BASE = {'B1': 'bs200 c2 ma1000', 'B2': 'bs800 c4 ma1000',
        'B3': 'bs1600 c8 ma1000', 'B4': 'bs3200 c8 ma4000'}
SCEN = {'lead': 'leader only', 'f1': 'one follower (0)',
        'f2': 'two followers (0,2)', 'f3': 'three followers (0,2,3)'}

runs = defaultdict(list)
rtt_bad, rtt_missing, rtt_ok = [], [], 0
delayed_avg = defaultdict(list)     # expected_ms -> measured avg RTTs
for d in sorted(glob.glob('results/run_logs/N_*')):
    rid = os.path.basename(d)
    m = PAT.match(rid)
    if not m:
        continue
    key = (m[1], m[2], int(m[3]))
    mp = os.path.join(d, 'metrics.json')
    if os.path.exists(mp):
        runs[key].append(json.load(open(mp)))
    rp = os.path.join(d, 'rtt.json')
    rtt = json.load(open(rp)) if os.path.exists(rp) else None
    if not rtt or 'pairs' not in rtt:
        rtt_missing.append(f'{rid}: {rtt.get("error") if rtt else "no rtt.json"}')
        continue
    fails = []
    for p in rtt['pairs']:
        exp, avg = p['expected_added_ms'], p.get('avg')
        if avg is None or p.get('loss_pct'):
            fails.append(f'{p["src"]}->{p["dst"]} loss {p.get("loss_pct")}%')
            continue
        delayed_avg[exp].append(avg)
        if abs(avg - exp) > max(1.0, 0.02 * exp):
            fails.append(f'{p["src"]}->{p["dst"]} expected +{exp} ms, '
                         f'measured {avg:.2f} ms')
    if fails:
        rtt_bad.append((rid, fails))
    else:
        rtt_ok += 1

n_runs = sum(len(v) for v in runs.values())
print(f'Stage N: {n_runs} runs with metrics, {len(runs)} cells')

print('\n=== 1. delay verification (rtt.json) ===')
print(f'  runs passing every pair: {rtt_ok}')
print(f'  runs with a failing pair: {len(rtt_bad)}')
for rid, fails in rtt_bad[:20]:
    print(f'    {rid}: ' + '; '.join(fails[:4]))
print(f'  runs with no usable probe: {len(rtt_missing)}')
for x in rtt_missing[:20]:
    print(f'    {x}')
print('  measured mean RTT by expected added RTT, over all pairs:')
for exp in sorted(delayed_avg):
    v = delayed_avg[exp]
    print(f'    expected +{exp:>3} ms: n={len(v):>5}  '
          f'min {min(v):8.2f}  median {st.median(v):8.2f}  max {max(v):8.2f}')


def agg(v):
    tps = [x['tps'] for x in v]
    return dict(tps=st.median(tps),
                lat=st.median(x['latency_ms_mean'] for x in v),
                p99=st.median(x['latency_ms_p99'] for x in v),
                spread=(max(tps) - min(tps)) / st.mean(tps) * 100,
                n=len(v), raw=sorted(tps))


C = {k: agg(v) for k, v in runs.items()}

print('\n=== 2. per baseline: median tps / mean latency, vs control ===')
for b in BASE:
    ctl = C.get((b, 'ctl', 0))
    if not ctl:
        continue
    print(f'\n########## {b} {BASE[b]} ##########')
    print(f'  control (0 ms): {ctl["tps"]:>10,.0f} tps  {ctl["lat"]:>7.1f} ms'
          f'  p99 {ctl["p99"]:.1f}  spread {ctl["spread"]:.1f}%  n={ctl["n"]}')
    for s, label in SCEN.items():
        print(f'  --- {label} ---')
        print(f'     {"delay":>6}{"tps":>11}{"vs ctl":>9}{"lat ms":>9}'
              f'{"vs ctl":>9}{"p99":>9}{"spread":>8}  verdict (tps)')
        for d in (50, 100, 150, 200):
            x = C.get((b, s, d))
            if not x:
                continue
            sep = abs(x['tps'] - ctl['tps']) / st.mean(
                [x['tps'], ctl['tps']]) * 100
            worst = max(x['spread'], ctl['spread'])
            v = 'RESOLVABLE' if sep > worst else 'not resolvable'
            print(f'     {d:>4}ms{x["tps"]:>11,.0f}'
                  f'{(x["tps"] - ctl["tps"]) / ctl["tps"] * 100:>8.1f}%'
                  f'{x["lat"]:>9.1f}'
                  f'{(x["lat"] - ctl["lat"]) / ctl["lat"] * 100:>8.0f}%'
                  f'{x["p99"]:>9.1f}{x["spread"]:>7.1f}%  {v}')

print('\n=== 3. lowest run / cell median (lowest 10) ===')
for r, k in sorted((min(x['raw']) / x['tps'], k) for k, x in C.items())[:10]:
    print(f'  {r:.3f}  {k[0]} {k[1]} d{k[2]}  runs '
          f'{[round(v) for v in C[k]["raw"]]}')
