#!/usr/bin/env python3
"""Stage O: does batching or in-flight load change anything under delay?

Stage N measured the collapse but cannot attribute it, because its four
baselines vary block_size, clients and max_async together. This stage
separates the two candidate knobs, holding everything else fixed at
8 clients, threads 4, 90% writes, skew 0.1.

  Axis A -- batching at fixed load
      clients 8, max_async 4000 (32,000 outstanding, the legal ceiling
      for block_size 6400), block_size 800 / 1600 / 3200 / 6400

  Axis B -- in-flight load at fixed batching
      block_size 3200, clients 8, max_async 8000 / 16000 / 32000
      (max_async 4000 at bs3200 comes from axis A)

Each under three network conditions:
      ctl       no delay
      lead100   leader (replica 1) delayed 100 ms
      lead200   leader delayed 200 ms

(4 + 3) x 3 conditions = 21 configs x 3 reps = 63 runs.

Rep-major order, shuffled within each pass with a fixed seed. Every run
records measured round trips in rtt.json.

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
         'num_clients': 8, 'nworker': 4, 'repnworker': 4, 'clinworker': 4,
         'repburst': 1000, 'cliburst': 1000, 'sb_users': 10**6,
         'sb_prob_choose_mtx': '0.9', 'sb_skew_factor': '0.1',
         'lat_node0': 0, 'lat_node2': 0, 'lat_node3': 0}

CELLS = ([(bs, 4000) for bs in (800, 1600, 3200, 6400)]      # axis A
         + [(3200, ma) for ma in (8000, 16000, 32000)])      # axis B
CONDITIONS = {'ctl': 0, 'lead100': 100, 'lead200': 200}
REPS = 3
SEED = 17


def main():
    cfgs = [(bs, ma, c) for bs, ma in CELLS for c in CONDITIONS]
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(cfgs)
        rng.shuffle(order)
        for bs, ma, cond in order:
            assert FIXED['num_clients'] * ma >= 5 * bs, (bs, ma)
            r = dict(FIXED)
            r.update(block_size=bs, max_async=ma,
                     lat_node1=CONDITIONS[cond],
                     run_id=f'O_bs{bs}_ma{ma}_{cond}_r{rep}')
            rows.append(r)
    with open('stage_o.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(cfgs)} configs x {REPS} reps = {len(rows)} runs '
          f'-> stage_o.csv')


if __name__ == '__main__':
    main()
