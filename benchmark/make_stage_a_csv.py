#!/usr/bin/env python3
"""Stage A: one-factor-at-a-time screening around a single centre point.

15 distinct configurations x 3 reps = 45 runs.

Load is expressed as pipeline DEPTH k, with max_async = k * block_size,
rather than as a raw max_async. Measured on 2026-09-08: with
block_size=200, max_async=400 (k=2) produced 2 proposals and 0 commits,
and max_async=600 (k=3) produced 3 proposals and 0 commits, while
max_async=1000 (k=5) committed 27,536 blocks. src/consensus.cpp commits
a block only once three certified blocks sit directly on top of it, so
crossing block_size against raw max_async would generate cells that
cannot commit. Every cell here holds k >= 5.

skew_factor is constrained to (0, 1): cpp_random_distributions/
zipfian_int_distribution.h asserts theta > 0.0 && theta < 1.0. Builds
are Release, so NDEBUG removes that assert -- a value of 0 would not
fail loudly. 0 is therefore never used here.

No expected outcome is recorded for any factor. The purpose is to
measure which factors move throughput, not to confirm a prediction.
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
    'repburst': 1000, 'cliburst': 1000,
    'lat_node0': 0, 'lat_node1': 0, 'lat_node2': 0, 'lat_node3': 0,
}

# Centre point.
C = dict(bs=200, k=10, threads=4, mtx=0.9, skew=0.1, users=10**6)

LEVELS = {
    'bs':      [100, 200, 400, 800],
    'k':       [5, 10, 40],
    'threads': [2, 4, 8, 16],
    'mtx':     [0.1, 0.5, 0.9],
    'skew':    [0.1, 0.5, 0.9],
    'users':   [10**3, 10**6, 10**7],
}


def tag(c):
    u = {10**3: '1e3', 10**6: '1e6', 10**7: '1e7'}[c['users']]
    return (f"bs{c['bs']}_k{c['k']}_t{c['threads']}"
            f"_mtx{c['mtx']}_skew{c['skew']}_u{u}")


def row(c, rep):
    r = dict(FIXED)
    r['block_size'] = c['bs']
    r['max_async'] = c['k'] * c['bs']          # depth, never raw
    r['nworker'] = r['repnworker'] = r['clinworker'] = c['threads']
    r['sb_users'] = c['users']
    r['sb_prob_choose_mtx'] = c['mtx']
    r['sb_skew_factor'] = c['skew']
    r['run_id'] = f"SA_{tag(c)}_r{rep}"
    return r


def main():
    configs = {}
    for factor, values in LEVELS.items():
        for v in values:
            c = dict(C)
            c[factor] = v
            configs[tag(c)] = c            # dict keying collapses the centre

    rows = []
    for _, c in sorted(configs.items()):
        for rep in (1, 2, 3):
            rows.append(row(c, rep))

    assert all(r['max_async'] >= 5 * r['block_size'] for r in rows)

    with open('stage_a.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(configs)} configs x 3 reps = {len(rows)} runs -> stage_a.csv')
    for t in sorted(configs):
        print('  ', t)


if __name__ == '__main__':
    main()
