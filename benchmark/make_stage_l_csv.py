#!/usr/bin/env python3
"""Stage L: a replica fails mid-run, at B1-B4, under the rr pacemaker.

rr is the only pacemaker in this code that can change leader
(PaceMakerDummyFixed never does). The rr shakedown measured it leading from
replica 0 with no rotation in steady state. So:

  arms  ctl           no failure
        lead_crash    replica 0 (rr leader) gets SIGKILL
        lead_freeze   replica 0 gets SIGSTOP
        f3_crash      replica 3 (a follower, not next in rotation) SIGKILL
        f3_freeze     replica 3 SIGSTOP

Leader and follower failures are never combined.

Each run lasts 120 s. The failure lands 40 s after all clients are
launched, leaving a 30 s pre-failure window after a 10 s warm-up and 80 s
afterwards. Protocol logging is on for the sweep (fab --proto-log), so
rotations and the new leader are in the replica logs; controls are logged
too. The sampler is on.

4 baselines x 5 arms x 5 reps = 100 runs, rep-major order, shuffled with a
fixed seed. No expected outcome is recorded.
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
BASELINES = {'B1': dict(bs=200, c=2, ma=1000),
             'B2': dict(bs=800, c=4, ma=1000),
             'B3': dict(bs=1600, c=8, ma=1000),
             'B4': dict(bs=3200, c=8, ma=4000)}
ARMS = {'ctl': (-1, ''), 'lead_crash': (0, 'crash'),
        'lead_freeze': (0, 'freeze'), 'f3_crash': (3, 'crash'),
        'f3_freeze': (3, 'freeze')}
REPS = 5
SEED = 37


def main():
    cfgs = [(b, a) for b in BASELINES for a in ARMS]
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(cfgs)
        rng.shuffle(order)
        for b, a in order:
            p = BASELINES[b]
            node, kind = ARMS[a]
            rows.append(dict(FIXED, block_size=p['bs'], num_clients=p['c'],
                             max_async=p['ma'], fail_node=node,
                             fail_type=kind, run_id=f'L_{b}_{a}_r{rep}'))
    with open('stage_l.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(cfgs)} configs x {REPS} reps = {len(rows)} runs -> stage_l.csv')


if __name__ == '__main__':
    main()
