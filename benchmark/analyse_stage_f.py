#!/usr/bin/env python3
"""Stage F: 7-rep confirmation of the Stage E effects.

Reports medians, and re-tests each comparison with the separation judged
against the rep spread of the cells involved.
"""
import glob
import json
import re
import statistics as st
from collections import defaultdict

PAT = r'{}_(B\d)_t(\d+)_skew([\d.]+)_mtx([\d.]+)_r(\d+)'
LABEL = {'B1': 'B1 bs200 c2 ma1000', 'B2': 'B2 bs800 c4 ma1000',
         'B3': 'B3 bs1600 c8 ma1000', 'B4': 'B4 bs3200 c8 ma4000'}


def load(prefix):
    g = defaultdict(list)
    for p in glob.glob(f'results/run_logs/{prefix}_B*/metrics.json'):
        m = re.match(PAT.format(prefix), p.split('/')[-2])
        if m:
            d = json.load(open(p))
            g[(m.group(1), int(m.group(2)), m.group(3), m.group(4))].append(
                (d['tps'], d['latency_ms_mean']))
    return g


E, F = load('E'), load('F')


def agg(v):
    tps = [x[0] for x in v]
    return (st.median(tps), st.median([x[1] for x in v]),
            (max(tps) - min(tps)) / st.mean(tps) * 100, len(v))


print('=== Stage F (7 reps) vs Stage E (3 reps) ===')
print(f'{"config":<30}{"E med":>10}{"E sp":>7}{"F med":>10}'
      f'{"F sp":>7}{"F lat":>8}{"F vs E":>9}')
for k in sorted(F):
    fm, flat, fsp, _ = agg(F[k])
    name = f'{k[0]} t{k[1]} skew{k[2]} mtx{k[3]}'
    if k in E:
        em, _, esp, _ = agg(E[k])
        print(f'{name:<30}{em:>10,.0f}{esp:>6.1f}%{fm:>10,.0f}'
              f'{fsp:>6.1f}%{flat:>8.1f}{100 * (fm - em) / em:>8.1f}%')
    else:
        print(f'{name:<30}{"-":>10}{"-":>7}{fm:>10,.0f}'
              f'{fsp:>6.1f}%{flat:>8.1f}{"-":>9}')

print('\n=== comparisons re-tested on 7-rep medians ===')


def compare(label, keys):
    got = [(k, agg(F[k])) for k in keys if k in F]
    if len(got) < 2:
        print(f'  {label}: insufficient data')
        return
    vals = [c[0] for _, c in got]
    sep = (max(vals) - min(vals)) / st.mean(vals) * 100
    worst = max(c[2] for _, c in got)
    verdict = 'CONFIRMED' if sep > worst else 'NOT resolvable at 7 reps'
    print(f'\n  {label}')
    for k, (m, lat, sp, n) in got:
        lv = k[1] if 't' in label else (k[2] if 'skew' in label else k[3])
        print(f'     {str(lv):<6}{m:>11,.0f}{lat:>9.1f} ms   spread {sp:.1f}%')
    print(f'     separation {sep:.1f}% vs worst spread {worst:.1f}%'
          f'  -> {verdict}')


compare('B3 threads (t)', [('B3', t, '0.1', '0.9') for t in (2, 4, 8)])
compare('B3 skew', [('B3', 4, s, '0.9') for s in ('0.1', '0.9')])
for b in ('B1', 'B2', 'B4'):
    compare(f'{b} write ratio (mtx)',
            [(b, 4, '0.1', m) for m in ('0.1', '0.5', '0.9')])

print('\n=== highest single cell in Stage F ===')
best = max(F.items(), key=lambda kv: agg(kv[1])[0])
m, lat, sp, n = agg(best[1])
print(f'  {best[0][0]} t{best[0][1]} skew{best[0][2]} mtx{best[0][3]}: '
      f'{m:,.0f} tps @ {lat:.1f} ms, spread {sp:.1f}%, {n} reps')

print('\n=== all 7 reps per config ===')
for k in sorted(F):
    vals = ', '.join(f'{x[0]:,.0f}' for x in sorted(F[k]))
    print(f'  {k[0]} t{k[1]} skew{k[2]} mtx{k[3]}: [{vals}]')
