#!/usr/bin/env python3
"""Stage P: the Stage O batching trend repeated at 4x the load.

Stage O swept block_size 800-6400 at 8 clients x max_async 4,000 (32,000
outstanding, whose legal block_size ceiling is exactly 6,400) and found,
under leader delay, each doubling of block_size roughly doubling
throughput, while with no delay the last doubling was worth only
+0.5% (Stage G) to +4.8% (Stage O).

This repeats the sweep at 8 clients x max_async 16,000 (128,000
outstanding, ceiling 25,600), from the same bottom block size, so the
trend can be compared at two loads. block_size 3200 at this load was
measured in Stage O; keeping it here gives a repeat check.

  clients 8, max_async 16000, threads 4, 90% writes, skew 0.1
  block_size  800, 1600, 3200, 6400, 12800, 25600
  conditions  no delay / leader (replica 1) 100ms / leader 200ms

6 x 3 = 18 configs x 3 reps = 54 runs. Rep-major order, shuffled with a
fixed seed. Every run records measured round trips in rtt.json.

Block sizes above 6400 have never been run here; a cell that exceeds some
per-block limit will surface as a failed row rather than a bad number.

No expected outcome is recorded.
"""
import csv
import random

FIELDS = ['run_id', 'nodes', 'num_clients', 'iter_count', 'max_async',
          'duration', 'collocate_client', 'block_size', 'pace_maker',
          'nworker', 'repnworker', 'clinworker', 'repburst', 'cliburst',
          'sb_users', 'sb_prob_choose_mtx', 'sb_skew_factor',
          'lat_node0', 'lat_node1', 'lat_node2', 'lat_node3']

FIXED = {'nodes': 4, 'num_clients': 8, 'iter_count': -1, 'max_async': 16000,
         'duration': 60, 'collocate_client': 'false', 'pace_maker': 'dummy',
         'nworker': 4, 'repnworker': 4, 'clinworker': 4,
         'repburst': 1000, 'cliburst': 1000, 'sb_users': 10**6,
         'sb_prob_choose_mtx': '0.9', 'sb_skew_factor': '0.1',
         'lat_node0': 0, 'lat_node2': 0, 'lat_node3': 0}

BLOCK_SIZES = (800, 1600, 3200, 6400, 12800, 25600)
CONDITIONS = {'ctl': 0, 'lead100': 100, 'lead200': 200}
REPS = 3
SEED = 19


def main():
    cfgs = [(bs, c) for bs in BLOCK_SIZES for c in CONDITIONS]
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(cfgs)
        rng.shuffle(order)
        for bs, cond in order:
            assert FIXED['num_clients'] * FIXED['max_async'] >= 5 * bs, bs
            r = dict(FIXED)
            r.update(block_size=bs, lat_node1=CONDITIONS[cond],
                     run_id=f'P_bs{bs}_{cond}_r{rep}')
            rows.append(r)
    with open('stage_p.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(cfgs)} configs x {REPS} reps = {len(rows)} runs '
          f'-> stage_p.csv  (ceiling at this load: '
          f'{FIXED["num_clients"] * FIXED["max_async"] // 5})')


if __name__ == '__main__':
    main()
