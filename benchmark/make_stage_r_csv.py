#!/usr/bin/env python3
"""Stage R: B4 against bs3200 / 16 clients / max_async 1000, on the
fixed-window measurement.

Stage H, with stalled runs excluded (BASELINE_ANALYSIS section 13.4),
found the candidate at the same throughput as B4 (476,782 vs 458,909,
p = 0.66) and half the latency (33.7 vs 69.7 ms, p = 0.0043), while
stalling in 2 of 7 runs against B4's 1 of 7. Those runs were measured on
the first-to-last-commit formula and classified after the fact. This
repeats the comparison on the fixed window, with enough runs to also
count stalls.

  B4         block_size 3200, clients 8,  max_async 4000
  candidate  block_size 3200, clients 16, max_async 1000
  both       threads 4, 90% writes, skew 0.1, dummy pacemaker, no delay
             duration 60 s, meas_warmup 10 s, meas_cooldown 2 s

10 reps each = 20 runs, interleaved and shuffled with a fixed seed.

Verdicts, fixed in advance: exact Mann-Whitney on tps_steady and on
latency_ms_mean_steady over non-stalled runs, two tests, confirmed at
p < 0.05 / 2 = 0.025. Stall counts are reported per cell; 10 runs each
can show a large difference in stall rate but not a small one.

No expected outcome is recorded.
"""
import csv
import random

FIELDS = ['run_id', 'nodes', 'num_clients', 'iter_count', 'max_async',
          'duration', 'meas_warmup', 'meas_cooldown', 'collocate_client',
          'block_size', 'pace_maker', 'nworker', 'repnworker', 'clinworker',
          'repburst', 'cliburst', 'sb_users', 'sb_prob_choose_mtx',
          'sb_skew_factor', 'lat_node0', 'lat_node1', 'lat_node2',
          'lat_node3']
FIXED = {'nodes': 4, 'iter_count': -1, 'duration': 60, 'meas_warmup': 10,
         'meas_cooldown': 2, 'collocate_client': 'false', 'block_size': 3200,
         'pace_maker': 'dummy', 'nworker': 4, 'repnworker': 4,
         'clinworker': 4, 'repburst': 1000, 'cliburst': 1000,
         'sb_users': 10**6, 'sb_prob_choose_mtx': '0.9',
         'sb_skew_factor': '0.1', 'lat_node0': 0, 'lat_node1': 0,
         'lat_node2': 0, 'lat_node3': 0}
CELLS = {'B4': (8, 4000), 'cand': (16, 1000)}
REPS = 10
SEED = 29


def main():
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(CELLS)
        rng.shuffle(order)
        for name in order:
            c, ma = CELLS[name]
            r = dict(FIXED)
            r.update(num_clients=c, max_async=ma,
                     run_id=f'R_{name}_bs3200_c{c}_ma{ma}_r{rep}')
            rows.append(r)
    with open('stage_r.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(CELLS)} cells x {REPS} reps = {len(rows)} runs -> stage_r.csv')


if __name__ == '__main__':
    main()
