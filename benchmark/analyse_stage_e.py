#!/usr/bin/env python3
"""Stage E: threads / skew / write ratio at each of the four baselines.

Reports medians. Each factor is compared against the baseline variant
(threads=4, skew=0.1, mtx=0.9) at the same baseline, and the separation
is judged against the rep spread of the cells involved.
"""
import glob
import json
import re
import statistics as st
from collections import defaultdict

BASE_T, BASE_S, BASE_M = 4, '0.1', '0.9'
LABEL = {'B1': 'B1 bs200 c2 ma1000', 'B2': 'B2 bs800 c4 ma1000',
         'B3': 'B3 bs1600 c8 ma1000', 'B4': 'B4 bs3200 c8 ma4000'}

g = defaultdict(list)
for p in glob.glob('results/run_logs/E_B*/metrics.json'):
    m = re.match(r'E_(B\d)_t(\d+)_skew([\d.]+)_mtx([\d.]+)_r(\d+)',
                 p.split('/')[-2])
    if m:
        d = json.load(open(p))
        g[(m.group(1), int(m.group(2)), m.group(3), m.group(4))].append(
            (d['tps'], d['latency_ms_mean']))

cells = {k: (st.median([x[0] for x in v]),
             st.median([x[1] for x in v]),
             (max(x[0] for x in v) - min(x[0] for x in v))
             / st.mean(x[0] for x in v) * 100,
             len(v))
         for k, v in g.items()}

for b in ('B1', 'B2', 'B3', 'B4'):
    base = cells.get((b, BASE_T, BASE_S, BASE_M))
    if not base:
        continue
    print(f'\n########## {LABEL[b]} ##########')
    print(f'  baseline: {base[0]:,.0f} tps  {base[1]:,.1f} ms  '
          f'spread {base[2]:.1f}%')

    for fname, keys in (
            ('threads', [(b, t, BASE_S, BASE_M) for t in (2, 4, 8, 16)]),
            ('skew', [(b, BASE_T, s, BASE_M) for s in ('0.1', '0.5', '0.9')]),
            ('write ratio',
             [(b, BASE_T, BASE_S, m) for m in ('0.1', '0.5', '0.9')])):
        got = [(k, cells[k]) for k in keys if k in cells]
        if len(got) < 2:
            continue
        print(f'  --- {fname} ---')
        print(f'     {"level":<8}{"tps":>11}{"lat ms":>10}'
              f'{"spread":>9}{"vs base":>10}')
        tps_vals = []
        for k, (t, lat, sp, n) in got:
            lv = (k[1] if fname == 'threads'
                  else k[2] if fname == 'skew' else k[3])
            tps_vals.append(t)
            print(f'     {str(lv):<8}{t:>11,.0f}{lat:>10,.1f}'
                  f'{sp:>8.1f}%{100 * (t - base[0]) / base[0]:>9.1f}%')
        sep = (max(tps_vals) - min(tps_vals)) / st.mean(tps_vals) * 100
        worst = max(c[2] for _, c in got)
        verdict = ('RESOLVABLE' if sep > worst
                   else 'within rep spread - not resolvable')
        print(f'     separation {sep:.1f}% vs worst spread {worst:.1f}%'
              f'  -> {verdict}')

sp = sorted(c[2] for c in cells.values())
n = len(sp)
print(f'\nrep spread over {n} cells: median {sp[n // 2]:.1f}%, '
      f'max {sp[-1]:.1f}%')
