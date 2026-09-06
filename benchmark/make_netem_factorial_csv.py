#!/usr/bin/env python3
"""Generate the network-latency factorial sweep: 192 latency-assignment
combinations x 2 baseline (block_size, max_async) points = 384 runs.

Node roles: node1 is the fixed leader (dummy pacemaker, proposer index
1). node0, node2, node3 are followers. "1 follower" and "2 followers"
use node0 and {node0, node2} as the fixed representative choice (per
discussion -- the point is testing "a follower being delayed", not an
exhaustive search over which one).

Shapes, each swept over LADDER = [50, 100, 150, 200] ms, full
factorial (every node varying in a shape takes every ladder value
independently, crossed with every other varying node in that shape):

  1. leader only            -- node1 varies                  (4 runs)
  2. 1 follower only        -- node0 varies                  (4 runs)
  3. leader + 1 follower    -- node1 x node0                 (16 runs)
  4. 2 followers            -- node0 x node2                 (16 runs)
  5. leader + 2 followers   -- node1 x node0 x node2          (64 runs)
  6. 3 followers            -- node0 x node2 x node3          (64 runs)
  7. all 4 distinct         -- permutations of LADDER onto    (24 runs)
                               (node0, node1, node2, node3)
                               (all four mutually different,
                               not the full 4^4=256 with repeats)

  Total per baseline point: 192. x 2 baseline points = 384.

Baseline points: (block_size=200, max_async=400) -- recommended --
and (block_size=3200, max_async=8000) -- extreme.
"""
import csv
from itertools import permutations, product

LADDER = [50, 100, 150, 200]
BASELINES = [(200, 400), (3200, 8000)]

FIXED = {
    'nodes': 4,
    'num_clients': 1,
    'iter_count': -1,
    'duration': 60,
    'collocate_client': 'false',
    'pace_maker': 'dummy',
    'nworker': 4, 'repnworker': 4, 'clinworker': 4,
    'repburst': 1000, 'cliburst': 1000,
    'sb_users': 1000, 'sb_prob_choose_mtx': 0.9, 'sb_skew_factor': 0.1,
}

FIELDNAMES = [
    'run_id', 'nodes', 'num_clients', 'iter_count', 'max_async', 'duration',
    'collocate_client', 'block_size', 'pace_maker',
    'nworker', 'repnworker', 'clinworker', 'repburst', 'cliburst',
    'sb_users', 'sb_prob_choose_mtx', 'sb_skew_factor',
    'lat_node0', 'lat_node1', 'lat_node2', 'lat_node3',
]


def shape_rows():
    """Yield (shape_tag, {node_idx: latency_ms}) for all 192 combos."""
    # 1. leader only
    for v in LADDER:
        yield 'leaderonly', {1: v}
    # 2. 1 follower only (node0)
    for v in LADDER:
        yield 'f0only', {0: v}
    # 3. leader + 1 follower (node1 x node0)
    for v1, v0 in product(LADDER, LADDER):
        yield 'leader_f0', {1: v1, 0: v0}
    # 4. 2 followers (node0 x node2)
    for v0, v2 in product(LADDER, LADDER):
        yield 'f0_f2', {0: v0, 2: v2}
    # 5. leader + 2 followers (node1 x node0 x node2)
    for v1, v0, v2 in product(LADDER, LADDER, LADDER):
        yield 'leader_f0_f2', {1: v1, 0: v0, 2: v2}
    # 6. 3 followers (node0 x node2 x node3)
    for v0, v2, v3 in product(LADDER, LADDER, LADDER):
        yield 'f0_f2_f3', {0: v0, 2: v2, 3: v3}
    # 7. all 4 distinct: every permutation of LADDER onto the 4 nodes
    for perm in permutations(LADDER):
        yield 'all4distinct', {0: perm[0], 1: perm[1], 2: perm[2], 3: perm[3]}


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', default='netem_factorial.csv')
    args = p.parse_args()

    n = 0
    with open(args.out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for bs, ma in BASELINES:
            for shape_idx, (tag, lat_map) in enumerate(shape_rows()):
                row = dict(FIXED)
                row['block_size'] = bs
                row['max_async'] = ma
                for i in range(4):
                    row[f'lat_node{i}'] = lat_map.get(i, 0)
                lat_str = '-'.join(str(row[f'lat_node{i}']) for i in range(4))
                row['run_id'] = f'NF_bs{bs}_ma{ma}_{tag}_{shape_idx}_{lat_str}'
                w.writerow(row)
                n += 1

    print(f'Wrote {n} rows to {args.out}')


if __name__ == '__main__':
    main()
