#!/usr/bin/env python3
"""Stage F: confirm the Stage E effects at 7 reps.

Stage E ran 3 reps and three comparisons cleared their rep spread:

  B3 threads        t2 was -8.2% vs t4; t4/t8/t16 identical within 0.6%
                    (separation 8.4% vs worst spread 6.4%)
  B1 write ratio    mtx=0.1 +6.4% over mtx=0.9, monotonic
                    (separation 6.2% vs 5.1%)
  B2 write ratio    mtx=0.1 +5.9% over mtx=0.9, non-monotonic
                    (separation 7.4% vs 5.6%)

Two more are included because they are close to their floor or produced
a notable absolute value:

  B3 skew           skew=0.9 +3.1%, separation 3.9% vs 3.4% -- clears by
                    half a point, treated as unconfirmed
  B4 write ratio    separation 4.6% vs 8.3% (not resolvable at 3 reps),
                    but mtx=0.5 measured 483,766 tps at 2.3% spread,
                    above any other figure in the dataset

7 reps because the earlier re-run showed single collapsed repetitions
moving a 3-rep result by up to 50%, and because a median needs enough
points to be robust to one.

Baselines (frontier of the Stage D3 grid):
  B1 bs=200  c=2  ma=1000
  B2 bs=800  c=4  ma=1000
  B3 bs=1600 c=8  ma=1000
  B4 bs=3200 c=8  ma=4000

Baseline variant is threads=4, skew=0.1, mtx=0.9.

No expected outcome is recorded.
"""
import csv

FIELDS = ['run_id', 'nodes', 'num_clients', 'iter_count', 'max_async',
          'duration', 'collocate_client', 'block_size', 'pace_maker',
          'nworker', 'repnworker', 'clinworker', 'repburst', 'cliburst',
          'sb_users', 'sb_prob_choose_mtx', 'sb_skew_factor',
          'lat_node0', 'lat_node1', 'lat_node2', 'lat_node3']

FIXED = {'nodes': 4, 'iter_count': -1, 'duration': 60,
         'collocate_client': 'false', 'pace_maker': 'dummy',
         'repburst': 1000, 'cliburst': 1000, 'sb_users': 10**6,
         'lat_node0': 0, 'lat_node1': 0, 'lat_node2': 0, 'lat_node3': 0}

B = {'B1': dict(bs=200, c=2, ma=1000),
     'B2': dict(bs=800, c=4, ma=1000),
     'B3': dict(bs=1600, c=8, ma=1000),
     'B4': dict(bs=3200, c=8, ma=4000)}

# (baseline, threads, skew, mtx)
CONFIGS = [
    ('B3', 2, '0.1', '0.9'),     # threads floor
    ('B3', 4, '0.1', '0.9'),     # B3 baseline, also the skew 0.1 point
    ('B3', 8, '0.1', '0.9'),
    ('B3', 4, '0.9', '0.9'),     # skew high
    ('B1', 4, '0.1', '0.1'),
    ('B1', 4, '0.1', '0.5'),
    ('B1', 4, '0.1', '0.9'),
    ('B2', 4, '0.1', '0.1'),
    ('B2', 4, '0.1', '0.5'),
    ('B2', 4, '0.1', '0.9'),
    ('B4', 4, '0.1', '0.1'),
    ('B4', 4, '0.1', '0.5'),
    ('B4', 4, '0.1', '0.9'),
]
REPS = 7


def main():
    rows = []
    for name, t, skew, mtx in CONFIGS:
        b = B[name]
        assert b['c'] * b['ma'] >= 5 * b['bs'], name
        for rep in range(1, REPS + 1):
            r = dict(FIXED)
            r['block_size'] = b['bs']
            r['num_clients'] = b['c']
            r['max_async'] = b['ma']
            r['nworker'] = r['repnworker'] = r['clinworker'] = t
            r['sb_skew_factor'] = skew
            r['sb_prob_choose_mtx'] = mtx
            r['run_id'] = f'F_{name}_t{t}_skew{skew}_mtx{mtx}_r{rep}'
            rows.append(r)
    with open('stage_f.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(CONFIGS)} configs x {REPS} reps = {len(rows)} runs '
          f'-> stage_f.csv')


if __name__ == '__main__':
    main()
