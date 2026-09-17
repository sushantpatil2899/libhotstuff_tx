#!/usr/bin/env python3
"""Stage MH: is the lost block a beat discarded by a rejected promise?

Per run:
  stuck        commands still waiting at client shutdown, with their replies
  blocks       assembled vs resolved on each replica, and the assembled
               block whose first command is stuck
  discarded    "diag beat discarded at <site>" lines, which fire when a beat
               already popped from pending_beats loses its pm_qc_finish wait
  distortion   this run's throughput and latency against Stage LT5, the same
               cells with no diagnostic, plus the extra log volume
"""
import glob
import gzip
import json
import os
import re
from collections import defaultdict
from datetime import datetime

# Stage LT5 medians, same cells, no diagnostic (FAILURE_ANALYSIS.md 6).
LT5 = {'B1': dict(normal=165805, after=145439, lat=13.4),
       'B4': dict(normal=433081, after=363805, lat=80.0)}
CAP = {'B1': 2000, 'B4': 32000}
PAT = re.compile(r'MH_(B\d)_(lead_crash|lead_freeze)_r(\d)$')
RE_STUCK = re.compile(r'\[hotstuff stuckcmd\] cmd=(\w+) confirmed=(\d+) sent=(-?[0-9.]+)')
RE_ASM = re.compile(r'^(\S+ \S+) \[hotstuff proto\] diag beat assembled first=(\w+) n=(\d+)')
RE_RES = re.compile(r'^(\S+ \S+) \[hotstuff proto\] diag beat resolved first=(\w+)')
RE_DIS = re.compile(r'^(\S+ \S+) \[hotstuff proto\] diag beat discarded at (\w+)')
RE_REP = re.compile(r'^(\S+ \S+) \[hotstuff proto\] reproposing pending commands')
RE_ROT = re.compile(r'^(\S+ \S+) \[hotstuff proto\] Pacemaker: rotate to (\d+)')


def ts(s):
    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S.%f').timestamp()


def open_log(d, i):
    f = os.path.join(d, f'replica-{i}.log')
    if os.path.exists(f):
        return open(f, errors='replace'), os.path.getsize(f)
    g = f + '.gz'
    if os.path.exists(g):
        return gzip.open(g, 'rt', errors='replace'), os.path.getsize(g)
    return None, 0


def main():
    for d in sorted(glob.glob('results/run_logs/MH_*')):
        m = PAT.match(os.path.basename(d))
        if not m or not os.path.exists(os.path.join(d, 'metrics.json')):
            continue
        b = m[1]
        T = json.load(open(os.path.join(d, 'failure-replica-0.json')))['injected_epoch']
        met = json.load(open(os.path.join(d, 'metrics.json')))
        stuck = {}
        for f in glob.glob(os.path.join(d, 'client-*.log')):
            for line in open(f, errors='replace'):
                s = RE_STUCK.search(line)
                if s:
                    stuck[s[1]] = (int(s[2]), float(s[3]))
        asm, res, dis, reps, rots, vol = {}, defaultdict(set), [], [], [], 0
        for i in range(4):
            fh, size = open_log(d, i)
            vol += size
            if fh is None:
                continue
            for line in fh:
                a = RE_ASM.match(line)
                if a:
                    asm[(i, a[2])] = (ts(a[1]) - T, int(a[3]))
                    continue
                r = RE_RES.match(line)
                if r:
                    res[i].add(r[2])
                    continue
                x = RE_DIS.match(line)
                if x:
                    dis.append((ts(x[1]) - T, i, x[2]))
                    continue
                if RE_REP.match(line):
                    reps.append((ts(line[:26]) - T, i))
                    continue
                o = RE_ROT.match(line)
                if o:
                    rots.append((ts(o[1]) - T, int(o[2])))
        steps = []
        for _, r in sorted(rots):
            if not steps or steps[-1] != r:
                steps.append(r)
        print(f'=== {os.path.basename(d)}  stuck {len(stuck):,}  '
              f'replies {sorted({v[0] for v in stuck.values()}) if stuck else "-"}  '
              f're-proposals {len(reps)}  rotations {steps}')
        print(f'    throughput {met.get("tps_steady"):,.0f} vs LT5 {LT5[b]["after"]:,} '
              f'(no failure {LT5[b]["normal"]:,}); latency {met.get("latency_ms_mean_steady")} ms '
              f'vs {LT5[b]["lat"]} ms; replica logs {vol / 1e6:.0f} MB')
        unresolved = [(k, v) for k, v in asm.items() if k[1] not in res[k[0]]]
        held = [(k, v) for k, v in unresolved if k[1] in stuck]
        print(f'    blocks assembled {len(asm):,}, never resolved {len(unresolved)}, '
              f'of those holding a stuck command {len(held)}')
        for (i, h), (t, n) in sorted(held, key=lambda kv: kv[1][0]):
            print(f'      r{i} block first={h} assembled T{t:+.4f} n={n}')
        for t, i, site in sorted(dis):
            print(f'      r{i} beat discarded at {site}: T{t:+.4f}')


if __name__ == '__main__':
    main()
