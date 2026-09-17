#!/usr/bin/env python3
"""Stage MG: where the lost block goes, per command, on a diagnostic build.

Stage MF (FAILURE_ANALYSIS.md 15.7) found the lost block is sent by the
clients 1-4 ms after the second new leader logs "reproposing pending
commands", and appears in no block the survivors decide.

This sweep runs a temporary diagnostic build applied to the hosts
uncommitted and removed afterwards (launched with --skip-update). It adds
logging only, no logic, and only from a leader rotation until 200 ms after
it stops:
  replica  "diag cmd <id> dup= proposer= buffered= buf=" for each command
           received; "diag beat cmd <id>" for each full block assembled and
           "diag beat resolved first= proposer= self=" for whether it was
           proposed; "diag repropose cmd <id>" for every re-proposed command
  client   "[hotstuff stuckcmd] cmd=<id> confirmed= sent=" at shutdown for
           each command waiting more than 10 s

Evidence-gathering, not a hypothesis test: for each stuck command, which
replicas received it, whether they buffered it, and whether it entered a
beat or a re-proposal.

Cells, Stage LT at --imp-timeout 5, leader fails at 40 s, 120 s runs:
  B1 lead_freeze (lost a block in 3 of 3 Stage MF runs)
  B4 lead_crash  (lost a block in 2 of 3)
2 cells x 3 reps = 6 runs.
"""
import csv
import random

import make_stage_l_csv as L

CELLS = [('B1', 'lead_freeze'), ('B4', 'lead_crash')]
REPS = 3
SEED = 71
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
                             run_id=f'MG_{b}_{a}_r{rep}'))
    with open('stage_mg.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=L.FIELDS + ['imp_timeout'])
        w.writeheader()
        w.writerows(rows)
    print(f'{len(CELLS)} cells x {REPS} reps = {len(rows)} runs -> stage_mg.csv')


if __name__ == '__main__':
    main()
