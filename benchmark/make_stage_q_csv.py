#!/usr/bin/env python3
"""Stage Q: re-measure the Stage O and P cells a 60 s run cannot measure.

Nine cells had mean latency of 14 s or more. A 60 s run never reaches
steady state there, and the old first-to-last-commit throughput inflated
them (Stage P block_size 800 / leader 200 ms: reported 9,076 tps, 120,800
commits in 60 s). The fixed-window client measurement (commit 2c3224d)
makes a correct measurement possible, given a long enough run.

A smoke run of one such cell showed commits arriving in bursts of about
max_async per client, roughly every 32 s. So the window must span several
cycles:
  duration 180 s, meas_warmup 40 s (above the largest latency, 32 s),
  meas_cooldown 2 s  ->  ~138 s measured, ~4 cycles at the slowest cell

Also included is one anchor cell per load that 60 s runs did measure
cleanly, re-measured the same way, so corrected cells can be set against
the old clean numbers:
  O anchor: bs3200 / ma4000 / leader 100 ms
  P anchor: bs6400 / ma16000 / leader 100 ms

8 clients, threads 4, 90% writes, skew 0.1, dummy pacemaker, as in O/P.
11 cells x 3 reps = 33 runs. Raw client logs are kept (parser --no-prune).

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

FIXED = {'nodes': 4, 'num_clients': 8, 'iter_count': -1, 'duration': 180,
         'meas_warmup': 40, 'meas_cooldown': 2, 'collocate_client': 'false',
         'pace_maker': 'dummy', 'nworker': 4, 'repnworker': 4,
         'clinworker': 4, 'repburst': 1000, 'cliburst': 1000,
         'sb_users': 10**6, 'sb_prob_choose_mtx': '0.9',
         'sb_skew_factor': '0.1', 'lat_node0': 0, 'lat_node2': 0,
         'lat_node3': 0}

# (source stage, block_size, max_async, leader delay ms, role)
CELLS = [
    ('O', 800, 4000, 200, 'slow'),
    ('O', 3200, 16000, 200, 'slow'),
    ('O', 3200, 32000, 100, 'slow'),
    ('O', 3200, 32000, 200, 'slow'),
    ('P', 800, 16000, 100, 'slow'),
    ('P', 800, 16000, 200, 'slow'),
    ('P', 1600, 16000, 100, 'slow'),
    ('P', 1600, 16000, 200, 'slow'),
    ('P', 3200, 16000, 200, 'slow'),
    ('O', 3200, 4000, 100, 'anchor'),
    ('P', 6400, 16000, 100, 'anchor'),
]
REPS = 3
SEED = 23


def main():
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(CELLS)
        rng.shuffle(order)
        for src, bs, ma, d, role in order:
            assert FIXED['num_clients'] * ma >= 5 * bs
            r = dict(FIXED)
            r.update(block_size=bs, max_async=ma, lat_node1=d,
                     run_id=f'Q_{src}_bs{bs}_ma{ma}_lead{d}_{role}_r{rep}')
            rows.append(r)
    with open('stage_q.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(CELLS)} cells x {REPS} reps = {len(rows)} runs -> stage_q.csv')


if __name__ == '__main__':
    main()
