#!/usr/bin/env python3
"""Stage G: block_size 6400 x clients x max_async x threads x write ratio.

3 reps per config, so verdicts use the rep-spread rule of section 1 of
BASELINE_ANALYSIS.md: a separation of medians is resolvable only if it
exceeds the worst (max-min)/mean spread of the cells compared. This is a
screen; anything it resolves is a candidate for a 7-rep check.

Reports, in order:
  1. block_size 6400 vs 3200 at identical (clients, max_async, threads,
     mtx) -- the question this stage exists for
  2. the surface at threads=4, mtx=0.9 (the adopted settings), with the
     Stage D3 median at the same bs3200 cell for overlap
  3. threads 2/4/8 within each (bs, clients, max_async, mtx) cell
  4. write ratio 0.1 vs 0.9 within each (bs, clients, max_async, threads)
  5. throughput/latency frontier over all 72 configs
  6. collapsed-run check: lowest run / cell median
"""
import csv
import glob
import json
import os
import re
import statistics as st
from collections import defaultdict

PAT = re.compile(r'G_bs(\d+)_c(\d+)_ma(\d+)_t(\d+)_mtx([\d.]+)_r(\d+)')

runs = defaultdict(list)
for p in glob.glob('results/run_logs/G_*/metrics.json'):
    m = PAT.match(p.split('/')[-2])
    if not m:
        continue
    d = json.load(open(p))
    k = (int(m.group(1)), int(m.group(2)), int(m.group(3)),
         int(m.group(4)), m.group(5))
    runs[k].append(d)


def agg(v):
    tps = [x['tps'] for x in v]
    return dict(tps=st.median(tps),
                lat=st.median(x['latency_ms_mean'] for x in v),
                p95=st.median(x['latency_ms_p95'] for x in v),
                p99=st.median(x['latency_ms_p99'] for x in v),
                spread=(max(tps) - min(tps)) / st.mean(tps) * 100,
                n=len(v), raw=sorted(tps))


C = {k: agg(v) for k, v in runs.items()}
print(f'Stage G: {sum(len(v) for v in runs.values())} runs parsed, '
      f'{len(C)} configs')


def verdict(cells):
    vals = [c['tps'] for c in cells]
    sep = (max(vals) - min(vals)) / st.mean(vals) * 100
    worst = max(c['spread'] for c in cells)
    return sep, worst, ('RESOLVABLE' if sep > worst else 'not resolvable')


def name(k):
    return f'bs{k[0]} c{k[1]} ma{k[2]} t{k[3]} mtx{k[4]}'


# 1. block_size 6400 vs 3200 ------------------------------------------------
print('\n=== 1. block_size 6400 vs 3200, identical other coordinates ===')
print(f'{"c":>3}{"ma":>7}{"t":>3}{"mtx":>5}{"bs3200":>11}{"bs6400":>11}'
      f'{"gain":>8}{"lat3200":>9}{"lat6400":>9}{"worst sp":>10}  verdict')
tally = defaultdict(int)
for k in sorted(C):
    if k[0] != 6400:
        continue
    lo = (3200,) + k[1:]
    if lo not in C:
        continue
    a, b = C[lo], C[k]
    gain = (b['tps'] - a['tps']) / a['tps'] * 100
    sep, worst, v = verdict([a, b])
    tag = v if v == 'not resolvable' else ('RISING' if gain > 0 else 'FALLING')
    tally[tag] += 1
    print(f'{k[1]:>3}{k[2]:>7}{k[3]:>3}{k[4]:>5}{a["tps"]:>11,.0f}'
          f'{b["tps"]:>11,.0f}{gain:>7.1f}%{a["lat"]:>9.1f}{b["lat"]:>9.1f}'
          f'{worst:>9.1f}%  {tag}')
print('  tally:', dict(tally))

# 2. surface at adopted settings ------------------------------------------
print('\n=== 2. surface at threads=4, mtx=0.9 (tps / mean lat ms / spread) ===')
d3 = defaultdict(list)
if os.path.exists('results/stage_d3_results.csv'):
    for r in csv.DictReader(open('results/stage_d3_results.csv')):
        if r['status'] == 'OK' and r['tps']:
            d3[(int(r['block_size']), int(r['num_clients']),
                int(r['max_async']))].append(float(r['tps']))
for bs in (3200, 6400):
    for c in (4, 8, 16):
        for ma in (1000, 4000, 16000):
            k = (bs, c, ma, 4, '0.9')
            if k not in C:
                continue
            x = C[k]
            ov = ''
            if bs == 3200 and d3.get((bs, c, ma)):
                dm = st.median(d3[(bs, c, ma)])
                ov = (f'   D3 median {dm:,.0f} '
                      f'({(x["tps"] - dm) / dm * 100:+.1f}%)')
            print(f'  bs{bs:<5} c{c:<3} ma{ma:<6} {x["tps"]:>10,.0f} '
                  f'{x["lat"]:>7.1f} ms {x["spread"]:>5.1f}%{ov}')

# 3. threads ---------------------------------------------------------------
print('\n=== 3. threads 2/4/8 within each (bs, c, ma, mtx) ===')
for bs, c, ma, m in sorted({(k[0], k[1], k[2], k[4]) for k in C}):
    got = [(t, C[(bs, c, ma, t, m)]) for t in (2, 4, 8)
           if (bs, c, ma, t, m) in C]
    if len(got) < 2:
        continue
    sep, worst, v = verdict([g for _, g in got])
    vals = '  '.join(f't{t} {g["tps"]:>9,.0f}/{g["lat"]:.1f}' for t, g in got)
    print(f'  bs{bs} c{c:<2} ma{ma:<5} mtx{m}  {vals}   '
          f'sep {sep:.1f}% vs {worst:.1f}%  {v}')

# 4. write ratio -----------------------------------------------------------
print('\n=== 4. write ratio 0.1 vs 0.9 within each (bs, c, ma, t) ===')
for bs, c, ma, t in sorted({k[:4] for k in C}):
    a, b = C.get((bs, c, ma, t, '0.1')), C.get((bs, c, ma, t, '0.9'))
    if not (a and b):
        continue
    sep, worst, v = verdict([a, b])
    print(f'  bs{bs} c{c:<2} ma{ma:<5} t{t}  10%w {a["tps"]:>9,.0f}/'
          f'{a["lat"]:.1f}  90%w {b["tps"]:>9,.0f}/{b["lat"]:.1f}  '
          f'{(a["tps"] - b["tps"]) / b["tps"] * 100:+.1f}%  '
          f'sep {sep:.1f}% vs {worst:.1f}%  {v}')

# 5. frontier ----------------------------------------------------------------
print('\n=== 5. throughput/latency frontier (no config has both higher tps '
      'and lower latency) ===')
front = [k for k in C if not any(
    C[o]['tps'] > C[k]['tps'] and C[o]['lat'] < C[k]['lat'] for o in C)]
for k in sorted(front, key=lambda k: C[k]['lat']):
    x = C[k]
    print(f'  {name(k):<36} {x["tps"]:>10,.0f}  {x["lat"]:>6.1f} ms  '
          f'p95 {x["p95"]:.1f}  p99 {x["p99"]:.1f}  spread {x["spread"]:.1f}%')
print('\n  top 10 by median tps:')
for k in sorted(C, key=lambda k: -C[k]['tps'])[:10]:
    x = C[k]
    print(f'  {name(k):<36} {x["tps"]:>10,.0f}  {x["lat"]:>6.1f} ms  '
          f'spread {x["spread"]:.1f}%')

# 6. collapsed runs -----------------------------------------------------------
print('\n=== 6. lowest run / cell median ===')
ratios = sorted((min(x['raw']) / x['tps'], k) for k, x in C.items())
for r, k in ratios[:5]:
    print(f'  {r:.3f}  {name(k)}  runs {[round(v) for v in C[k]["raw"]]}')
sp = sorted(x['spread'] for x in C.values())
print(f'\nrep spread over {len(sp)} configs: median {sp[len(sp) // 2]:.1f}%, '
      f'max {sp[-1]:.1f}%')
