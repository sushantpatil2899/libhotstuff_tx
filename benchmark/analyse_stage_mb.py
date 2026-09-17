#!/usr/bin/env python3
"""Stage MB: attribute each block's quorum-to-QC gap on the leader.

Beats queue: each "beat: block of N ready" line adds one full block of
commands to a FIFO, and each proposal carrying commands (ncmds > 0) takes
one off. The pacemaker's startup blocks carry no commands and take none.

For every "got QC, propose a new block" line g on replica 0, in log order:
  q  the 2f+1'th vote for the block most recently proposed
  g - q is the gap Stages L and M called "QC formed"
  pending at q   whether any beat was queued when that vote arrived

If a beat was pending at q, commands were already waiting when the quorum
completed. If none was, the leader had its quorum and no full block; the
beat that eventually resolves it is the first to arrive after q, at b, and
g - b is how long the QC line followed it.

Tests (stated in make_stage_mb_csv.py before the sweep ran):
  P1  gaps over 0.1 ms occur with no beat queued at q, and g follows the
      next beat closely; gaps with a beat queued stay near 0.02 ms
  P2  at bs400 c2, raising max_async keeps a beat queued and removes the gap

Windows as in Stage M: [T-30, T) four replicas, [T+40, T+76) three for
runs with a failure; both four-replica otherwise.
"""
import glob
import gzip
import json
import os
import re
import statistics as st
from collections import defaultdict, deque
from datetime import datetime

PAT = re.compile(r'MB_(\w+?)_r(\d+)$')
RE_E = re.compile(r'^(\S+ \S+) \[hotstuff proto\] (?:'
                  r'propose <block id=(?P<prop>\w+) height=\d+ ncmds=(?P<ncmds>\d+)|'
                  r'got <vote rid=\d+ blk=(?P<vote>\w+)>|'
                  r'(?P<qc>got QC, propose a new block)|'
                  r'beat: block of \d+ ready, (?P<left>\d+) left in buffer)')
RE_S = re.compile(r'\[hotstuff steady\] start=([0-9.]+)')
QUORUM = 3


def ts(s):
    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S.%f').timestamp()


def first_client_start(run_dir):
    per = defaultdict(list)
    sp = os.path.join(run_dir, 'summaries.txt')
    if os.path.exists(sp):
        for line in open(sp):
            name, _, rest = line.partition(': ')
            per[name].append(rest)
    texts = ['\n'.join(v) for v in per.values()] or [
        open(f, errors='replace').read() for f in glob.glob(os.path.join(run_dir, 'client-*.log'))]
    starts = [float(m[1]) for m in (RE_S.search(t) for t in texts) if m]
    return min(starts) if starts else None


def analyse(run_dir, windows):
    f = os.path.join(run_dir, 'replica-0.log')
    fh = open(f, errors='replace') if os.path.exists(f) else gzip.open(f + '.gz', 'rt', errors='replace')
    out = {w: defaultdict(list) for w in windows}
    beats = deque()                    # timestamps of queued full blocks
    cur, nvotes, q, pending_at_q = None, 0, None, None
    for line in fh:
        m = RE_E.match(line)
        if not m:
            continue
        t = ts(m[1])
        if m['prop']:
            if int(m['ncmds']) > 0 and beats:
                beats.popleft()
            cur, nvotes, q, pending_at_q = m['prop'], 0, None, None
        elif m['vote']:
            if m['vote'] == cur:
                nvotes += 1
                if nvotes == QUORUM:
                    q, pending_at_q = t, bool(beats)
        elif m['left'] is not None:
            beats.append(t)
            for w, (lo, hi) in windows.items():
                if lo <= t < hi:
                    out[w]['left'].append(int(m['left']))
        elif m['qc'] and q is not None:
            w = next((w for w, (lo, hi) in windows.items() if lo <= t < hi), None)
            if w is None:
                continue
            o = out[w]
            gap = (t - q) * 1000
            o['gap'].append(gap)
            o['no_beat_at_quorum'].append(not pending_at_q)
            if pending_at_q:
                o['gap_when_pending'].append(gap)
            elif beats:
                b = beats[0]
                o['gap_when_not_pending'].append(gap)
                o['qc_after_beat'].append((t - b) * 1000)
                # Model check: with nothing queued at q, the beat that
                # resolves this QC line must have arrived after q.
                o['model_violations'].append(b <= q)
            else:
                o['model_violations'].append(True)
            if gap > 0.1:
                o['big_no_beat'].append(not pending_at_q)
    return out


def summarise(runs, w):
    def pooled(key):
        return [x for r in runs for x in r[w][key]]
    gap = pooled('gap')
    if not gap:
        return None
    nob, bign = pooled('no_beat_at_quorum'), pooled('big_no_beat')
    gp, gn, qab, left = (pooled('gap_when_pending'), pooled('gap_when_not_pending'),
                         pooled('qc_after_beat'), pooled('left'))
    med = lambda v: st.median(v) if v else None
    return dict(
        blocks=len(gap), gap=st.median(gap),
        big=sum(1 for x in gap if x > 0.1) / len(gap) * 100,
        no_beat=sum(nob) / len(nob) * 100,
        big_no_beat=(sum(bign) / len(bign) * 100) if bign else None,
        gap_pending=med(gp), gap_not_pending=med(gn), qc_after_beat=med(qab),
        left=med(left),
        violations=sum(pooled('model_violations')),
        checked=len(pooled('model_violations')),
        left_zero=(sum(1 for x in left if x == 0) / len(left) * 100) if left else None)


def main():
    cells = defaultdict(list)
    for d in sorted(glob.glob('results/run_logs/MB_*')):
        m = PAT.match(os.path.basename(d))
        if not m or not os.path.exists(os.path.join(d, 'metrics.json')):
            continue
        fp = os.path.join(d, 'failure-replica-3.json')
        if os.path.exists(fp):
            T = json.load(open(fp))['injected_epoch']
        else:
            t0 = first_client_start(d)
            if t0 is None:
                continue
            T = t0 + 40.26
        failed = os.path.exists(fp)
        runs = analyse(d, {'pre': (T - 30, T), 'post': (T + 40, T + 76)})
        cells[(m[1], failed)].append(runs)

    def f(x, spec):
        return spec.format(x) if x is not None else '-'

    print("=== Stage MB: the leader's quorum-to-QC gap, attributed per block ===")
    print("no beat at quorum = when the 2f+1'th vote arrived, no full block of")
    print("                    commands was queued")
    print(f"{'cell':<13}{'repl':>5}{'blocks':>8}{'gap med':>8}{'gap>0.1':>8}"
          f"{'no beat at quorum':>18}{'of gaps>0.1':>12}{'gap|beat queued':>16}"
          f"{'gap|no beat':>12}{'QC after beat':>14}{'left med':>9}{'left=0':>7}{'runs':>5}{'model check':>14}")
    for (name, failed) in sorted(cells):
        runs = cells[(name, failed)]
        for w, n in (('pre', 4), ('post', 3 if failed else 4)):
            s = summarise(runs, w)
            if not s:
                continue
            print(f'{name:<13}{n:>5}{s["blocks"]:>8,}{s["gap"]:>8.2f}{s["big"]:>7.1f}%'
                  f'{s["no_beat"]:>17.1f}%{f(s["big_no_beat"], "{:.1f}%"):>12}'
                  f'{f(s["gap_pending"], "{:.2f}"):>16}{f(s["gap_not_pending"], "{:.2f}"):>12}'
                  f'{f(s["qc_after_beat"], "{:.2f}"):>14}{f(s["left"], "{:.0f}"):>9}'
                  f'{f(s["left_zero"], "{:.0f}%"):>7}{len(runs):>5}'
                  f'{str(s["violations"]) + "/" + str(s["checked"]):>14}')


if __name__ == '__main__':
    main()
