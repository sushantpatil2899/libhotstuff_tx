#!/usr/bin/env python3
"""Stage M: where the 0.45 ms goes, and what reduced load alone does.

Windows match Stage L so the numbers are comparable: for a run with a
failure, T is the injection time from failure-replica-3.json and the
windows are [T-30, T) with four replicas and [T+40, T+76) with three;
for a run without one, T is the first client start + 40.26 s, so both
windows are four-replica and any difference between them is drift.

Per window:
  tps, latency   from the clients' per-second commit counts and latency sums
  in flight      tps x latency, against clients x max_async
  blocks/s, gap  "commit <block ... ncmds=N>" lines on replica 1
  A, B, C        on the leader (replica 0), per proposed block:
                 A propose -> the 2f+1'th vote for that block
                 B that vote -> the "got QC" line
                 C that line -> the next propose
"""
import csv
import glob
import gzip
import json
import os
import re
import statistics as st
from collections import defaultdict
from datetime import datetime

PAT = re.compile(r'M_(map|workers|burst|load)_(\w+?)_r(\d+)$')
RE_S = re.compile(r'\[hotstuff steady\] start=([0-9.]+)')
RE_B = re.compile(r'\[hotstuff buckets\] counts=([0-9,]+)')
RE_L = re.compile(r'\[hotstuff latsums\] seconds=([0-9.,]+)')
RE_C = re.compile(r'^(\S+ \S+) \[hotstuff proto\] commit <block .*ncmds=(\d+)')
RE_PV = re.compile(r'^(\S+ \S+) \[hotstuff proto\] (propose <block id=(\w+)|'
                   r'got <vote rid=\d+ blk=(\w+)|got QC,)')
QUORUM = 3


def ts(s):
    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S.%f').timestamp()


def open_log(run_dir, i):
    f = os.path.join(run_dir, f'replica-{i}.log')
    if os.path.exists(f):
        return open(f, errors='replace')
    return gzip.open(f + '.gz', 'rt', errors='replace') if os.path.exists(f + '.gz') else None


def client_series(run_dir):
    texts = [open(f, errors='replace').read()
             for f in glob.glob(os.path.join(run_dir, 'client-*.log'))]
    sp = os.path.join(run_dir, 'summaries.txt')
    if not texts and os.path.exists(sp):
        # One line per client per marker; group the lines back per client.
        per = defaultdict(list)
        for line in open(sp):
            name, _, rest = line.partition(': ')
            per[name].append(rest)
        texts = ['\n'.join(v) for v in per.values()]
    series, starts = defaultdict(lambda: [0, 0.0]), []
    for t in texts:
        ms, mb, ml = RE_S.search(t), RE_B.search(t), RE_L.search(t)
        if not (ms and mb and ml):
            continue
        starts.append(float(ms[1]))
        for i, (c, s) in enumerate(zip(mb[1].split(','), ml[1].split(','))):
            sec = int(float(ms[1])) + i
            series[sec][0] += int(c)
            series[sec][1] += float(s)
    return series, (min(starts) if starts else None)


def window(series, lo, hi):
    c = sum(series[s][0] for s in range(int(lo), int(hi)) if s in series)
    l = sum(series[s][1] for s in range(int(lo), int(hi)) if s in series)
    return (c / (int(hi) - int(lo)), l / c * 1000) if c else (0.0, None)


def blocks(run_dir, lo, hi):
    fh = open_log(run_dir, 1)
    if fh is None:
        return None
    v = [(ts(m[1]), int(m[2])) for m in
         (RE_C.match(line) for line in fh) if m and lo <= ts(m[1]) < hi]
    if len(v) < 10:
        return None
    gaps = [(b[0] - a[0]) * 1000 for a, b in zip(v, v[1:])]
    return dict(rate=len(v) / (hi - lo), gap=st.median(gaps),
                ncmds=st.median(x[1] for x in v))


def segments(run_dir, lo, hi):
    fh = open_log(run_dir, 0)
    if fh is None:
        return None
    out = defaultdict(list)
    cur = ptime = qtime = qcline = None
    nvotes = 0
    for line in fh:
        m = RE_PV.match(line)
        if not m:
            continue
        t = ts(m[1])
        if m[3]:
            if cur and qcline and ptime and lo <= ptime < hi:
                out['A'].append((qtime - ptime) * 1000)
                out['B'].append((qcline - qtime) * 1000)
                out['C'].append((t - qcline) * 1000)
            cur, ptime, nvotes, qtime, qcline = m[3], t, 0, None, None
        elif m[4]:
            if m[4] == cur:
                nvotes += 1
                if nvotes == QUORUM:
                    qtime = t
        elif qtime and qcline is None:
            qcline = t
    if len(out['A']) < 10:
        return None
    return {k: st.median(v) for k, v in out.items()}


def main():
    cfg = {r['run_id']: r for r in csv.DictReader(open('stage_m.csv'))}
    cells = defaultdict(list)
    for d in sorted(glob.glob('results/run_logs/M_*')):
        m = PAT.match(os.path.basename(d))
        if not m or not os.path.exists(os.path.join(d, 'metrics.json')):
            continue
        row = cfg.get(os.path.basename(d))
        series, t0 = client_series(d)
        if t0 is None:
            continue
        fp = os.path.join(d, 'failure-replica-3.json')
        failed = m[1] == 'map' and os.path.exists(fp)
        T = json.load(open(fp))['injected_epoch'] if failed else t0 + 40.26
        rec = {'cap': int(row['num_clients']) * int(row['max_async']),
               'bs': int(row['block_size']), 'failed': failed}
        for name, (lo, hi) in (('pre', (T - 30, T)), ('post', (T + 40, T + 76))):
            tps, lat = window(series, lo, hi)
            rec[name] = dict(tps=tps, lat=lat, blocks=blocks(d, lo, hi),
                             seg=segments(d, lo, hi))
        cells[(m[1], m[2])].append(rec)

    def med(v, w, *path):
        out = []
        for r in v:
            x = r[w]
            for p in path:
                if x is None:
                    break
                x = x[p] if isinstance(x, dict) else None
            if x:
                out.append(x)
        return st.median(out) if out else None

    def fmt(x, f='{:.2f}'):
        return f.format(x) if x is not None else '-'

    print('=== 1. map: the same configuration with four replicas, then three ===')
    print(f"{'configuration':<16}{'replicas':>9}{'tps':>10}{'lat ms':>8}{'blocks/s':>9}"
          f"{'gap':>7}{'A vote':>8}{'B QC':>7}{'C next':>8}{'runs':>6}")
    for k in sorted(cells):
        if k[0] != 'map':
            continue
        v = cells[k]
        for w, n in (('pre', 4), ('post', 3)):
            print(f'{k[1]:<16}{n:>9}{med(v, w, "tps"):>10,.0f}'
                  f'{fmt(med(v, w, "lat")):>8}{fmt(med(v, w, "blocks", "rate"), "{:.1f}"):>9}'
                  f'{fmt(med(v, w, "blocks", "gap")):>7}{fmt(med(v, w, "seg", "A")):>8}'
                  f'{fmt(med(v, w, "seg", "B")):>7}{fmt(med(v, w, "seg", "C")):>8}{len(v):>6}')

    print('\n=== 2. workers and burst: B2, four replicas, no failure ===')
    print(f"{'cell':<16}{'tps':>10}{'lat ms':>8}{'blocks/s':>9}{'gap':>7}"
          f"{'A vote':>8}{'B QC':>7}{'C next':>8}{'runs':>6}")
    for k in sorted(cells):
        if k[0] not in ('workers', 'burst'):
            continue
        v = cells[k]
        print(f'{k[0]+" "+k[1]:<16}{med(v, "post", "tps"):>10,.0f}'
              f'{fmt(med(v, "post", "lat")):>8}{fmt(med(v, "post", "blocks", "rate"), "{:.1f}"):>9}'
              f'{fmt(med(v, "post", "blocks", "gap")):>7}{fmt(med(v, "post", "seg", "A")):>8}'
              f'{fmt(med(v, "post", "seg", "B")):>7}{fmt(med(v, "post", "seg", "C")):>8}{len(v):>6}')

    print('\n=== 3. load: a healthy system at the load a leader failure leaves ===')
    print(f"{'cell':<16}{'tps':>10}{'lat ms':>8}{'in flight':>11}{'cap':>9}{'runs':>6}")
    for k in sorted(cells):
        if k[0] != 'load':
            continue
        v = cells[k]
        tps, lat = med(v, 'post', 'tps'), med(v, 'post', 'lat')
        print(f'{k[1]:<16}{tps:>10,.0f}{fmt(lat):>8}{tps * lat / 1000:>11,.0f}'
              f'{v[0]["cap"]:>9,}{len(v):>6}')


if __name__ == '__main__':
    main()
