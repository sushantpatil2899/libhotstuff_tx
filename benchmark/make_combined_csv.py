#!/usr/bin/env python3
"""Generate combined.csv: threads x block_size x max_async, replicated.

Follow-up to Phase 0 (thread calibration, inconclusive at 1 rep) and
Phase 1 (block_size didn't matter across {100,200,400,800}, throughput
still slowly climbing at max_async up to 8000). This crosses all three
factors at the higher-load range with 3 reps per config, to check
whether scaled threads' +5.2% edge (seen only at ma=1300, 1 rep) is
real and growing with load, and whether larger block_size does
anything once threads are no longer at their calibrated default.

    python3 make_combined_csv.py --out combined.csv
"""
import csv

THREAD_CONFIGS = [
    ('default', 4, 4, 4),
    ('scaled', 16, 8, 16),
]
BLOCK_SIZES = [200, 800, 1600, 3200]
MAX_ASYNC = [2000, 3000, 5000, 8000]
REPS = 3

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
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', default='combined.csv')
    args = p.parse_args()

    n = 0
    with open(args.out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for thread_name, nworker, repnworker, clinworker in THREAD_CONFIGS:
            for bs in BLOCK_SIZES:
                for ma in MAX_ASYNC:
                    for rep in range(1, REPS + 1):
                        row = dict(FIXED)
                        row['run_id'] = f'COMB_{thread_name}_bs{bs}_ma{ma}_r{rep}'
                        row['block_size'] = bs
                        row['max_async'] = ma
                        row['nworker'] = nworker
                        row['repnworker'] = repnworker
                        row['clinworker'] = clinworker
                        w.writerow(row)
                        n += 1

    print(f'Wrote {n} rows to {args.out} '
          f'({len(THREAD_CONFIGS)} thread configs x {len(BLOCK_SIZES)} block '
          f'sizes x {len(MAX_ASYNC)} max_async x {REPS} reps)')


if __name__ == '__main__':
    main()
