#!/usr/bin/env python3
"""Stage E: threads, skew and write ratio re-tested at the four baselines.

Stage A found no resolvable effect for thread count, skew or write
ratio, but measured all three at a SINGLE operating point: bs=200,
max_async=2000, one client. Throughput there was ~85k. The baselines
below run 167k-460k with multiple clients, so Stage A's bound does not
carry over.

The four baselines are the throughput/latency frontier from the Stage D3
grid (medians, 7 reps where re-run):

  B1 lowest latency  bs=200  c=2  ma=1000   167,191 tps @ 12.0 ms
  B2 mid             bs=800  c=4  ma=1000   310,922 tps @ 12.9 ms
  B3 recommended     bs=1600 c=8  ma=1000   446,133 tps @ 18.0 ms
  B4 max throughput  bs=3200 c=8  ma=4000   459,963 tps @ 69.5 ms

One factor at a time around each baseline:

  threads (nworker/repnworker/clinworker together)  2, 4, 8, 16
  sb_skew_factor                                    0.1, 0.5, 0.9
  sb_prob_choose_mtx (write ratio)                  0.1, 0.5, 0.9

Baseline values are threads=4, skew=0.1, mtx=0.9, so the baseline cell
is shared by all three groups: 4 + 3 + 3 - 2 = 8 distinct configs per
baseline, 32 in total.

skew is held inside (0, 1): zipfian_int_distribution.h asserts
theta > 0 && theta < 1 and Release builds define NDEBUG, so 0 would not
fail loudly.

3 reps. Any config showing an apparent effect is to be re-run at 7 reps
before it is believed -- several Stage D3 cells contained a single
collapsed run that dominated a 3-rep mean.

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

BASELINES = {
    'B1': dict(bs=200, c=2, ma=1000),
    'B2': dict(bs=800, c=4, ma=1000),
    'B3': dict(bs=1600, c=8, ma=1000),
    'B4': dict(bs=3200, c=8, ma=4000),
}
THREADS = [2, 4, 8, 16]
SKEW = [0.1, 0.5, 0.9]
MTX = [0.1, 0.5, 0.9]
BASE = dict(t=4, skew=0.1, mtx=0.9)
REPS = 3


def main():
    rows, n = [], 0
    for name, b in BASELINES.items():
        assert b['c'] * b['ma'] >= 5 * b['bs'], name
        variants = {}
        for t in THREADS:
            variants[(t, BASE['skew'], BASE['mtx'])] = None
        for s in SKEW:
            variants[(BASE['t'], s, BASE['mtx'])] = None
        for m in MTX:
            variants[(BASE['t'], BASE['skew'], m)] = None
        for (t, s, m) in sorted(variants):
            n += 1
            for rep in range(1, REPS + 1):
                r = dict(FIXED)
                r['block_size'] = b['bs']
                r['num_clients'] = b['c']
                r['max_async'] = b['ma']
                r['nworker'] = r['repnworker'] = r['clinworker'] = t
                r['sb_skew_factor'] = s
                r['sb_prob_choose_mtx'] = m
                r['run_id'] = f'E_{name}_t{t}_skew{s}_mtx{m}_r{rep}'
                rows.append(r)

    with open('stage_e.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{n} configs x {REPS} reps = {len(rows)} runs -> stage_e.csv')
    print(f'   {len(BASELINES)} baselines x 8 variants each')


if __name__ == '__main__':
    main()
