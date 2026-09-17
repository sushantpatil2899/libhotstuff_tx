#!/usr/bin/env python3
"""Stage MF: which commands are left unconfirmed after a leader failure.

FAILURE_ANALYSIS.md 13 found that some leader failures leave exactly one
block of client commands unconfirmed for the rest of the run, inferred from
throughput x latency. Across the 143 recovered leader-failure runs of
Stages L and LT, 45 lost one block and 97 lost none; every re-proposed
block was committed by all surviving replicas, so the lost commands were
proposed and committed but never collected f+1 answers.

This build adds two diagnostics:
  replica  "decided block X height H: N cmds, M answered" per decided block
           (protocol-log builds only) -- M is how many of the block's
           commands this replica answered; a replica answers only commands
           still in its own decision_waiting.
  client   "[hotstuff waiting] n=... sent=..." at shutdown -- the commands
           never confirmed, counted directly.

This is an evidence-gathering sweep, not a hypothesis test. What it is for:
  E1  whether the client's own stuck count equals the one block inferred
      from throughput x latency, run by run;
  E2  which decided blocks were answered by fewer than f+1 = 2 replicas in
      total, and whether their size matches the stuck count.

Design: Stage LT at --imp-timeout 5 s, where the loss was most consistent
(B1 freeze, B4 crash and B4 freeze all lost one block; B2 lost none).
Leader (replica 0) fails at 40 s, 120 s runs, rr, protocol logging on.
  B4 lead_crash, B4 lead_freeze, B1 lead_freeze     expected to lose
  B1 lead_crash, B2 lead_crash, B2 lead_freeze      expected not to
6 cells x 3 reps = 18 runs.
"""
import csv
import random

import make_stage_l_csv as L

CELLS = [('B4', 'lead_crash'), ('B4', 'lead_freeze'), ('B1', 'lead_freeze'),
         ('B1', 'lead_crash'), ('B2', 'lead_crash'), ('B2', 'lead_freeze')]
REPS = 3
SEED = 67
TIMEOUT = 5


def main():
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(CELLS)
        rng.shuffle(order)
        for b, a in order:
            p = L.BASELINES[b]
            node, kind = L.ARMS[a]
            rows.append(dict(L.FIXED, block_size=p['bs'], num_clients=p['c'],
                             max_async=p['ma'], fail_node=node, fail_type=kind,
                             imp_timeout=TIMEOUT,
                             run_id=f'MF_{b}_{a}_r{rep}'))
    with open('stage_mf.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=L.FIELDS + ['imp_timeout'])
        w.writeheader()
        w.writerows(rows)
    print(f'{len(CELLS)} cells x {REPS} reps = {len(rows)} runs -> stage_mf.csv')


if __name__ == '__main__':
    main()
