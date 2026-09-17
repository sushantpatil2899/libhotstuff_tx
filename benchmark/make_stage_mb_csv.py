#!/usr/bin/env python3
"""Stage MB: is the quorum-to-QC delay the leader waiting for commands?

On the leader, "got QC, propose a new block" is logged at the later of two
events: the previous block's QC completing, and a full block of commands
being ready (beat() is called only when cmd_pending_buffer reaches
blk_size; include/hotstuff/liveness.h proposer_schedule_next). Stage M
could not tell the two apart. This build adds one protocol-log line at the
moment beat() is called ("beat: block of N ready, M left in buffer",
src/hotstuff.cpp), so each block's delay can be attributed.

Stated before running, so the result can refute it:

  P1  For a block whose quorum-to-QC gap exceeds 0.1 ms, the beat line for
      the next block comes AFTER that block's 2f+1'th vote, and the QC line
      follows the beat within ~0.1 ms. If large gaps occur with the beat
      already logged before the vote, the explanation is wrong.
  P2  Doubling or quadrupling max_async at bs400 c2 (more commands
      outstanding, same block size) makes the beat precede the QC and the
      gap fall to ~0.02 ms. If the gap stays near 0.84 ms, it is wrong.

Cells, 3 reps each, 120 s, protocol logging on:
  bs400c2        follower 3 killed at 40 s  (worst case in Stage M)
  bs800c4        follower 3 killed at 40 s  (B2)
  bs800c8        follower 3 killed at 40 s  (no delay in Stage M)
  bs400c2ma2     no failure                 (P2)
  bs400c2ma4     no failure                 (P2)
"""
import csv
import random

FIELDS = ['run_id', 'nodes', 'num_clients', 'iter_count', 'max_async',
          'duration', 'meas_warmup', 'meas_cooldown', 'sample_compute',
          'collocate_client', 'block_size', 'pace_maker', 'nworker',
          'repnworker', 'clinworker', 'repburst', 'cliburst', 'sb_users',
          'sb_prob_choose_mtx', 'sb_skew_factor', 'lat_node0', 'lat_node1',
          'lat_node2', 'lat_node3', 'fail_node', 'fail_type', 'fail_at']
FIXED = {'nodes': 4, 'iter_count': -1, 'duration': 120, 'meas_warmup': 10,
         'meas_cooldown': 2, 'sample_compute': 'true',
         'collocate_client': 'false', 'pace_maker': 'rr', 'nworker': 4,
         'repnworker': 4, 'clinworker': 4, 'repburst': 1000,
         'cliburst': 1000, 'sb_users': 10**6, 'sb_prob_choose_mtx': '0.9',
         'sb_skew_factor': '0.1', 'lat_node0': 0, 'lat_node1': 0,
         'lat_node2': 0, 'lat_node3': 0, 'fail_at': 40}
# name: block_size, clients, max_async, fail_node
CELLS = {
    'bs400c2':    (400, 2, 1000, 3),
    'bs800c4':    (800, 4, 1000, 3),
    'bs800c8':    (800, 8, 1000, 3),
    'bs400c2ma2': (400, 2, 2000, -1),
    'bs400c2ma4': (400, 2, 4000, -1),
}
REPS = 3
SEED = 59


def main():
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(CELLS.items())
        rng.shuffle(order)
        for name, (bs, c, ma, node) in order:
            assert c * ma >= 5 * bs, name
            rows.append(dict(FIXED, block_size=bs, num_clients=c, max_async=ma,
                             fail_node=node, fail_type='crash' if node >= 0 else '',
                             run_id=f'MB_{name}_r{rep}'))
    with open('stage_mb.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(CELLS)} cells x {REPS} reps = {len(rows)} runs -> stage_mb.csv')


if __name__ == '__main__':
    main()
