#!/usr/bin/env python3
"""Stage L: replica failure mid-run under rr, at B1-B4.

Per run, from the clients' per-second commit counts and latency sums, placed
on one wall clock (each client's own start time):

  T           injection time, from failure-replica-<i>.json. Controls
              have no injection, so T = first client start + 40 s + the
              failure runs' median launch offset, making their windows
              comparable.
  before      mean tps and latency over [T-30, T)
  dip         lowest per-second tps in [T, T+40), as % of before
  zero_s      longest stretch of zero-commit seconds starting at or after T
  recover_s   seconds from T until tps stays >= 90% of before for 5
              consecutive seconds (None if it never does)
  after       mean tps and latency over [T+40, T+76)
  peak_lat    highest per-second mean latency in [T, T+40)

Verification from failure-replica-<i>.json: the signal was delivered
(kill_rc 0), and one second later the process was gone or a zombie after a
crash, or stopped ("T") after a freeze.

From the replica logs (protocol logging on): "Pacemaker: stop rotation at
<id>" and "Pacemaker: rotate to <id>" lines with timestamps, giving the
leader at start, every rotation, their times relative to T, and the last
leader each surviving replica settled on.
"""
import glob
import gzip
import json
import sys
import os
import re
import statistics as st
from collections import defaultdict
from datetime import datetime

# Run-id prefix: L (Stage L, default 11 s impeachment timeout) or LT<t>
# (the same sweep with --imp-timeout <t>), e.g. `analyse_stage_l.py LT2`.
PREFIX = sys.argv[1] if len(sys.argv) > 1 else 'L'
EXPECT_TIMEOUT = float(PREFIX[2:]) if PREFIX.startswith('LT') else None
PAT = re.compile(PREFIX + r'_(B\d)_(ctl|lead_crash|lead_freeze|f3_crash|f3_freeze)_r(\d+)$')
ARMS = ('ctl', 'lead_crash', 'lead_freeze', 'f3_crash', 'f3_freeze')
LABEL = {'ctl': 'no failure', 'lead_crash': 'leader crash',
         'lead_freeze': 'leader freeze', 'f3_crash': 'follower 3 crash',
         'f3_freeze': 'follower 3 freeze'}
TARGET = {'lead_crash': 0, 'lead_freeze': 0, 'f3_crash': 3, 'f3_freeze': 3}
RE_STEADY = re.compile(r'\[hotstuff steady\] start=([0-9.]+)')
RE_BUCKETS = re.compile(r'\[hotstuff buckets\] counts=([0-9,]+)')
RE_LATSUMS = re.compile(r'\[hotstuff latsums\] seconds=([0-9.,]+)')
RE_PM = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) .*Pacemaker: '
                   r'(rotate to|stop rotation at) (\d+)')


def client_series(run_dir):
    """{absolute second: [commits, latency_sum]} summed over clients."""
    texts = []
    for f in glob.glob(os.path.join(run_dir, 'client-*.log')):
        texts.append(open(f, errors='replace').read())
    sp = os.path.join(run_dir, 'summaries.txt')
    if not texts and os.path.exists(sp):
        per = defaultdict(list)
        for line in open(sp):
            name, _, rest = line.partition(': ')
            per[name].append(rest)
        texts = ['\n'.join(v) for v in per.values()]
    series = defaultdict(lambda: [0, 0.0])
    starts = []
    for t in texts:
        ms, mb, ml = RE_STEADY.search(t), RE_BUCKETS.search(t), RE_LATSUMS.search(t)
        if not (ms and mb and ml):
            continue
        start = float(ms[1])
        starts.append(start)
        counts = [int(x) for x in mb[1].split(',')]
        sums = [float(x) for x in ml[1].split(',')]
        for i, (c, s) in enumerate(zip(counts, sums)):
            sec = int(start) + i
            series[sec][0] += c
            series[sec][1] += s
    return series, (min(starts) if starts else None), len(starts)


def window(series, lo, hi):
    secs = range(int(lo), int(hi))
    c = sum(series[s][0] for s in secs if s in series)
    l = sum(series[s][1] for s in secs if s in series)
    return c / max(1, len(secs)), (l / c * 1000 if c else None)


def open_replica_log(run_dir, i):
    """replica-<i>.log, or its gzipped form after parser --gzip-replica-logs."""
    f = os.path.join(run_dir, f'replica-{i}.log')
    if os.path.exists(f):
        return open(f, errors='replace')
    if os.path.exists(f + '.gz'):
        return gzip.open(f + '.gz', 'rt', errors='replace')
    return None


def timeout_flags(run_dir):
    """--imp-timeout value on each replica's command line (None = absent)."""
    out = {}
    for i in range(4):
        f = os.path.join(run_dir, f'compute-replica-{i}.jsonl')
        if not os.path.exists(f):
            continue
        for line in open(f):
            if '"cmdline"' not in line:
                continue
            procs = json.loads(line).get('procs', {})
            for p in procs.values():
                m = re.search(r'--imp-timeout (\S+)', p.get('cmdline') or '')
                out[i] = float(m[1]) if m else None
            if i in out:
                break
    return out


def pacemaker_events(run_dir, t_inject):
    ev = []
    for i in range(4):
        fh = open_replica_log(run_dir, i)
        if fh is None:
            continue
        for line in fh:
            m = RE_PM.search(line)
            if m:
                ts = datetime.strptime(m[1], '%Y-%m-%d %H:%M:%S.%f').timestamp()
                ev.append((ts - t_inject if t_inject else ts, i, m[2], int(m[3])))
    return sorted(ev)


runs = defaultdict(list)
verify = defaultdict(lambda: [0, 0])
launch_offsets = []
raw = []
timeout_ok = timeout_bad = timeout_unrecorded = 0
for d in sorted(glob.glob(f'results/run_logs/{PREFIX}_*')):
    m = PAT.match(os.path.basename(d))
    if not m or not os.path.exists(os.path.join(d, 'metrics.json')):
        continue
    b, arm, rep = m[1], m[2], int(m[3])
    series, t0, nclients = client_series(d)
    flags = timeout_flags(d)
    if not flags:
        # Runs sampled before the sampler recorded command lines (Stage L).
        timeout_unrecorded += 1
    elif len(flags) == 4 and all(v == EXPECT_TIMEOUT for v in flags.values()):
        timeout_ok += 1
    else:
        timeout_bad += 1
    rec = None
    if arm != 'ctl':
        fp = os.path.join(d, f'failure-replica-{TARGET[arm]}.json')
        rec = json.load(open(fp)) if os.path.exists(fp) else None
        ok = bool(rec) and rec.get('kill_rc') == 0 and (
            rec.get('state_after_1s') in ('gone', 'Z') if 'crash' in arm
            else rec.get('state_after_1s') == 'T')
        verify[arm][0 if ok else 1] += 1
        if rec and t0:
            launch_offsets.append(rec['injected_epoch'] - t0 - 40)
    raw.append((b, arm, rep, d, series, t0, nclients, rec,
                json.load(open(os.path.join(d, 'metrics.json')))))

offset = st.median(launch_offsets) if launch_offsets else 0.0
for b, arm, rep, d, series, t0, nclients, rec, met in raw:
    if t0 is None:
        continue
    T = rec['injected_epoch'] if rec else t0 + 40 + offset
    before_tps, before_lat = window(series, T - 30, T)
    after_tps, after_lat = window(series, T + 40, T + 76)
    post = [(s, series[s][0], series[s][1]) for s in range(int(T), int(T) + 40)]
    dip = min((c for _, c, _ in post), default=0) / before_tps * 100 if before_tps else 0
    zero = cur = 0
    for _, c, _ in post:
        cur = cur + 1 if c == 0 else 0
        zero = max(zero, cur)
    recover = None
    for k in range(len(post) - 4):
        if all(post[k + j][1] >= 0.9 * before_tps for j in range(5)):
            recover = k
            break
    lats = [l / c * 1000 for _, c, l in post if c]
    ev = pacemaker_events(d, T)
    runs[(b, arm)].append(dict(
        rep=rep, before=before_tps, before_lat=before_lat, after=after_tps,
        after_lat=after_lat, dip=dip, zero=zero, recover=recover,
        peak_lat=max(lats) if lats else None, events=ev,
        stalled_early=before_tps == 0, nclients=nclients,
        state=rec.get('state_after_1s') if rec else None))

print(f'{PREFIX}: {sum(len(v) for v in runs.values())} runs, impeachment '
      f'timeout {EXPECT_TIMEOUT if EXPECT_TIMEOUT else "default (11 s)"}')
print(f'timeout on all 4 replicas\' command lines as expected: {timeout_ok} runs, '
      f'not as expected: {timeout_bad}, command line not recorded: '
      f'{timeout_unrecorded}')
print(f'launch offset of injection after first client start + 40 s: '
      f'median {offset:.2f} s')
print('\n=== 1. injection verification ===')
for arm in ARMS[1:]:
    print(f'  {LABEL[arm]:<20} verified {verify[arm][0]}, failed {verify[arm][1]}')


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def fmt(x, f='{:,.0f}'):
    return f.format(x) if x is not None else '-'


print('\n=== 2. per baseline: medians over runs not stalled before T ===')
for b in ('B1', 'B2', 'B3', 'B4'):
    print(f'\n########## {b} ##########')
    print(f'  {"arm":<20}{"n":>3}{"early stall":>12}{"before tps":>12}{"lat ms":>8}'
          f'{"dip %":>7}{"zero s":>7}{"recover s":>10}{"peak lat":>10}'
          f'{"after tps":>11}{"lat ms":>8}{"after/before":>13}')
    for arm in ARMS:
        v = runs.get((b, arm), [])
        ok = [x for x in v if not x['stalled_early']]
        if not v:
            continue
        rec_vals = [x['recover'] for x in ok]
        never = sum(1 for r in rec_vals if r is None)
        ratio = med([x['after'] / x['before'] * 100 for x in ok if x['before']])
        print(f'  {LABEL[arm]:<20}{len(v):>3}{len(v) - len(ok):>12}'
              f'{fmt(med([x["before"] for x in ok])):>12}'
              f'{fmt(med([x["before_lat"] for x in ok]), "{:.1f}"):>8}'
              f'{fmt(med([x["dip"] for x in ok]), "{:.0f}"):>7}'
              f'{fmt(med([x["zero"] for x in ok]), "{:.0f}"):>7}'
              f'{fmt(med(rec_vals), "{:.0f}"):>7}'
              f'{"" if not never else f"/{never}x":>3}'
              f'{fmt(med([x["peak_lat"] for x in ok]), "{:,.0f}"):>10}'
              f'{fmt(med([x["after"] for x in ok])):>11}'
              f'{fmt(med([x["after_lat"] for x in ok]), "{:.1f}"):>8}'
              f'{fmt(ratio, "{:.1f}%"):>13}')

print('\n=== 3. pacemaker: leader at start, rotations, settled leader ===')
for b in ('B1', 'B2', 'B3', 'B4'):
    for arm in ARMS:
        for x in sorted(runs.get((b, arm), []), key=lambda x: x['rep']):
            ev = x['events']
            start = sorted({e[3] for e in ev if e[2] == 'stop rotation at' and e[0] < 0})
            rot = [e for e in ev if e[2] == 'rotate to']
            settled = {}
            for t, r, kind, lid in ev:
                if kind == 'stop rotation at':
                    settled[r] = lid
            first = f'{rot[0][0]:+.1f}s' if rot else '-'
            print(f'  {b} {LABEL[arm]:<18} r{x["rep"]}  start leader {start}  '
                  f'rotate lines {len(rot):>3} (first {first})  '
                  f'settled {settled}')

print('\n=== 4. per-second tps around T, first rep of each failure arm ===')
for b in ('B1', 'B2', 'B3', 'B4'):
    for arm in ARMS[1:]:
        for bb, aa, rep, d, series, t0, nc, rec, met in raw:
            if (bb, aa, rep) == (b, arm, 1) and rec and t0:
                T = int(rec['injected_epoch'])
                seq = [series[s][0] for s in range(T - 3, T + 30)]
                print(f'  {b} {LABEL[arm]:<18} T-3..T+29: '
                      + ' '.join(f'{c // 1000}k' if c >= 1000 else str(c) for c in seq))

print('\n=== 5. every run: before tps, after/before, longest zero-commit '
      'stretch, recovery, rotations, settled leader ===')
for b in ('B1', 'B2', 'B3', 'B4'):
    for arm in ARMS:
        for x in sorted(runs.get((b, arm), []), key=lambda x: x['rep']):
            ev = x['events']
            rot = [e for e in ev if e[2] == 'rotate to']
            pre = sum(1 for e in rot if e[0] < 0)
            settled = sorted({lid for t, r, k, lid in ev
                              if k == 'stop rotation at' and r != TARGET.get(arm)
                              and t == max(tt for tt, rr, kk, ll in ev
                                           if rr == r and kk == 'stop rotation at')})
            ratio = x['after'] / x['before'] * 100 if x['before'] else 0
            rec = '-' if x['recover'] is None else f'{x["recover"]}s'
            print(f'  {b} {LABEL[arm]:<18} r{x["rep"]}  before {x["before"]:>9,.0f}  '
                  f'after/before {ratio:>6.1f}%  zero {x["zero"]:>2}s  '
                  f'recover90 {rec:>4}  rotations {len(rot):>2} '
                  f'(before T {pre})  settled {settled}')
