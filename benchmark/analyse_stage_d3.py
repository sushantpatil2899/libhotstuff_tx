#!/usr/bin/env python3
"""Stage D3: block_size x num_clients x max_async.

Reports measurements only, plus a mechanical edge check.

Edge rule: for each axis, compare the top level against the level below
it at the SAME other coordinates. If the gain exceeds the rep spread of
the two cells compared, that edge has not saturated at those
coordinates. Applied per slice, not to the grid average, because
saturation was already observed to depend on location.
"""
import glob
import json
import re
import statistics as st
from collections import defaultdict

BS = [200, 400, 800, 1600, 3200]
NC = [1, 2, 4, 8, 16]
MA = [1000, 4000, 16000, 64000]


def load():
    g = defaultdict(list)
    for p in glob.glob('results/run_logs/D3_bs*/metrics.json'):
        m = re.match(r'D3_bs(\d+)_c(\d+)_ma(\d+)_r(\d+)', p.split('/')[-2])
        if not m:
            continue
        d = json.load(open(p))
        g[(int(m.group(1)), int(m.group(2)), int(m.group(3)))].append(
            (d['tps'], d['latency_ms_mean']))
    return {k: (st.mean(x[0] for x in v),
                st.mean(x[1] for x in v),
                (max(x[0] for x in v) - min(x[0] for x in v))
                / st.mean(x[0] for x in v) * 100)
            for k, v in g.items()}


def main():
    C = load()
    print(f'cells with data: {len(C)}')

    for ma in MA:
        print(f'\n=== tps @ max_async={ma:,} per client '
              f'(rows block_size, cols clients) ===')
        print('  bs \\ c ' + ''.join(f'{c:>11}' for c in NC))
        for bs in BS:
            line = f'  {bs:<6}'
            for nc in NC:
                k = (bs, nc, ma)
                line += f'{C[k][0]:>11,.0f}' if k in C else f'{".":>11}'
            print(line)

    top = sorted(C.items(), key=lambda kv: -kv[1][0])[:10]
    print('\n=== top 10 cells ===')
    print(f'  {"bs":>6}{"clients":>9}{"max_async":>11}{"tps":>11}'
          f'{"lat ms":>10}{"spread":>9}')
    for (bs, nc, ma), (t, l, sp) in top:
        print(f'  {bs:>6}{nc:>9}{ma:>11,}{t:>11,.0f}{l:>10,.1f}{sp:>8.1f}%')

    sp = sorted(v[2] for v in C.values())
    n = len(sp)
    print(f'\nrep spread over {n} cells: median {sp[n // 2]:.1f}%, '
          f'p90 {sp[int(n * .9)]:.1f}%, max {sp[-1]:.1f}%')

    # ---- mechanical edge check ----
    print('\n=== EDGE CHECK: is the top level still rising? ===')
    print('(gain vs the level below, at identical other coordinates;'
          ' "rising" = gain > spread of both cells)')
    axes = [('block_size', BS, lambda v, o: (v, o[0], o[1]),
             [(c, m) for c in NC for m in MA]),
            ('clients', NC, lambda v, o: (o[0], v, o[1]),
             [(b, m) for b in BS for m in MA]),
            ('max_async', MA, lambda v, o: (o[0], o[1], v),
             [(b, c) for b in BS for c in NC])]
    for name, levels, mk, others in axes:
        hi, lo = levels[-1], levels[-2]
        rising, flat, gains = [], 0, []
        for o in others:
            kh, kl = mk(hi, o), mk(lo, o)
            if kh not in C or kl not in C:
                continue
            gain = 100 * (C[kh][0] - C[kl][0]) / C[kl][0]
            thr = max(C[kh][2], C[kl][2])
            gains.append(gain)
            if gain > thr:
                rising.append((o, gain, thr))
            else:
                flat += 1
        print(f'\n  {name}: {hi} vs {lo}   '
              f'{len(rising)} rising / {flat} flat')
        if gains:
            print(f'     gains: min {min(gains):+.1f}%  '
                  f'median {sorted(gains)[len(gains) // 2]:+.1f}%  '
                  f'max {max(gains):+.1f}%')
        for o, gain, thr in sorted(rising, key=lambda r: -r[1])[:6]:
            print(f'     rising at {o}: {gain:+.1f}% (spread {thr:.1f}%)')
        if not rising:
            print('     -> saturated everywhere tested')


if __name__ == '__main__':
    main()
