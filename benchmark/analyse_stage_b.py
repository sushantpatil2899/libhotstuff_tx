#!/usr/bin/env python3
"""Stage B: block_size x max_async surface.

Reports measurements only. Rep spread is (max-min)/mean over the 3 reps
of a cell and is the reference for whether a difference between cells is
larger than the run-to-run variation observed here.
"""
import glob
import json
import re
import statistics as st
from collections import defaultdict

BS = [100, 200, 400, 800, 1600]
MA = [500, 1000, 2000, 4000, 8000, 16000, 32000]


def main():
    g = defaultdict(list)
    for p in glob.glob('results/run_logs/SB_bs*/metrics.json'):
        name = p.split('/')[-2]
        m = re.match(r'SB_bs(\d+)_ma(\d+)_r(\d+)', name)
        if not m:
            continue
        d = json.load(open(p))
        g[(int(m.group(1)), int(m.group(2)))].append(
            (d['tps'], d['latency_ms_mean']))

    cells = {k: (st.mean(x[0] for x in v),
                 st.mean(x[1] for x in v),
                 (max(x[0] for x in v) - min(x[0] for x in v))
                 / st.mean(x[0] for x in v) * 100)
             for k, v in g.items()}

    for title, idx in (('throughput (tps)', 0),
                       ('mean latency (ms)', 1),
                       ('rep spread (%)', 2)):
        print(f'\n=== {title} ===')
        print('bs \\ ma  ' + ''.join(f'{m:>10}' for m in MA))
        for bs in BS:
            line = f'{bs:<9}'
            for ma in MA:
                if (bs, ma) in cells:
                    v = cells[(bs, ma)][idx]
                    line += f'{v:>10,.0f}' if idx == 0 else f'{v:>10.1f}'
                else:
                    line += f'{".":>10}'
            print(line)

    sp = sorted(c[2] for c in cells.values())
    n = len(sp)
    print(f'\nrep spread over {n} cells: median {sp[n // 2]:.1f}%, '
          f'max {sp[-1]:.1f}%')
    best = max(cells.items(), key=lambda kv: kv[1][0])
    worst = min(cells.items(), key=lambda kv: kv[1][0])
    print(f'highest cell: bs={best[0][0]} ma={best[0][1]}  '
          f'{best[1][0]:,.0f} tps')
    print(f'lowest  cell: bs={worst[0][0]} ma={worst[0][1]}  '
          f'{worst[1][0]:,.0f} tps')
    print(f'range across all cells: '
          f'{100 * (best[1][0] - worst[1][0]) / worst[1][0]:.1f}%')

    # Per-axis reads, holding the other axis fixed.
    print('\n=== along max_async, at fixed block_size ===')
    for bs in BS:
        row = [(ma, cells[(bs, ma)][0]) for ma in MA if (bs, ma) in cells]
        if len(row) < 2:
            continue
        seq = '  '.join(f'{ma}:{t:,.0f}' for ma, t in row)
        lo, hi = row[0][1], row[-1][1]
        print(f'  bs={bs:<5} {seq}   first->last {100 * (hi - lo) / lo:+.1f}%')

    print('\n=== along block_size, at fixed max_async ===')
    for ma in MA:
        col = [(bs, cells[(bs, ma)][0]) for bs in BS if (bs, ma) in cells]
        if len(col) < 2:
            continue
        seq = '  '.join(f'{bs}:{t:,.0f}' for bs, t in col)
        lo, hi = col[0][1], col[-1][1]
        print(f'  ma={ma:<6} {seq}   first->last {100 * (hi - lo) / lo:+.1f}%')


if __name__ == '__main__':
    main()
