#!/usr/bin/env python3
"""Stage N: injected network latency at the four adopted baselines.

Scenarios, as per-replica latency values (replica 1 is the fixed leader).
A link between two replicas gets max(lat_a, lat_b), both directions;
client traffic is never delayed (benchmark/netem.py).

  lead   leader only           lat_node1 = d
  f1     one follower          lat_node0 = d
  f2     two followers         lat_node0 = lat_node2 = d
  f3     three followers       lat_node0 = lat_node2 = lat_node3 = d

"All nodes delayed" is omitted: under the max rule every link has a
follower end, so it produces exactly the tc rules of f3.

  d          50, 100, 150, 200 ms
  control    all four lat_node = 0, per baseline
  baselines  B1-B4 at threads 4, 90% writes, skew 0.1 (BASELINE_ANALYSIS
             section 10b)

4 baselines x (4 scenarios x 4 delays + 1 control) = 68 configs x 5 reps
= 340 runs. Rep-major order, shuffled within each pass with a fixed seed.

Each run also records measured round trips in rtt.json
(RemoteBench._probe_rtt).

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
         'nworker': 4, 'repnworker': 4, 'clinworker': 4,
         'repburst': 1000, 'cliburst': 1000, 'sb_users': 10**6,
         'sb_prob_choose_mtx': '0.9', 'sb_skew_factor': '0.1'}

BASELINES = {'B1': dict(bs=200, c=2, ma=1000),
             'B2': dict(bs=800, c=4, ma=1000),
             'B3': dict(bs=1600, c=8, ma=1000),
             'B4': dict(bs=3200, c=8, ma=4000)}

# which replica indices carry the delay
SCENARIOS = {'lead': (1,), 'f1': (0,), 'f2': (0, 2), 'f3': (0, 2, 3)}
DELAYS = (50, 100, 150, 200)
REPS = 5
SEED = 13


def configs():
    for b in BASELINES:
        yield b, 'ctl', 0
        for s in SCENARIOS:
            for d in DELAYS:
                yield b, s, d


def main():
    cfgs = list(configs())
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(cfgs)
        rng.shuffle(order)
        for b, s, d in order:
            p = BASELINES[b]
            r = dict(FIXED)
            r.update(block_size=p['bs'], num_clients=p['c'],
                     max_async=p['ma'])
            delayed = SCENARIOS.get(s, ())
            for i in range(4):
                r[f'lat_node{i}'] = d if i in delayed else 0
            r['run_id'] = f'N_{b}_{s}_d{d}_r{rep}'
            rows.append(r)
    with open('stage_n.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(cfgs)} configs x {REPS} reps = {len(rows)} runs '
          f'-> stage_n.csv')


if __name__ == '__main__':
    main()
