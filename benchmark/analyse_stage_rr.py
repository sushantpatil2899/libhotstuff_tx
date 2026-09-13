#!/usr/bin/env python3
"""rr pacemaker shakedown: does a rotating leader work at all, and who leads?

B3 (bs1600 c8 ma1000), 4 cases x 3 reps, built with HOTSTUFF_PROTO_LOG=ON so
the pacemaker's rotation lines are in the replica logs:

    dummyctl    fixed proposer, no delay  -- the logged-build reference
    rrctl       rr, no delay
    rrlead200   rr, replica 1 delayed 200ms (the fixed-proposer position)
    rrfoll200   rr, replica 0 delayed 200ms

Which replica proposes under rr is an outcome, not a setting, so this reads
it out of the logs rather than assuming it.
"""
import glob
import json
import os
import re
import statistics as st
from collections import Counter, defaultdict

CASES = ('dummyctl', 'rrctl', 'rrlead200', 'rrfoll200')

# Anchored to this probe's four case labels: the earlier high-variance
# re-run (section 8) also used an RR_ prefix (RR_bs1600_c8_ma64000_r1),
# and a looser pattern picks those up as extra cases.
R = defaultdict(list)
for d in sorted(glob.glob('results/run_logs/RR_*')):
    m = re.match(r'RR_(' + '|'.join(CASES) + r')_r(\d+)$',
                 os.path.basename(d))
    if not m:
        continue
    rec = {'dir': d, 'rep': int(m[2])}
    mp = os.path.join(d, 'metrics.json')
    if os.path.exists(mp):
        rec.update(json.load(open(mp)))
    rot, stop = Counter(), Counter()
    for lf in sorted(glob.glob(os.path.join(d, 'replica-*.log'))):
        txt = open(lf, errors='replace').read()
        rot.update(re.findall(r'Pacemaker: rotate to (\d+)', txt))
        stop.update(re.findall(r'Pacemaker: stop rotation at (\d+)', txt))
    rec['rotate_to'] = dict(rot)
    rec['stop_at'] = dict(stop)
    rec['n_rotations'] = sum(rot.values())
    R[m[1]].append(rec)

print(f'{sum(len(v) for v in R.values())} runs, {len(R)} cases\n')
print(f'{"case":<12}{"n":>3}{"tps median":>13}{"lat ms":>9}{"spread":>8}'
      f'{"rotations":>11}  settled proposer (count over reps)')
for case in CASES:
    v = [x for x in R.get(case, []) if 'tps' in x]
    if not v:
        print(f'{case:<12}  no parsed runs')
        continue
    tps = [x['tps'] for x in v]
    settled = Counter()
    for x in v:
        for k, n in x['stop_at'].items():
            settled[k] += n
    print(f'{case:<12}{len(v):>3}{st.median(tps):>13,.0f}'
          f'{st.median(x["latency_ms_mean"] for x in v):>9.1f}'
          f'{(max(tps) - min(tps)) / st.mean(tps) * 100:>7.1f}%'
          f'{st.median(x["n_rotations"] for x in v):>11.0f}'
          f'  {dict(settled) or "none logged"}')

print('\nper run:')
for case in CASES:
    for x in sorted(R.get(case, []), key=lambda x: x['rep']):
        tps = f'{x["tps"]:,.0f}' if 'tps' in x else 'NO METRICS'
        lat = f'{x["latency_ms_mean"]:.1f} ms' if 'tps' in x else ''
        print(f'  {case:<12} r{x["rep"]}  {tps:>12} {lat:>10}  '
              f'rotate_to={x["rotate_to"]}  stop_at={x["stop_at"]}')
