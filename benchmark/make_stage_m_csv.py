#!/usr/bin/env python3
"""Stage M: what the 0.45 ms between quorum and QC is (FAILURE_ANALYSIS.md 14).

Stage L found that on the leader, the step from the 2f+1'th vote of a block
to the "got QC" line takes 0.49 ms at B2 with four replicas and 0.02 ms
with three, while B1, B3 and B4 take 0.02-0.03 ms always. Protocol logging
is on for the whole sweep, so that step is measurable per block.

Four arms, none of them combined in one run:

  map      11 configurations, each with follower 3 killed at t=40 s, so one
           run gives the four-replica and the three-replica figure for the
           same configuration. Block size, client count and max_async are
           varied around B2 to find where the delay appears. B1, B3 and B4
           are included as the configurations known not to have it.

  workers  B2 with repnworker 1, 2 and 8 against its usual 4 (no failure).
           If the delay is work queued behind the replicas' worker threads,
           their number should move it.

  burst    B2 with repburst 100 and 10,000 against its usual 1,000 (no
           failure), the other knob on how the replicas drain messages.

  load     B4 at max_async 3,600 and B1 at 900 (no failure), which put
           28,800 and 1,800 requests in flight -- what a leader failure
           leaves in those two baselines after losing one block
           (FAILURE_ANALYSIS.md 13). These say what a healthy four-replica
           system does at exactly that reduced load, which is what
           separates "the clients offer less work" from "the system is
           slower" in the leader-failure figures.

Runs are 120 s with a 10 s warm-up and a 2 s cool-down, matching Stage L,
so the numbers are directly comparable. Cells respect
clients x max_async >= 5 x block_size (BASELINE_ANALYSIS.md 6). No
expected outcome is recorded.
"""
import csv
import random

FIELDS = ['run_id', 'nodes', 'num_clients', 'iter_count', 'max_async',
          'duration', 'meas_warmup', 'meas_cooldown', 'sample_compute',
          'collocate_client', 'block_size', 'pace_maker', 'nworker',
          'repnworker', 'clinworker', 'repburst', 'cliburst', 'sb_users',
          'sb_prob_choose_mtx', 'sb_skew_factor', 'lat_node0', 'lat_node1',
          'lat_node2', 'lat_node3', 'fail_node', 'fail_type', 'fail_at']
FIXED = {'nodes': 4, 'iter_count': -1, 'duration': 120, 'meas_warmup': 10,
         'meas_cooldown': 2, 'sample_compute': 'true',
         'collocate_client': 'false', 'pace_maker': 'rr', 'nworker': 4,
         'repnworker': 4, 'clinworker': 4, 'repburst': 1000,
         'cliburst': 1000, 'sb_users': 10**6, 'sb_prob_choose_mtx': '0.9',
         'sb_skew_factor': '0.1', 'lat_node0': 0, 'lat_node1': 0,
         'lat_node2': 0, 'lat_node3': 0, 'fail_at': 40}

# name: block_size, clients, max_async. In flight = clients x max_async.
MAP = {
    'bs200c2':   (200, 2, 1000),      # B1        2,000 in flight
    'bs400c2':   (400, 2, 1000),      #           2,000
    'bs400c4':   (400, 4, 1000),      #           4,000
    'bs400c8':   (400, 8, 1000),      #           8,000
    'bs800c4':   (800, 4, 1000),      # B2        4,000
    'bs800c8':   (800, 8, 1000),      #           8,000
    'bs800c4ma2': (800, 4, 2000),     #           8,000
    'bs800c4ma4': (800, 4, 4000),     #          16,000
    'bs1600c8':  (1600, 8, 1000),     # B3        8,000
    'bs1600c8ma2': (1600, 8, 2000),   #          16,000
    'bs3200c8ma4': (3200, 8, 4000),   # B4       32,000
}
WORKERS = [1, 2, 8]                   # B2, against its usual 4
BURSTS = [100, 10000]                 # B2, against its usual 1,000
LOAD = {'B4ma3600': (3200, 8, 3600),  #          28,800 in flight
        'B1ma900': (200, 2, 900)}     #           1,800
REPS = 3
SEED = 53


def main():
    cfgs = []
    for name, (bs, c, ma) in MAP.items():
        cfgs.append((f'map_{name}', dict(block_size=bs, num_clients=c,
                                         max_async=ma, fail_node=3,
                                         fail_type='crash')))
    for w in WORKERS:
        cfgs.append((f'workers_w{w}', dict(block_size=800, num_clients=4,
                                           max_async=1000, repnworker=w,
                                           fail_node=-1, fail_type='')))
    for b in BURSTS:
        cfgs.append((f'burst_b{b}', dict(block_size=800, num_clients=4,
                                         max_async=1000, repburst=b,
                                         fail_node=-1, fail_type='')))
    for name, (bs, c, ma) in LOAD.items():
        cfgs.append((f'load_{name}', dict(block_size=bs, num_clients=c,
                                          max_async=ma, fail_node=-1,
                                          fail_type='')))
    for name, p in cfgs:
        assert p['num_clients'] * p['max_async'] >= 5 * p['block_size'], name

    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(cfgs)
        rng.shuffle(order)
        for name, p in order:
            rows.append(dict(FIXED, **p, run_id=f'M_{name}_r{rep}'))
    with open('stage_m.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(cfgs)} configs x {REPS} reps = {len(rows)} runs -> stage_m.csv')


if __name__ == '__main__':
    main()
