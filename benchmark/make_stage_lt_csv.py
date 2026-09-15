#!/usr/bin/env python3
"""Stage LT: Stage L repeated at impeachment timeouts of 5, 2 and 1 s.

Stage L ran with rr's default impeachment timeout of 11 s; the first
leader change after every leader failure came at +11.0 s. In its 20
no-failure runs, the longest pause between commits on replica 1 was
0.010-0.132 s (B2 the largest), so 1 s is still over 7 times the
longest normal pause.

Identical to make_stage_l_csv.py except for imp_timeout (passed as
hotstuff-app --imp-timeout). All three levels are interleaved in one
sweep: rep-major passes, each shuffled across all 60 configurations.

  timeouts  5, 2, 1 s
  per level 4 baselines x 5 arms x 5 reps = 100 runs
  total     300 runs, 120 s each, failure at 40 s, rr, protocol logging

Run ids: LT<t>_<baseline>_<arm>_r<rep>. No expected outcome is recorded.
"""
import csv
import random

import make_stage_l_csv as L

TIMEOUTS = (5, 2, 1)
SEED = 41
FIELDS = L.FIELDS + ['imp_timeout']


def main():
    cfgs = [(t, b, a) for t in TIMEOUTS for b in L.BASELINES for a in L.ARMS]
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, L.REPS + 1):
        order = list(cfgs)
        rng.shuffle(order)
        for t, b, a in order:
            p = L.BASELINES[b]
            node, kind = L.ARMS[a]
            rows.append(dict(L.FIXED, block_size=p['bs'], num_clients=p['c'],
                             max_async=p['ma'], fail_node=node, fail_type=kind,
                             imp_timeout=t, run_id=f'LT{t}_{b}_{a}_r{rep}'))
    with open('stage_lt.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(cfgs)} configs x {L.REPS} reps = {len(rows)} runs -> stage_lt.csv')


if __name__ == '__main__':
    main()
