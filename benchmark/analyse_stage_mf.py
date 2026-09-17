#!/usr/bin/env python3
"""Stage MF: unconfirmed commands after a leader failure, per run.

  stuck     sum over clients of "[hotstuff waiting] ... over10s=", read at
            shutdown: commands outstanding for more than 10 s, far above any
            normal latency (the total n is always clients x max_async in a
            closed loop and says nothing)
  inferred  clients x max_async - (commits/s x mean latency) over
            [T+40, T+76), the estimate FAILURE_ANALYSIS.md 13 used
  blocks    every "decided block X height H: N cmds, M answered" line from
            T-2 s on, for blocks where some surviving replica answered fewer
            than all N. (A threshold on the total across replicas hides
            commands answered by one replica among others answered by
            three.) A re-proposed block legitimately repeats commands
            already answered, so a short count is not by itself a loss; the
            per-replica counts are printed so each case can be read.

Replica 0 is the failed leader. A SIGKILL or SIGSTOP stops its log where it
stands, so its lines can be missing for blocks it did answer.
"""
import glob
import gzip
import json
import os
import re
from collections import defaultdict
from datetime import datetime

CAP = {'B1': 2000, 'B2': 4000, 'B3': 8000, 'B4': 32000}
PAT = re.compile(r'MF_(B\d)_(lead_crash|lead_freeze)_r(\d)$')
RE_S = re.compile(r'\[hotstuff steady\] start=([0-9.]+)')
RE_B = re.compile(r'\[hotstuff buckets\] counts=([0-9,]+)')
RE_L = re.compile(r'\[hotstuff latsums\] seconds=([0-9.,]+)')
RE_W = re.compile(r'\[hotstuff waiting\] n=(\d+) over1s=(\d+) over10s=(\d+) sent=(\d+) '
                  r'stuck_sent_min=(-?[0-9.]+) stuck_sent_med=(-?[0-9.]+) stuck_sent_max=(-?[0-9.]+)')
RE_D = re.compile(r'^(\S+ \S+) \[hotstuff proto\] decided block (\w+) height (\d+): '
                  r'(\d+) cmds, (\d+) answered')
RE_R = re.compile(r'^(\S+ \S+) \[hotstuff proto\] (reproposing pending commands|'
                  r'Pacemaker: rotate to (\d+))')


def ts(s):
    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S.%f').timestamp()


def clients(run_dir):
    per = defaultdict(list)
    for line in open(os.path.join(run_dir, 'summaries.txt')):
        name, _, rest = line.partition(': ')
        per[name].append(rest)
    return ['\n'.join(v) for v in per.values()]


def main():
    for d in sorted(glob.glob('results/run_logs/MF_*')):
        m = PAT.match(os.path.basename(d))
        if not m or not os.path.exists(os.path.join(d, 'metrics.json')):
            continue
        b = m[1]
        T = json.load(open(os.path.join(d, 'failure-replica-0.json')))['injected_epoch']
        texts = clients(d)
        waits = [RE_W.search(t) for t in texts]
        stuck = sum(int(w[3]) for w in waits if w)
        over1 = sum(int(w[2]) for w in waits if w)
        c = l = 0
        for t in texts:
            ms, mb, ml = RE_S.search(t), RE_B.search(t), RE_L.search(t)
            if not (ms and mb and ml):
                continue
            s0 = int(float(ms[1]))
            for i, (x, y) in enumerate(zip(mb[1].split(','), ml[1].split(','))):
                if int(T) + 40 <= s0 + i < int(T) + 76:
                    c += int(x)
                    l += float(y)
        inferred = CAP[b] - (c / 36) * (l / c) if c >= 36000 else None
        blocks = defaultdict(dict)
        events = []
        for i in range(4):
            f = os.path.join(d, f'replica-{i}.log')
            fh = open(f, errors='replace') if os.path.exists(f) else (
                gzip.open(f + '.gz', 'rt', errors='replace') if os.path.exists(f + '.gz') else None)
            if fh is None:
                continue
            for line in fh:
                md = RE_D.match(line)
                if md:
                    t = ts(md[1]) - T
                    if t >= -2:
                        blocks[md[2]][i] = (t, int(md[3]), int(md[4]), int(md[5]))
                    continue
                mr = RE_R.match(line)
                if mr and ts(mr[1]) > T:
                    events.append((ts(mr[1]) - T, i, mr[2]))
        inf = '-' if inferred is None else f'{inferred:,.0f}'
        print(f'=== {os.path.basename(d)}  stuck >10 s {stuck:,}  >1 s {over1:,} '
              f'(clients reporting {sum(1 for w in waits if w)}/{len(texts)})  '
              f'inferred {inf}')
        # Send times of stuck commands, from each client's own run_start,
        # shown relative to the injection (client start + 40 s, as fail_at).
        for w in waits:
            if w and int(w[3]):
                print(f'      client: {int(w[3]):,} stuck, sent at run +{float(w[5]):.3f} / '
                      f'+{float(w[6]):.3f} / +{float(w[7]):.3f} s (min / median / max)')
        for t, i, kind in sorted(events):
            print(f'      {t:+7.2f}s r{i} {kind}')
        for bid, per in sorted(blocks.items(), key=lambda kv: min(v[0] for v in kv[1].values())):
            n = max(v[2] for v in per.values())
            total = sum(v[3] for v in per.values())
            if all(per[i][3] == n for i in (1, 2, 3) if i in per):
                continue
            first = min(v[0] for v in per.values())
            h = next(iter(per.values()))[1]
            ans = ' '.join(f'r{i}:{per[i][3]}' if i in per else f'r{i}:-' for i in range(4))
            print(f'      block {bid} h={h} first decided {first:+7.2f}s  cmds {n:,}  '
                  f'answered {ans}')


if __name__ == '__main__':
    main()
