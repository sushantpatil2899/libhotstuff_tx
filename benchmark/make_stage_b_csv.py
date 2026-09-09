#!/usr/bin/env python3
"""Stage B: block_size x max_async grid, varied independently.

Stage A parameterised load as depth (max_async = k * block_size), which
confounded the two: the block_size sweep also swept max_async. This grid
varies them independently so each can be read on its own, and so the
saturation point of each axis is visible.

Only legal cells are emitted. src/consensus.cpp commits a block once
three certified blocks sit directly above it, and measurement on
2026-09-08 showed max_async/block_size of 2 and 3 producing zero
commits while 5 committed normally, so every cell here holds
max_async >= 5 * block_size.

Small max_async is only reachable at small block_size for that reason,
which is why the block_size rows have different lengths.

Everything else is pinned at the Stage A centre: threads 4/4/4,
sb_users 1e6, prob_choose_mtx 0.9, skew 0.1, no injected latency. The
surface this produces is therefore characterised at those settings.

No expected outcome is recorded.
"""
import csv

FIELDS = [
    'run_id', 'nodes', 'num_clients', 'iter_count', 'max_async', 'duration',
    'collocate_client', 'block_size', 'pace_maker',
    'nworker', 'repnworker', 'clinworker', 'repburst', 'cliburst',
    'sb_users', 'sb_prob_choose_mtx', 'sb_skew_factor',
    'lat_node0', 'lat_node1', 'lat_node2', 'lat_node3',
]

FIXED = {
    'nodes': 4, 'num_clients': 1, 'iter_count': -1, 'duration': 60,
    'collocate_client': 'false', 'pace_maker': 'dummy',
    'nworker': 4, 'repnworker': 4, 'clinworker': 4,
    'repburst': 1000, 'cliburst': 1000,
    'sb_users': 10**6, 'sb_prob_choose_mtx': 0.9, 'sb_skew_factor': 0.1,
    'lat_node0': 0, 'lat_node1': 0, 'lat_node2': 0, 'lat_node3': 0,
}

BLOCK_SIZES = [100, 200, 400, 800, 1600]
MAX_ASYNC = [500, 1000, 2000, 4000, 8000, 16000, 32000]
MIN_DEPTH = 5

REPS = (1, 2, 3)


def main():
    rows = []
    cells = []
    for bs in BLOCK_SIZES:
        for ma in MAX_ASYNC:
            if ma < MIN_DEPTH * bs:
                continue
            cells.append((bs, ma))
            for rep in REPS:
                r = dict(FIXED)
                r['block_size'] = bs
                r['max_async'] = ma
                r['run_id'] = f'SB_bs{bs}_ma{ma}_r{rep}'
                rows.append(r)

    assert all(r['max_async'] >= MIN_DEPTH * r['block_size'] for r in rows)

    with open('stage_b.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f'{len(cells)} cells x {len(REPS)} reps = {len(rows)} runs '
          f'-> stage_b.csv\n')
    hdr = 'bs \\ ma  ' + ''.join(f'{m:>8}' for m in MAX_ASYNC)
    print(hdr)
    for bs in BLOCK_SIZES:
        line = f'{bs:<9}'
        for ma in MAX_ASYNC:
            line += f'{("k=" + str(ma // bs)) if (bs, ma) in cells else ".":>8}'
        print(line)


if __name__ == '__main__':
    main()
