#!/usr/bin/env python3
"""Re-run the 9 Stage D3 cells whose rep spread exceeded 15%, at 7 reps.

Stage D3 ran 3 reps per cell. Nine cells came back with a spread of
(max-min)/mean above 15%, the worst at 112.4% -- meaning that cell's
three runs disagreed by more than its own average. Point estimates from
those cells cannot be relied on, and one of them sits inside the
clients 16-vs-8 edge comparison that the edge rule declined to call.

Seven reps instead of three so a median is available rather than an
average that one anomalous run can dominate.

Cells and their Stage D3 spreads:
  bs=3200 c=8  ma=64000  112.4%
  bs=1600 c=8  ma=64000   43.6%
  bs=3200 c=16 ma=1000    30.6%
  bs=800  c=16 ma=64000   29.9%
  bs=400  c=2  ma=64000   24.7%
  bs=200  c=8  ma=1000    18.0%
  bs=200  c=2  ma=64000   16.7%
  bs=3200 c=16 ma=16000   15.7%
  bs=400  c=8  ma=4000    15.1%
"""
import csv

FIELDS = ['run_id', 'nodes', 'num_clients', 'iter_count', 'max_async',
          'duration', 'collocate_client', 'block_size', 'pace_maker',
          'nworker', 'repnworker', 'clinworker', 'repburst', 'cliburst',
          'sb_users', 'sb_prob_choose_mtx', 'sb_skew_factor',
          'lat_node0', 'lat_node1', 'lat_node2', 'lat_node3']

FIXED = {'nodes': 4, 'iter_count': -1, 'duration': 60,
         'collocate_client': 'false', 'pace_maker': 'dummy',
         'nworker': 4, 'repnworker': 4, 'clinworker': 4,
         'repburst': 1000, 'cliburst': 1000, 'sb_users': 10**6,
         'sb_prob_choose_mtx': 0.9, 'sb_skew_factor': 0.1,
         'lat_node0': 0, 'lat_node1': 0, 'lat_node2': 0, 'lat_node3': 0}

CELLS = [(3200, 8, 64000), (1600, 8, 64000), (3200, 16, 1000),
         (800, 16, 64000), (400, 2, 64000), (200, 8, 1000),
         (200, 2, 64000), (3200, 16, 16000), (400, 8, 4000)]

# The 8-client half of the worst edge comparison is already in CELLS
# (bs=3200 c=8 ma=64000). Its 16-client counterpart was clean (2.1%)
# and is not re-run.

REPS = 7


def main():
    rows = []
    for bs, nc, ma in CELLS:
        assert nc * ma >= 5 * bs, (bs, nc, ma)
        for rep in range(1, REPS + 1):
            r = dict(FIXED)
            r['block_size'] = bs
            r['num_clients'] = nc
            r['max_async'] = ma
            r['run_id'] = f'RR_bs{bs}_c{nc}_ma{ma}_r{rep}'
            rows.append(r)
    with open('rerun_noisy.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(CELLS)} cells x {REPS} reps = {len(rows)} runs '
          f'-> rerun_noisy.csv')


if __name__ == '__main__':
    main()
