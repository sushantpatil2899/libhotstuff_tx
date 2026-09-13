#!/usr/bin/env python3
"""Stage K: fewer physical cores on selected replicas, at B1-B4.

Reports, in order:
  1. pinning verification: for every run, every sample in the steady
     window must show each pinned replica's process AND all its threads
     allowed exactly CPUs 1-N, and each unpinned replica allowed all CPUs
  2. per baseline: the control, then each scenario x core level --
     tps_steady and latency medians, change against the control, stalled
     runs, rep spread, the rep-spread verdict, and on the pinned replicas
     the median cores used, busiest thread and host CPU pressure
  3. cells whose mean latency reached 8 s, where a 10 s warm-up in a 60 s
     run may not reach steady state (as in Stage Q)

5 reps per cell, so this is a screen. Verdicts use the rep-spread rule
(section 1 of BASELINE_ANALYSIS.md).
"""
import glob
import json
import os
import re
import statistics as st
from collections import defaultdict

W0, W1 = 15.0, 55.0
PAT = re.compile(r'K_(B\d)_(ctl|lead_f0_f3|lead_f0|lead_f3|lead|f0|f3)'
                 r'_c(\d+)_r(\d+)$')
SCEN = {'lead': (1,), 'f0': (0,), 'f3': (3,), 'lead_f0': (1, 0),
        'lead_f3': (1, 3), 'lead_f0_f3': (1, 0, 3)}
LABEL = {'lead': 'leader', 'f0': 'follower 0', 'f3': 'follower 3',
         'lead_f0': 'leader + follower 0', 'lead_f3': 'leader + follower 3',
         'lead_f0_f3': 'leader + followers 0, 3'}
BASE = {'B1': 'bs200 c2 ma1000', 'B2': 'bs800 c4 ma1000',
        'B3': 'bs1600 c8 ma1000', 'B4': 'bs3200 c8 ma4000'}


def replica_file(path, expect_cpus):
    """Steady-window rates for one replica host and its pinning check."""
    lines = [json.loads(l) for l in open(path) if l.strip()]
    tck = lines[0]['header']['clk_tck']
    ncpu = lines[0]['header']['ncpu']
    S = [x for x in lines[1:] if 't' in x and W0 <= x['t'] <= W1]
    if len(S) < 2:
        return None
    expected = expect_cpus or f'0-{ncpu - 1}'
    bad = 0
    for s in S:
        for p in s['procs'].values():
            if p.get('cpus') != expected or p.get('thread_cpus') != [expected]:
                bad += 1
    a, b = S[0], S[-1]
    dt = b['t'] - a['t']
    pids = set(a['procs']) & set(b['procs'])
    cores = sum(b['procs'][p]['ticks'] - a['procs'][p]['ticks']
                for p in pids) / tck / dt
    busiest = 0.0
    for p in pids:
        ta, tb = a['procs'][p]['threads'], b['procs'][p]['threads']
        for tid in set(ta) & set(tb):
            busiest = max(busiest, (tb[tid][1] - ta[tid][1]) / tck / dt * 100)
    psi = (b['psi'].get('some', 0) - a['psi'].get('some', 0)) / (dt * 1e6) * 100
    return {'ok': bad == 0 and len(pids) == 1, 'bad_samples': bad,
            'nprocs': len(pids), 'cores': cores, 'busiest': busiest,
            'psi': psi}


runs = defaultdict(list)
pin_ok = pin_bad = 0
pin_detail = []
for d in sorted(glob.glob('results/run_logs/K_*')):
    m = PAT.match(os.path.basename(d))
    mp = os.path.join(d, 'metrics.json')
    if not m or not os.path.exists(mp):
        continue
    b, s, n = m[1], m[2], int(m[3])
    pinned = SCEN.get(s, ())
    hosts, ok = {}, True
    for i in range(4):
        f = os.path.join(d, f'compute-replica-{i}.jsonl')
        # Linux prints a one-CPU list as '1', not '1-1'.
        exp = (f'1-{n}' if n > 1 else '1') if i in pinned else None
        h = replica_file(f, exp) if os.path.exists(f) else None
        if h is None or not h['ok']:
            ok = False
            pin_detail.append(f'{os.path.basename(d)} replica {i}: '
                              f'{"no samples" if h is None else h}')
        hosts[i] = h
    pin_ok += ok
    pin_bad += not ok
    runs[(b, s, n)].append((json.load(open(mp)), hosts))

total = sum(len(v) for v in runs.values())
print(f'Stage K: {total} runs, {len(runs)} cells')
print(f'\n=== 1. pinning verification === runs passing: {pin_ok}  '
      f'failing: {pin_bad}')
for x in pin_detail[:15]:
    print(f'    {x}')


def agg(v):
    clean = [met for met, _ in v if not met.get('stalled')]
    t = [x['tps_steady'] for x in clean]
    return {
        'tps': st.median(t) if t else 0.0,
        'lat': st.median(x['latency_ms_mean_steady'] for x in clean)
        if clean else 0.0,
        'spread': (max(t) - min(t)) / st.mean(t) * 100
        if len(t) > 1 and st.mean(t) else 0.0,
        'stalled': len(v) - len(clean), 'n': len(v),
    }


slow = []
print('\n=== 2. per baseline (medians over non-stalled runs) ===')
for b in BASE:
    ctl = runs.get((b, 'ctl', 0))
    if not ctl:
        continue
    c = agg(ctl)
    print(f'\n########## {b} {BASE[b]} ##########')
    print(f'  control: {c["tps"]:>10,.0f} tps  {c["lat"]:>8.1f} ms  '
          f'spread {c["spread"]:.1f}%  stalled {c["stalled"]}/{c["n"]}')
    for s in SCEN:
        print(f'  --- {LABEL[s]} pinned ---')
        print(f'     {"cores":>5}{"tps":>11}{"vs ctl":>9}{"lat ms":>10}'
              f'{"vs ctl":>9}{"spread":>8}{"stall":>7}  verdict'
              f'{"":>6}pinned: cores used / busiest thr % / host psi %')
        for n in (8, 6, 4, 3, 2, 1):
            v = runs.get((b, s, n))
            if not v:
                continue
            x = agg(v)
            sep = abs(x['tps'] - c['tps']) / st.mean([x['tps'], c['tps']]) * 100 \
                if x['tps'] else 100.0
            res = 'RESOLVABLE' if sep > max(x['spread'], c['spread']) else 'not resolvable'
            pin = []
            for i in SCEN[s]:
                hs = [h[i] for _, h in v if h.get(i)]
                if hs:
                    pin.append(f'r{i} {st.median(h["cores"] for h in hs):.2f}/'
                               f'{st.median(h["busiest"] for h in hs):.0f}/'
                               f'{st.median(h["psi"] for h in hs):.1f}')
            print(f'     {n:>5}{x["tps"]:>11,.0f}'
                  f'{(x["tps"] - c["tps"]) / c["tps"] * 100:>8.1f}%'
                  f'{x["lat"]:>10.1f}'
                  f'{(x["lat"] - c["lat"]) / c["lat"] * 100 if c["lat"] else 0:>8.0f}%'
                  f'{x["spread"]:>7.1f}%{x["stalled"]:>4}/{x["n"]}  {res:<15}'
                  f'{"  ".join(pin)}')
            if x['lat'] >= 8000:
                slow.append((b, s, n, x['lat']))

print('\n=== 3. cells with mean latency >= 8 s (warm-up may be too short) ===')
for b, s, n, lat in slow:
    print(f'  {b} {LABEL[s]} {n} cores: {lat / 1000:.1f} s')
if not slow:
    print('  none')
