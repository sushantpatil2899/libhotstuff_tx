#!/usr/bin/env python3
"""Stage C: extend max_async past the top of the Stage B grid.

Stage B sampled max_async up to 32,000 and every cell landed between
76,042 and 90,541 tps. That grid cannot say whether ~90k is a ceiling of
the system or simply the top of the sampled region, because it has no
points above 32,000.

This sweep pushes max_async to 256,000 across four block sizes.
ma=32,000 is repeated from Stage B as an overlap anchor, so the two
sweeps can be checked against each other rather than assumed
comparable.

Every cell holds max_async >= 5 * block_size.

Other parameters are pinned at the Stage B settings (threads 4/4/4,
sb_users 1e6, prob_choose_mtx 0.9, skew 0.1, no injected latency) so
the two surfaces are directly comparable.

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

BLOCK_SIZES = [100, 200, 400, 800]
MAX_ASYNC = [32000, 64000, 128000, 256000]
MIN_DEPTH = 5
REPS = (1, 2, 3)


def main():
    rows, cells = [], []
    for bs in BLOCK_SIZES:
        for ma in MAX_ASYNC:
            if ma < MIN_DEPTH * bs:
                continue
            cells.append((bs, ma))
            for rep in REPS:
                r = dict(FIXED)
                r['block_size'] = bs
                r['max_async'] = ma
                r['run_id'] = f'SC_bs{bs}_ma{ma}_r{rep}'
                rows.append(r)

    assert all(r['max_async'] >= MIN_DEPTH * r['block_size'] for r in rows)

    with open('stage_c.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f'{len(cells)} cells x {len(REPS)} reps = {len(rows)} runs '
          f'-> stage_c.csv\n')
    print('bs \\ ma  ' + ''.join(f'{m:>9}' for m in MAX_ASYNC))
    for bs in BLOCK_SIZES:
        line = f'{bs:<9}'
        for ma in MAX_ASYNC:
            line += f'{("k=" + str(ma // bs)) if (bs, ma) in cells else ".":>9}'
        print(line)


if __name__ == '__main__':
    main()
