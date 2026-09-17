#!/usr/bin/env python3
"""Stage MH: does the discarded beat account for the lost block?

Stage MG (FAILURE_ANALYSIS.md 15.8) showed the lost block is assembled by
the new leader and never proposed. Two things were left open: why that
proposal never happens, and whether the same mechanism explains the losses
that occur with only one re-proposal (9 of 24 B1 leader-crash runs, 3 of 33
B2 runs; at B4 all 24 losses had a second re-proposal).

In the code, a beat is popped from pending_beats and then waits on a single
promise slot, pm_qc_finish, which the next scheduling pass, a rotate, or a
stop_rotate rejects (include/hotstuff/liveness.h). A rejected promise never
fires, so such a beat is never proposed although its commands have already
left cmd_pending_buffer. This build logs that discard directly.

Diagnostic (temporary, applied to the hosts uncommitted, removed after the
sweep, 58 lines added and none changed), deliberately light so it cannot
change what it measures -- two lines per block instead of Stage MG's one
line per command, and per-command output only at client shutdown:
  replica  "diag beat assembled first=<id> n=<n>"    one per block
           "diag beat resolved first=<id> ..."       one per block
           "diag beat discarded at schedule_next|rotate|stop_rotate"
  client   "[hotstuff stuckcmd] cmd=<id> confirmed= sent=" at shutdown

Cells, Stage LT at --imp-timeout 5, leader fails at 40 s, 120 s runs:
  B1 lead_crash  5 reps   the single-re-proposal case
  B4 lead_crash  3 reps   behaved normally under Stage MF's light logging
                          and abnormally under Stage MG's heavy logging, so
                          it also checks that this build does not distort
8 runs. Comparison for distortion: Stage LT5, same cells, no diagnostic.
"""
import csv
import random

import make_stage_l_csv as L

CELLS = [('B1', 'lead_crash')] * 5 + [('B4', 'lead_crash')] * 3
REPS = 1
SEED = 73
TIMEOUT = 5


def main():
    rng = random.Random(SEED)
    rows = []
    order = list(CELLS)
    rng.shuffle(order)
    seen = {}
    if True:
        for i, (b, a) in enumerate(order):
            seen[(b, a)] = seen.get((b, a), 0) + 1
            p = L.BASELINES[b]
            node, kind = L.ARMS[a]
            rows.append(dict(L.FIXED, block_size=p['bs'], num_clients=p['c'],
                             max_async=p['ma'], fail_node=node, fail_type=kind,
                             imp_timeout=TIMEOUT,
                             run_id=f'MH_{b}_{a}_r{seen[(b, a)]}'))
    with open('stage_mh.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=L.FIELDS + ['imp_timeout'])
        w.writeheader()
        w.writerows(rows)
    print(f'{len(CELLS)} cells x {REPS} reps = {len(rows)} runs -> stage_mh.csv')


if __name__ == '__main__':
    main()
