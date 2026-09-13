#!/usr/bin/env python3
"""Re-run each stage's comparisons with stalled runs excluded.

A run is classified stalled when its first-to-last-commit window plus its
mean latency is under 55 s: the window is too short to be explained by
slow commits, so commits stopped early (see commit 2c3224d). Old runs
cannot be re-measured over a fixed window (their raw client logs were
truncated, then pruned), but every one can be classified from the fields
already in its results CSV.

Every comparison below is computed twice with the stage's original method:
  ALL    every run, which must reproduce the figures already published
         in BASELINE_ANALYSIS.md
  CLEAN  stalled runs excluded
and each line reports whether the verdict changed. Stalled runs are also
counted per cell, since how often a configuration stalls is itself a
finding.
"""
import csv
import re
import statistics as st
from collections import defaultdict
from itertools import combinations

WINDOW_PLUS_LATENCY_S = 55


def stalled(r):
    return (float(r['duration_s']) + float(r['latency_ms_mean']) / 1000
            < WINDOW_PLUS_LATENCY_S)


def load(stage, pattern):
    """{key tuple: [row, ...]} for rows whose run_id matches pattern."""
    cells = defaultdict(list)
    for r in csv.DictReader(open(f'results/{stage}_results.csv')):
        if not r.get('tps'):
            continue
        m = re.match(pattern, r['run_id'])
        if m:
            cells[m.groups()].append(r)
    return cells


def pick(cells, clean):
    return {k: [r for r in v if not (clean and stalled(r))]
            for k, v in cells.items()}


def tps(v):
    return [float(r['tps']) for r in v]


def lat(v):
    return [float(r['latency_ms_mean']) for r in v]


def spread(v):
    t = tps(v)
    return (max(t) - min(t)) / st.mean(t) * 100 if len(t) > 1 else 0.0


def mw(a, b):
    """Exact two-sided Mann-Whitney U p-value by full enumeration."""
    def u(x, y):
        return sum((i > j) + 0.5 * (i == j) for i in x for j in y)
    pool, n = a + b, len(a)
    mu = n * len(b) / 2
    obs = abs(u(a, b) - mu)
    hits = tot = 0
    for idx in combinations(range(len(pool)), n):
        s = set(idx)
        x = [pool[i] for i in idx]
        y = [pool[i] for i in range(len(pool)) if i not in s]
        tot += 1
        hits += abs(u(x, y) - mu) >= obs - 1e-9
    return hits / tot


def range_verdict(group):
    """Rep-spread rule on medians: separation must exceed worst spread."""
    meds = [st.median(tps(v)) for v in group]
    sep = (max(meds) - min(meds)) / st.mean(meds) * 100
    worst = max(spread(v) for v in group)
    return sep, worst, sep > worst


def mark(changed):
    return '  <-- CHANGED' if changed else ''


# ---------------------------------------------------------------- counts
print('=== 0. stalled runs per stage ===')
STAGES = {
    'stage_a': r'(.*)_r\d+$', 'stage_b': r'(.*)_r\d+$',
    'stage_c': r'(.*)_r\d+$', 'stage_d3': r'(.*)_r\d+$',
    'rerun_noisy': r'(.*)_r\d+$', 'stage_e': r'(.*)_r\d+$',
    'stage_f': r'(.*)_r\d+$', 'stage_g': r'(.*)_r\d+$',
    'stage_h': r'(.*)_r\d+$', 'stage_n': r'(.*)_r\d+$',
    'stage_o': r'(.*)_r\d+$', 'stage_p': r'(.*)_r\d+$',
}
for s, pat in STAGES.items():
    c = load(s, pat)
    runs = sum(len(v) for v in c.values())
    bad = {k[0]: sum(stalled(r) for r in v) for k, v in c.items()
           if any(stalled(r) for r in v)}
    print(f'  {s:<12} {runs:>4} runs  {sum(bad.values()):>3} stalled  '
          f'in {len(bad)} cells')
    for k, n in sorted(bad.items()):
        print(f'      {k:<36} {n}/{len(c[(k,)])}')

# --------------------------------------------------------------- D3 edge
print('\n=== 1. Stage D3 edge check (means, as in analyse_stage_d3.py) ===')
d3 = load('stage_d3', r'D3_bs(\d+)_c(\d+)_ma(\d+)_r\d+')
BS, NC, MA = [200, 400, 800, 1600, 3200], [1, 2, 4, 8, 16], \
    [1000, 4000, 16000, 64000]


def d3cells(clean):
    out = {}
    for (b, c, m), v in pick(d3, clean).items():
        if v:
            t = tps(v)
            out[(int(b), int(c), int(m))] = (
                st.mean(t), (max(t) - min(t)) / st.mean(t) * 100)
    return out


for name, levels, mk, others in (
        ('block_size', BS, lambda v, o: (v, o[0], o[1]),
         [(c, m) for c in NC for m in MA]),
        ('clients', NC, lambda v, o: (o[0], v, o[1]),
         [(b, m) for b in BS for m in MA]),
        ('max_async', MA, lambda v, o: (o[0], o[1], v),
         [(b, c) for b in BS for c in NC])):
    res = {}
    for clean in (False, True):
        C = d3cells(clean)
        rising = []
        n = 0
        for o in others:
            kh, kl = mk(levels[-1], o), mk(levels[-2], o)
            if kh in C and kl in C:
                n += 1
                gain = 100 * (C[kh][0] - C[kl][0]) / C[kl][0]
                if gain > max(C[kh][1], C[kl][1]):
                    rising.append(o)
        res[clean] = (len(rising), n - len(rising), sorted(rising))
    print(f'  {name:<11} ALL {res[False][0]} rising / {res[False][1]} flat'
          f'   CLEAN {res[True][0]} rising / {res[True][1]} flat'
          f'{mark(res[False][2] != res[True][2])}')
    if res[False][2] != res[True][2]:
        print(f'      rising ALL   {res[False][2]}')
        print(f'      rising CLEAN {res[True][2]}')

# ------------------------------------------------------- D3 + rerun cells
print('\n=== 2. Stage D3 / section 8 re-run: cells touched by stalls '
      '(median tps / median latency) ===')
rr = load('rerun_noisy', r'RR_bs(\d+)_c(\d+)_ma(\d+)_r\d+')
for label, cells in (('D3', d3), ('re-run', rr)):
    for k, v in sorted(cells.items(), key=lambda kv: tuple(map(int, kv[0]))):
        if not any(stalled(r) for r in v):
            continue
        a, c = v, [r for r in v if not stalled(r)]
        cm = f'{st.median(tps(c)):>9,.0f} @ {st.median(lat(c)):>7.1f} ms' \
            if c else 'no clean run'
        print(f'  {label:<7} bs{k[0]:<5} c{k[1]:<3} ma{k[2]:<6} '
              f'stalled {len(a) - len(c)}/{len(a)}   '
              f'ALL {st.median(tps(a)):>9,.0f} @ {st.median(lat(a)):>7.1f} ms'
              f'   CLEAN {cm}   spread {spread(a):.1f}% -> '
              f'{spread(c) if c else 0:.1f}%')

# ------------------------------------------------------------ Stage E
print('\n=== 3. Stage E factor verdicts (rep-spread rule on medians) ===')
E = load('stage_e', r'E_(B\d)_t(\d+)_skew([\d.]+)_mtx([\d.]+)_r\d+')
for b in ('B1', 'B2', 'B3', 'B4'):
    for fname, keys in (
            ('threads', [(b, t, '0.1', '0.9') for t in ('2', '4', '8', '16')]),
            ('skew', [(b, '4', s, '0.9') for s in ('0.1', '0.5', '0.9')]),
            ('write ratio', [(b, '4', '0.1', m) for m in ('0.1', '0.5', '0.9')])):
        out = {}
        for clean in (False, True):
            P = pick(E, clean)
            out[clean] = range_verdict([P[k] for k in keys])
        touched = any(stalled(r) for k in keys for r in E[k])
        if touched:
            print(f'  {b} {fname:<12} ALL sep {out[False][0]:.1f}% vs '
                  f'{out[False][1]:.1f}% -> {"RES" if out[False][2] else "not"}'
                  f'   CLEAN sep {out[True][0]:.1f}% vs {out[True][1]:.1f}% -> '
                  f'{"RES" if out[True][2] else "not"}'
                  f'{mark(out[False][2] != out[True][2])}')

# ------------------------------------------------------------ Stage F
print('\n=== 4. Stage F rank tests (bar p < 0.05/13 = 0.0038) ===')
F = load('stage_f', r'F_(B\d)_t(\d+)_skew([\d.]+)_mtx([\d.]+)_r\d+')
FP = [(('B3', '2', '0.1', '0.9'), ('B3', '4', '0.1', '0.9')),
      (('B3', '4', '0.1', '0.9'), ('B3', '8', '0.1', '0.9')),
      (('B3', '2', '0.1', '0.9'), ('B3', '8', '0.1', '0.9')),
      (('B3', '4', '0.1', '0.9'), ('B3', '4', '0.9', '0.9'))]
for b in ('B1', 'B2', 'B4'):
    FP += [((b, '4', '0.1', x), (b, '4', '0.1', y))
           for x, y in (('0.1', '0.9'), ('0.1', '0.5'), ('0.5', '0.9'))]
for ka, kb in FP:
    touched = any(stalled(r) for r in F[ka] + F[kb])
    if not touched:
        continue
    res = {}
    for clean in (False, True):
        P = pick(F, clean)
        res[clean] = (mw(tps(P[ka]), tps(P[kb])), st.median(tps(P[ka])),
                      st.median(tps(P[kb])), len(P[ka]), len(P[kb]))
    ca, cb = res[False][0] < 0.0038, res[True][0] < 0.0038
    print(f'  {ka} vs {kb[3] if kb[0] == ka[0] and kb[1] == ka[1] else kb}\n'
          f'      ALL   n={res[False][3]}/{res[False][4]} medians '
          f'{res[False][1]:,.0f} vs {res[False][2]:,.0f}  p={res[False][0]:.4f}'
          f' {"CONF" if ca else "not"}\n'
          f'      CLEAN n={res[True][3]}/{res[True][4]} medians '
          f'{res[True][1]:,.0f} vs {res[True][2]:,.0f}  p={res[True][0]:.4f}'
          f' {"CONF" if cb else "not"}{mark(ca != cb)}')
b4 = F[('B4', '4', '0.1', '0.9')]
print(f'  adopted B4 (section 10b), 7-rep median: ALL {st.median(tps(b4)):,.0f}'
      f' @ {st.median(lat(b4)):.1f} ms   CLEAN '
      f'{st.median(tps([r for r in b4 if not stalled(r)])):,.0f} @ '
      f'{st.median(lat([r for r in b4 if not stalled(r)])):.1f} ms')

# ------------------------------------------------------------ Stage G
print('\n=== 5. Stage G verdicts touched by stalls (rep-spread rule) ===')
G = load('stage_g', r'G_bs(\d+)_c(\d+)_ma(\d+)_t(\d+)_mtx([\d.]+)_r\d+')


def g_compare(label, groups):
    touched = any(stalled(r) for g in groups for r in G[g])
    if not touched:
        return 0
    out = {}
    for clean in (False, True):
        P = pick(G, clean)
        if any(not P[g] for g in groups):
            out[clean] = None
            continue
        out[clean] = range_verdict([P[g] for g in groups]) + (
            [st.median(tps(P[g])) for g in groups],)
    a, c = out[False], out[True]
    cv = 'no clean run' if c is None else \
        f'{"RES" if c[2] else "not"} {[round(x) for x in c[3]]}'
    changed = c is None or a[2] != c[2]
    print(f'  {label}\n      ALL   {"RES" if a[2] else "not"} '
          f'{[round(x) for x in a[3]]}\n      CLEAN {cv}{mark(changed)}')
    return int(changed)


n6400 = 0
for (bs, c, ma, t, m) in sorted(G, key=lambda k: tuple(map(float, k))):
    if bs == '6400' and ('3200', c, ma, t, m) in G:
        n6400 += g_compare(f'6400 vs 3200 at c{c} ma{ma} t{t} mtx{m}',
                           [('3200', c, ma, t, m), (bs, c, ma, t, m)])
for (bs, c, ma, m) in sorted({(k[0], k[1], k[2], k[4]) for k in G}):
    g_compare(f'threads at bs{bs} c{c} ma{ma} mtx{m}',
              [(bs, c, ma, t, m) for t in ('2', '4', '8') if (bs, c, ma, t, m) in G])
for (bs, c, ma, t) in sorted({k[:4] for k in G}):
    g_compare(f'write ratio at bs{bs} c{c} ma{ma} t{t}',
              [(bs, c, ma, t, m) for m in ('0.1', '0.9')])

# ------------------------------------------------------------ Stage H
print('\n=== 6. Stage H rank tests (bar p < 0.05/4 = 0.0125) ===')
H = load('stage_h', r'H_bs(\d+)_c(\d+)_ma(\d+)_r\d+')
for ka, kb in ((('3200', '16', '1000'), ('3200', '8', '4000')),
               (('6400', '16', '4000'), ('3200', '16', '4000'))):
    for metric, fn in (('tps', tps), ('latency', lat)):
        res = {}
        for clean in (False, True):
            P = pick(H, clean)
            res[clean] = (mw(fn(P[ka]), fn(P[kb])), st.median(fn(P[ka])),
                          st.median(fn(P[kb])), len(P[ka]), len(P[kb]))
        a, c = res[False][0] < 0.0125, res[True][0] < 0.0125
        print(f'  bs{ka[0]} c{ka[1]} ma{ka[2]} vs bs{kb[0]} c{kb[1]} ma{kb[2]}'
              f' {metric:<8} ALL n={res[False][3]}/{res[False][4]} '
              f'{res[False][1]:,.1f} vs {res[False][2]:,.1f} p={res[False][0]:.4f}'
              f' {"CONF" if a else "not"}   CLEAN n={res[True][3]}/'
              f'{res[True][4]} {res[True][1]:,.1f} vs {res[True][2]:,.1f} '
              f'p={res[True][0]:.4f} {"CONF" if c else "not"}{mark(a != c)}')
