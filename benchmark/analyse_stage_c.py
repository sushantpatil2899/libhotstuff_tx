#!/usr/bin/env python3
"""Stage C: max_async extended to 256,000, with the Stage B overlap checked.

Reports measurements only.
"""
import glob
import json
import re
import statistics as st
from collections import defaultdict

BS = [100, 200, 400, 800]
MA_C = [32000, 64000, 128000, 256000]


def load(prefix):
    g = defaultdict(list)
    for p in glob.glob(f'results/run_logs/{prefix}_bs*/metrics.json'):
        name = p.split('/')[-2]
        m = re.match(rf'{prefix}_bs(\d+)_ma(\d+)_r(\d+)', name)
        if not m:
            continue
        d = json.load(open(p))
        g[(int(m.group(1)), int(m.group(2)))].append(
            (d['tps'], d['latency_ms_mean']))
    return g


def agg(g):
    return {k: (st.mean(x[0] for x in v),
                st.mean(x[1] for x in v),
                (max(x[0] for x in v) - min(x[0] for x in v))
                / st.mean(x[0] for x in v) * 100)
            for k, v in g.items()}


def main():
    C = agg(load('SC'))
    B = agg(load('SB'))

    for title, idx, fmt in (('throughput (tps)', 0, ',.0f'),
                            ('mean latency (ms)', 1, ',.1f'),
                            ('rep spread (%)', 2, '.1f')):
        print(f'\n=== Stage C {title} ===')
        print('bs \\ ma  ' + ''.join(f'{m:>11}' for m in MA_C))
        for bs in BS:
            line = f'{bs:<9}'
            for ma in MA_C:
                line += (f'{C[(bs, ma)][idx]:>11{fmt}}'
                         if (bs, ma) in C else f'{".":>11}')
            print(line)

    print('\n=== overlap check: ma=32000, Stage B vs Stage C ===')
    print(f'  {"bs":<7}{"Stage B":>11}{"Stage C":>11}{"diff":>9}')
    for bs in BS:
        k = (bs, 32000)
        if k in B and k in C:
            b, c = B[k][0], C[k][0]
            print(f'  {bs:<7}{b:>11,.0f}{c:>11,.0f}{100 * (c - b) / b:>8.1f}%')

    print('\n=== along max_async, at fixed block_size (Stage C) ===')
    for bs in BS:
        row = [(ma, C[(bs, ma)][0]) for ma in MA_C if (bs, ma) in C]
        if len(row) < 2:
            continue
        seq = '  '.join(f'{ma // 1000}k:{t:,.0f}' for ma, t in row)
        lo, hi = row[0][1], row[-1][1]
        print(f'  bs={bs:<5} {seq}   first->last {100 * (hi - lo) / lo:+.1f}%')

    allc = {**B, **C}
    sp = sorted(c[2] for c in C.values())
    n = len(sp)
    print(f'\nStage C rep spread over {n} cells: '
          f'median {sp[n // 2]:.1f}%, max {sp[-1]:.1f}%')
    best = max(allc.items(), key=lambda kv: kv[1][0])
    print(f'highest cell across B+C: bs={best[0][0]} ma={best[0][1]}  '
          f'{best[1][0]:,.0f} tps')
    bestc = max(C.items(), key=lambda kv: kv[1][0])
    print(f'highest cell in C only : bs={bestc[0][0]} ma={bestc[0][1]}  '
          f'{bestc[1][0]:,.0f} tps')


if __name__ == '__main__':
    main()
