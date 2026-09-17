#!/usr/bin/env python3
"""Stage MG: follow each stuck command through the replicas.

Joins the clients' stuck-command list with the replicas' per-command
diagnostic lines, both from a temporary diagnostic build that is not part
of the repo (see make_stage_mg_csv.py).

Client, at shutdown:
    [hotstuff stuckcmd] cmd=<id> confirmed=<n> sent=<s from run_start>
Replica, from a rotation until 200 ms after it stops:
    diag cmd <id> dup=<0|1> proposer=<p> buffered=<0|1> buf=<n>
    diag beat cmd <id>            command placed in a full block
    diag beat resolved first=<id> proposer=<p> self=<i>
    diag repropose cmd <id>       command in a new leader's re-proposal

For every stuck command the join answers, per replica: was it received in
the window, was it buffered, did it enter a block, was it re-proposed.
"""
import glob
import gzip
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

RE_STUCK = re.compile(r'\[hotstuff stuckcmd\] cmd=(\w+) confirmed=(\d+) sent=(-?[0-9.]+)')
RE_TOTAL = re.compile(r'\[hotstuff stucktotal\] n=(\d+) start=([0-9.]+)')
RE_CMD = re.compile(r'^(\S+ \S+) \[hotstuff proto\] diag cmd (\w+) dup=(\d) '
                    r'proposer=(\d+) buffered=(\d) buf=(\d+)')
RE_BEAT = re.compile(r'^(\S+ \S+) \[hotstuff proto\] diag beat cmd (\w+)')
RE_BRES = re.compile(r'^(\S+ \S+) \[hotstuff proto\] diag beat resolved first=(\w+) '
                     r'proposer=(\d+) self=(\d+)')
RE_REP = re.compile(r'^(\S+ \S+) \[hotstuff proto\] diag repropose cmd (\w+)')


def ts(s):
    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S.%f').timestamp()


def open_log(run_dir, i):
    f = os.path.join(run_dir, f'replica-{i}.log')
    if os.path.exists(f):
        return open(f, errors='replace')
    return gzip.open(f + '.gz', 'rt', errors='replace') if os.path.exists(f + '.gz') else None


def main():
    for d in sorted(glob.glob('results/run_logs/MG_*')):
        if not os.path.exists(os.path.join(d, 'metrics.json')):
            continue
        fp = os.path.join(d, 'failure-replica-0.json')
        T = json.load(open(fp))['injected_epoch']
        stuck, confirmed = {}, defaultdict(int)
        for f in glob.glob(os.path.join(d, 'client-*.log')):
            for line in open(f, errors='replace'):
                m = RE_STUCK.search(line)
                if m:
                    stuck[m[1]] = float(m[3])
                    confirmed[int(m[2])] += 1
        print(f'=== {os.path.basename(d)}  stuck {len(stuck):,}  '
              f'confirmations: ' + ', '.join(f'{k} reply: {v:,}' for k, v in sorted(confirmed.items())))
        if not stuck:
            continue
        got = {i: {'received': set(), 'buffered': set(), 'beat': set(),
                   'repropose': set(), 'dup': set()} for i in range(4)}
        first_seen = {}
        for i in range(4):
            fh = open_log(d, i)
            if fh is None:
                continue
            for line in fh:
                m = RE_CMD.match(line)
                if m:
                    if m[2] in stuck:
                        got[i]['received'].add(m[2])
                        first_seen.setdefault((i, m[2]), ts(m[1]) - T)
                        if m[5] == '1':
                            got[i]['buffered'].add(m[2])
                        if m[3] == '1':
                            got[i]['dup'].add(m[2])
                    continue
                m = RE_BEAT.match(line)
                if m:
                    if m[2] in stuck:
                        got[i]['beat'].add(m[2])
                    continue
                m = RE_REP.match(line)
                if m and m[2] in stuck:
                    got[i]['repropose'].add(m[2])
        n = len(stuck)
        print(f'{"":<6}{"received":>10}{"buffered":>10}{"in a block":>12}'
              f'{"re-proposed":>13}{"already pending":>17}')
        for i in range(4):
            g = got[i]
            print(f'  r{i}  {len(g["received"]):>8,}{len(g["buffered"]):>10,}'
                  f'{len(g["beat"]):>12,}{len(g["repropose"]):>13,}{len(g["dup"]):>17,}')
        seen_any = set().union(*(got[i]['received'] for i in range(4)))
        blk_any = set().union(*(got[i]['beat'] | got[i]['repropose'] for i in range(4)))
        print(f'  of {n:,} stuck commands: seen by no replica in the window '
              f'{n - len(seen_any):,}; never in a block or re-proposal {n - len(blk_any):,}')
        if first_seen:
            times = sorted(first_seen.values())
            print(f'  first seen at a replica: T{times[0]:+.3f} .. T{times[-1]:+.3f} s')


if __name__ == '__main__':
    main()
