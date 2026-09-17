#!/usr/bin/env python3
"""Stage MS: the same load split across twice the clients.

Per cell, four replicas ([T-30, T)) and three ([T+40, T+76)):
  tps              clients' per-second commits over the window
  starved          % of quorums with no full block of commands queued, and
                   the model check -- from analyse_stage_mb.analyse, the
                   per-block attribution validated in Stage MB
  client threads   the busiest threads on the client host, % of one core

Tests P3 and P4 are stated in make_stage_ms_csv.py.
"""
import glob
import json
import os
import re
import statistics as st
from collections import defaultdict

from analyse_stage_mb import analyse, summarise

PAT = re.compile(r'MS_(\w+?)_r(\d+)$')
RE_S = re.compile(r'\[hotstuff steady\] start=([0-9.]+)')
RE_B = re.compile(r'\[hotstuff buckets\] counts=([0-9,]+)')


def tps(run_dir, lo, hi):
    per = defaultdict(list)
    for line in open(os.path.join(run_dir, 'summaries.txt')):
        name, _, rest = line.partition(': ')
        per[name].append(rest)
    series = defaultdict(int)
    for v in per.values():
        t = '\n'.join(v)
        ms, mb = RE_S.search(t), RE_B.search(t)
        if ms and mb:
            for i, c in enumerate(mb[1].split(',')):
                series[int(float(ms[1])) + i] += int(c)
    return sum(series[s] for s in range(int(lo), int(hi))) / (int(hi) - int(lo))


def client_threads(run_dir, lo, hi):
    S, tck = [], 100
    for line in open(os.path.join(run_dir, 'compute-clienthost-0.jsonl')):
        o = json.loads(line)
        if 'header' in o:
            tck = o['header']['clk_tck']
        elif lo <= o['wall'] < hi:
            S.append(o)
    a, b = S[0], S[-1]
    dt = b['wall'] - a['wall']
    out = []
    for p in set(a['procs']) & set(b['procs']):
        ta, tb = a['procs'][p]['threads'], b['procs'][p]['threads']
        for tid in set(ta) & set(tb):
            out.append((tb[tid][1] - ta[tid][1]) / tck / dt * 100)
    return sorted(out, reverse=True)


def main():
    cells = defaultdict(lambda: {'runs': [], 'tps': defaultdict(list),
                                 'thr': defaultdict(list)})
    for d in sorted(glob.glob('results/run_logs/MS_*')):
        m = PAT.match(os.path.basename(d))
        if not m or not os.path.exists(os.path.join(d, 'metrics.json')):
            continue
        T = json.load(open(os.path.join(d, 'failure-replica-3.json')))['injected_epoch']
        win = {'pre': (T - 30, T), 'post': (T + 40, T + 76)}
        c = cells[m[1]]
        c['runs'].append(analyse(d, win))
        for w, (lo, hi) in win.items():
            c['tps'][w].append(tps(d, lo, hi))
            c['thr'][w].append(client_threads(d, lo, hi))

    print('=== Stage MS: the same load split across twice the clients ===')
    print(f"{'cell':<14}{'repl':>5}{'tps':>10}{'change':>8}{'starved':>9}"
          f"{'gap med':>8}{'model check':>13}{'  busiest client threads %'}")
    for name in ('bs800c4', 'bs800c8ma500', 'bs400c2', 'bs400c4ma500'):
        if name not in cells:
            continue
        c = cells[name]
        base = None
        for w, n in (('pre', 4), ('post', 3)):
            s = summarise(c['runs'], w)
            t = st.median(c['tps'][w])
            base = base or t
            thr = c['thr'][w]
            k = min(len(x) for x in thr)
            top = ' '.join(f'{st.median(x[i] for x in thr):.0f}' for i in range(min(k, 8)))
            change = '' if w == 'pre' else f'{(t - base) / base * 100:+.1f}%'
            print(f'{name:<14}{n:>5}{t:>10,.0f}{change:>8}{s["no_beat"]:>8.1f}%'
                  f'{s["gap"]:>8.2f}{str(s["violations"]) + "/" + str(s["checked"]):>13}  {top}')


if __name__ == '__main__':
    main()
