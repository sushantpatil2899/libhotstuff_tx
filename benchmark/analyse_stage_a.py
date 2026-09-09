#!/usr/bin/env python3
"""Stage A: report each factor's levels against the centre point.

Reports measurements only. Rep spread is (max-min)/mean across the 3
reps of a configuration and is the reference for whether a difference
between levels is larger than the run-to-run variation observed here.
"""
import glob
import json
import re
import statistics as st
from collections import defaultdict

CENTRE = 'bs200_k10_t4_mtx0.9_skew0.1_u1e6'
FACTORS = [('bs', 'block_size'), ('k', 'depth k'), ('t', 'threads'),
           ('mtx', 'write ratio'), ('skew', 'skew'), ('u', 'sb_users')]
PATS = {'bs': r'bs(\d+)', 'k': r'_k(\d+)', 't': r'_t(\d+)',
        'mtx': r'mtx([\d.]+)', 'skew': r'skew([\d.]+)', 'u': r'_u(\S+)'}


def parse(cfg):
    return {k: re.search(p, cfg).group(1) for k, p in PATS.items()}


def main():
    g = defaultdict(list)
    for p in glob.glob('results/run_logs/SA_*/metrics.json'):
        cfg = p.split('/')[-2][3:].rsplit('_r', 1)[0]
        m = json.load(open(p))
        g[cfg].append((m['tps'], m['latency_ms_mean'], m['n_committed']))

    if CENTRE not in g:
        print('centre point missing')
        return
    cen = st.mean(x[0] for x in g[CENTRE])
    reps = ', '.join(f'{x[0]:,.0f}' for x in g[CENTRE])
    print(f'centre {CENTRE}')
    print(f'  tps {cen:,.0f}   reps: {reps}')
    cd = parse(CENTRE)

    all_spreads = []
    for key, label in FACTORS:
        rows = []
        for cfg in g:
            d = parse(cfg)
            if all(d[o] == cd[o] for o, _ in FACTORS if o != key):
                v = [x[0] for x in g[cfg]]
                lat = [x[1] for x in g[cfg]]
                spread = (max(v) - min(v)) / st.mean(v) * 100
                all_spreads.append(spread)
                rows.append((d[key], st.mean(v), st.mean(lat), spread,
                             100 * (st.mean(v) - cen) / cen))
        try:
            rows.sort(key=lambda r: float(r[0]))
        except ValueError:
            rows.sort()
        print(f'\n--- {label} ---')
        print(f'   {"level":<8}{"tps":>11}{"lat ms":>10}'
              f'{"rep spread":>12}{"vs centre":>11}')
        for lv, t, lat, sp, dv in rows:
            print(f'   {lv:<8}{t:>11,.0f}{lat:>10.1f}{sp:>11.1f}%{dv:>10.1f}%')

    all_spreads.sort()
    n = len(all_spreads)
    print(f'\nrep spread across all {n} configs: '
          f'median {all_spreads[n // 2]:.1f}%, max {all_spreads[-1]:.1f}%')


if __name__ == '__main__':
    main()
