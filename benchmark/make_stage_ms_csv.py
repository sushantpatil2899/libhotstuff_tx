#!/usr/bin/env python3
"""Stage MS: are saturated clients what starves the leader?

Stage MB established that the extra per-block time at B2 and bs400 c2 is
the leader holding a quorum with no full block of commands ready. In both
configurations every client process has a thread at 96-99% of a core,
with four replicas and with three, and at max_async 2,000 and 4,000; in
bs800 c8, which never starves, client threads run at 65-84%.

This sweep changes only client capacity. Each pair keeps requests in
flight (clients x max_async) and block size fixed, and doubles the number
of client processes by halving max_async. The original cells are re-run in
the same sweep so the comparison does not cross sweeps.

Stated before running, so the result can refute it:

  P3  With the same load split across twice the clients, the busiest
      client threads fall clearly below 96%, the leader has no full block
      queued at far fewer quorums than the original (81% at bs800, 90% at
      bs400, four replicas), and four-replica throughput rises. If
      starvation stays near the original with the clients unsaturated,
      client CPU is not what starves the leader.
  P4  In the split cells, losing a replica no longer raises throughput
      (as in every eight-client cell of Stage M). If it still does by a
      similar margin, the replica-loss gain has another source.

Cells, follower 3 killed at 40 s, 3 reps, 120 s, protocol logging on:
  bs800c4        4 clients x 1,000   4,000 in flight   (B2, original)
  bs800c8ma500   8 clients x   500   4,000 in flight   (split)
  bs400c2        2 clients x 1,000   2,000 in flight   (original)
  bs400c4ma500   4 clients x   500   2,000 in flight   (split)
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
         'lat_node2': 0, 'lat_node3': 0, 'fail_at': 40,
         'fail_node': 3, 'fail_type': 'crash'}
# name: block_size, clients, max_async
CELLS = {
    'bs800c4':      (800, 4, 1000),
    'bs800c8ma500': (800, 8, 500),
    'bs400c2':      (400, 2, 1000),
    'bs400c4ma500': (400, 4, 500),
}
REPS = 3
SEED = 61


def main():
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(CELLS.items())
        rng.shuffle(order)
        for name, (bs, c, ma) in order:
            assert c * ma >= 5 * bs, name
            rows.append(dict(FIXED, block_size=bs, num_clients=c, max_async=ma,
                             run_id=f'MS_{name}_r{rep}'))
    with open('stage_ms.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(CELLS)} cells x {REPS} reps = {len(rows)} runs -> stage_ms.csv')


if __name__ == '__main__':
    main()
