#!/usr/bin/env python3
"""Stage H: 7-rep check of the two Stage G results worth confirming.

All at the adopted settings: threads=4, mtx=0.9, skew=0.1.

  1. bs3200 c16 ma1000  vs  bs3200 c8 ma4000 (B4)
     Stage G: 482,211 tps / 33.3 ms against 474,923 / 67.3 ms.
  2. bs6400 c16 ma4000  vs  bs3200 c16 ma4000
     Stage G: 454,309 against 415,681 (+9.3%), the one 6400-vs-3200 pair
     resolvable at the adopted settings.

Row order: rep-major, shuffled within each pass with a fixed seed.

No expected outcome is recorded.
"""
import csv
import random

FIELDS = ['run_id', 'nodes', 'num_clients', 'iter_count', 'max_async',
          'duration', 'collocate_client', 'block_size', 'pace_maker',
          'nworker', 'repnworker', 'clinworker', 'repburst', 'cliburst',
          'sb_users', 'sb_prob_choose_mtx', 'sb_skew_factor',
          'lat_node0', 'lat_node1', 'lat_node2', 'lat_node3']

FIXED = {'nodes': 4, 'iter_count': -1, 'duration': 60,
         'collocate_client': 'false', 'pace_maker': 'dummy',
         'repburst': 1000, 'cliburst': 1000, 'sb_users': 10**6,
         'sb_prob_choose_mtx': '0.9', 'sb_skew_factor': '0.1',
         'nworker': 4, 'repnworker': 4, 'clinworker': 4,
         'lat_node0': 0, 'lat_node1': 0, 'lat_node2': 0, 'lat_node3': 0}

CELLS = [(3200, 16, 1000), (3200, 8, 4000), (6400, 16, 4000),
         (3200, 16, 4000)]
REPS = 7
SEED = 11


def main():
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(CELLS)
        rng.shuffle(order)
        for bs, c, ma in order:
            assert c * ma >= 5 * bs
            r = dict(FIXED)
            r.update(block_size=bs, num_clients=c, max_async=ma,
                     run_id=f'H_bs{bs}_c{c}_ma{ma}_r{rep}')
            rows.append(r)
    with open('stage_h.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(CELLS)} cells x {REPS} reps = {len(rows)} runs -> stage_h.csv')


if __name__ == '__main__':
    main()
