#!/usr/bin/env python3
"""Stage U: how much compute B3 uses, unrestricted.

B3 = block_size 1600, 8 clients, max_async 1000, threads 4, 90% writes,
skew 0.1, fixed proposer (replica 1), no delay. B3 never stalled in any
stage and its runs agree within 0.9%.

  sampled  5 runs with compute_sampler.py on all 4 replicas and the
           client host (sample_compute=true)
  plain    5 runs without it, interleaved, to check the sampler does not
           change throughput

60 s runs, fixed window (meas_warmup 10 s, meas_cooldown 2 s).
10 runs. No expected outcome is recorded.
"""
import csv

FIELDS = ['run_id', 'nodes', 'num_clients', 'iter_count', 'max_async',
          'duration', 'meas_warmup', 'meas_cooldown', 'sample_compute',
          'collocate_client', 'block_size', 'pace_maker', 'nworker',
          'repnworker', 'clinworker', 'repburst', 'cliburst', 'sb_users',
          'sb_prob_choose_mtx', 'sb_skew_factor', 'lat_node0', 'lat_node1',
          'lat_node2', 'lat_node3']
FIXED = {'nodes': 4, 'num_clients': 8, 'iter_count': -1, 'max_async': 1000,
         'duration': 60, 'meas_warmup': 10, 'meas_cooldown': 2,
         'collocate_client': 'false', 'block_size': 1600,
         'pace_maker': 'dummy', 'nworker': 4, 'repnworker': 4,
         'clinworker': 4, 'repburst': 1000, 'cliburst': 1000,
         'sb_users': 10**6, 'sb_prob_choose_mtx': '0.9',
         'sb_skew_factor': '0.1', 'lat_node0': 0, 'lat_node1': 0,
         'lat_node2': 0, 'lat_node3': 0}


def main():
    rows = []
    for rep in range(1, 6):
        for label, flag in (('sampled', 'true'), ('plain', 'false')):
            order = (label, flag)
            r = dict(FIXED, sample_compute=order[1],
                     run_id=f'U_{order[0]}_r{rep}')
            rows.append(r)
    # alternate which comes first each pass
    for i in range(0, len(rows), 4):
        rows[i:i + 2] = rows[i:i + 2][::-1]
    with open('stage_u.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(rows)} runs -> stage_u.csv:', [r['run_id'] for r in rows])


if __name__ == '__main__':
    main()
