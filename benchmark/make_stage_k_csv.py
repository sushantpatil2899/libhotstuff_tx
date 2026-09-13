#!/usr/bin/env python3
"""Stage K: fewer physical cores on selected replicas, at B1-B4.

Stage U measured B3 unrestricted: each replica used 4.49-5.48 cores of its
64 logical CPUs, with its two busiest threads at 78-95% of a core. The core
levels bracket that use:

  cores      8, 6, 4, 3, 2, 1   (physical cores 1..N via taskset)
  scenarios  which replicas are pinned (replica 1 is the fixed leader)
               lead         {1}
               f0           {0}
               f3           {3}
               lead_f0      {1, 0}
               lead_f3      {1, 3}
               lead_f0_f3   {1, 0, 3}
  control    no replica pinned, per baseline
  baselines  B1-B4 at threads 4, 90% writes, skew 0.1

4 x (6 x 6 + 1) = 148 configs x 5 reps = 740 runs. Rep-major order,
shuffled within each pass with a fixed seed.

Every run samples compute on every host (sample_compute), which records
each replica's allowed-CPU list per process and per thread. Pinning is
verified per run from that, the way Stage N verified delay from rtt.json.
60 s runs on the fixed window (meas_warmup 10 s, meas_cooldown 2 s).

No expected outcome is recorded.
"""
import csv
import random

FIELDS = ['run_id', 'nodes', 'num_clients', 'iter_count', 'max_async',
          'duration', 'meas_warmup', 'meas_cooldown', 'sample_compute',
          'collocate_client', 'block_size', 'pace_maker', 'nworker',
          'repnworker', 'clinworker', 'repburst', 'cliburst', 'sb_users',
          'sb_prob_choose_mtx', 'sb_skew_factor', 'lat_node0', 'lat_node1',
          'lat_node2', 'lat_node3', 'cpu_node0', 'cpu_node1', 'cpu_node2',
          'cpu_node3']
FIXED = {'nodes': 4, 'iter_count': -1, 'duration': 60, 'meas_warmup': 10,
         'meas_cooldown': 2, 'sample_compute': 'true',
         'collocate_client': 'false', 'pace_maker': 'dummy', 'nworker': 4,
         'repnworker': 4, 'clinworker': 4, 'repburst': 1000,
         'cliburst': 1000, 'sb_users': 10**6, 'sb_prob_choose_mtx': '0.9',
         'sb_skew_factor': '0.1', 'lat_node0': 0, 'lat_node1': 0,
         'lat_node2': 0, 'lat_node3': 0}
BASELINES = {'B1': dict(bs=200, c=2, ma=1000),
             'B2': dict(bs=800, c=4, ma=1000),
             'B3': dict(bs=1600, c=8, ma=1000),
             'B4': dict(bs=3200, c=8, ma=4000)}
SCENARIOS = {'lead': (1,), 'f0': (0,), 'f3': (3,), 'lead_f0': (1, 0),
             'lead_f3': (1, 3), 'lead_f0_f3': (1, 0, 3)}
LEVELS = (8, 6, 4, 3, 2, 1)
REPS = 5
SEED = 31


def configs():
    for b in BASELINES:
        yield b, 'ctl', 0
        for s in SCENARIOS:
            for n in LEVELS:
                yield b, s, n


def main():
    cfgs = list(configs())
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(cfgs)
        rng.shuffle(order)
        for b, s, n in order:
            p = BASELINES[b]
            r = dict(FIXED, block_size=p['bs'], num_clients=p['c'],
                     max_async=p['ma'])
            pinned = SCENARIOS.get(s, ())
            for i in range(4):
                r[f'cpu_node{i}'] = n if i in pinned else 0
            r['run_id'] = f'K_{b}_{s}_c{n}_r{rep}'
            rows.append(r)
    with open('stage_k.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(cfgs)} configs x {REPS} reps = {len(rows)} runs -> stage_k.csv')


if __name__ == '__main__':
    main()
