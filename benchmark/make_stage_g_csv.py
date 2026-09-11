#!/usr/bin/env python3
"""Stage G: block_size extension to 6400, crossed with clients, max_async,
threads and write ratio.

Section 5 of BASELINE_ANALYSIS.md found block_size still rising from 1600
to 3200 at four (clients, max_async) slices, the highest measured level.
This stage adds 6400 and keeps 3200 as the overlap with Stage D3.

  block_size   3200, 6400
  clients      4, 8, 16
  max_async    1000, 4000, 16000   (64000 was flat in Stage C/D3 and is
                                    where collapsed runs concentrated)
  threads      2, 4, 8             (16 matched 8 at every baseline)
  write ratio  mtx 0.1, 0.9

Only cells with clients x max_async >= 5 x block_size are generated; below
that ratio the 3-chain commit rule stalls (section 6). That leaves 7
(bs, c, ma) cells at 3200 and 5 at 6400.

skew = 0.1 and sb_users = 1e6, as in every other stage.

Row order: rep-major (every config's rep 1, then every rep 2, then rep 3),
shuffled within each pass with a fixed seed, so drift over the ~5h sweep
is spread across configs instead of landing on whichever ran last.

No expected outcome is recorded.
"""
import csv
import itertools
import random

FIELDS = ['run_id', 'nodes', 'num_clients', 'iter_count', 'max_async',
          'duration', 'collocate_client', 'block_size', 'pace_maker',
          'nworker', 'repnworker', 'clinworker', 'repburst', 'cliburst',
          'sb_users', 'sb_prob_choose_mtx', 'sb_skew_factor',
          'lat_node0', 'lat_node1', 'lat_node2', 'lat_node3']

FIXED = {'nodes': 4, 'iter_count': -1, 'duration': 60,
         'collocate_client': 'false', 'pace_maker': 'dummy',
         'repburst': 1000, 'cliburst': 1000, 'sb_users': 10**6,
         'sb_skew_factor': '0.1',
         'lat_node0': 0, 'lat_node1': 0, 'lat_node2': 0, 'lat_node3': 0}

BLOCK_SIZES = (3200, 6400)
CLIENTS = (4, 8, 16)
MAX_ASYNC = (1000, 4000, 16000)
THREADS = (2, 4, 8)
MTX = ('0.1', '0.9')
REPS = 3
SEED = 7


def legal(bs, c, ma):
    return c * ma >= 5 * bs


def main():
    cells = [(bs, c, ma) for bs, c, ma
             in itertools.product(BLOCK_SIZES, CLIENTS, MAX_ASYNC)
             if legal(bs, c, ma)]
    configs = [(bs, c, ma, t, m) for (bs, c, ma), t, m
               in itertools.product(cells, THREADS, MTX)]
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(configs)
        rng.shuffle(order)
        for bs, c, ma, t, m in order:
            r = dict(FIXED)
            r['block_size'] = bs
            r['num_clients'] = c
            r['max_async'] = ma
            r['nworker'] = r['repnworker'] = r['clinworker'] = t
            r['sb_prob_choose_mtx'] = m
            r['run_id'] = f'G_bs{bs}_c{c}_ma{ma}_t{t}_mtx{m}_r{rep}'
            rows.append(r)
    with open('stage_g.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    for bs in BLOCK_SIZES:
        print(f'  bs={bs}: {[(c, ma) for b, c, ma in cells if b == bs]}')
    print(f'{len(cells)} (bs,c,ma) cells x {len(THREADS)} threads x '
          f'{len(MTX)} mtx = {len(configs)} configs x {REPS} reps = '
          f'{len(rows)} runs -> stage_g.csv')


if __name__ == '__main__':
    main()
