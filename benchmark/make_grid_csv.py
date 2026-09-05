#!/usr/bin/env python3
"""Generate main_grid.csv: the block_size x max_async saturation grid.

Run this AFTER calibration.csv has been executed and you know which
thread config won (see PLAN.md, Phase 0). Pass the winning nworker /
repnworker / clinworker values; everything else is fixed at the
defaults this project settled on.

    python3 make_grid_csv.py --out main_grid.csv
    python3 make_grid_csv.py --out main_grid.csv --nworker 16 --repnworker 8 --clinworker 16

Block sizes {100, 200, 400, 800} bracket the two values that disagreed
across this repo's own hotstuff.conf (200) and gen_all.sh (400), with
one point below and one above. max_async {10, 25, 50, 100, 175, 250,
400, 600, 900, 1300} includes the repo's own default (175) as a
reference point and is denser at the low-mid range where the
throughput/latency knee is expected to sit.
"""
import argparse
import csv

BLOCK_SIZES = [100, 200, 400, 800]
MAX_ASYNC = [10, 25, 50, 100, 175, 250, 400, 600, 900, 1300]

FIXED = {
    'nodes': 4,
    'num_clients': 1,
    'iter_count': -1,
    'duration': 60,
    'collocate_client': 'false',
    'pace_maker': 'dummy',
    'repburst': 1000,
    'cliburst': 1000,
    'sb_users': 1000,
    'sb_prob_choose_mtx': 0.9,
    'sb_skew_factor': 0.1,
}

FIELDNAMES = [
    'run_id', 'nodes', 'num_clients', 'iter_count', 'max_async', 'duration',
    'collocate_client', 'block_size', 'pace_maker',
    'nworker', 'repnworker', 'clinworker', 'repburst', 'cliburst',
    'sb_users', 'sb_prob_choose_mtx', 'sb_skew_factor',
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', default='main_grid.csv')
    p.add_argument('--nworker', type=int, default=4)
    p.add_argument('--repnworker', type=int, default=4)
    p.add_argument('--clinworker', type=int, default=4)
    args = p.parse_args()

    with open(args.out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for bs in BLOCK_SIZES:
            for ma in MAX_ASYNC:
                row = dict(FIXED)
                row['run_id'] = f'GRID_bs{bs}_ma{ma}'
                row['block_size'] = bs
                row['max_async'] = ma
                row['nworker'] = args.nworker
                row['repnworker'] = args.repnworker
                row['clinworker'] = args.clinworker
                w.writerow(row)

    n = len(BLOCK_SIZES) * len(MAX_ASYNC)
    print(f'Wrote {n} rows to {args.out} '
          f'(nworker={args.nworker}, repnworker={args.repnworker}, '
          f'clinworker={args.clinworker})')


if __name__ == '__main__':
    main()
