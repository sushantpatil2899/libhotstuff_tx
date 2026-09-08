#!/usr/bin/env python3
"""Generate the three CSVs for the 2026-09-08 session.

Plan (agreed):

  Phase 1 -- does block_size actually govern the batch?
      Build with proto_log=ON, vary ONLY block_size, no netem.
      Read ncmds= off the `propose` lines and compare to the configured
      value. This question is immune to logging overhead: either
      ncmds == block_size or it does not.

      Constraint: block_size must be <= max_async. The leader only
      proposes once cmd_pending_buffer reaches blk_size
      (src/hotstuff.cpp:458), and the client keeps at most max_async
      commands outstanding, so blk_size > max_async can never fill a
      block and the run stalls with zero proposals. Hence ma=8000 for
      the block-size ladder, plus one row at the bs200/ma400 operating
      point we have actually been running.

  Phase 2 -- network latency, 200ms only, no ladder.
      Same rows run twice, once per build:
        phase2_nolog.csv  with proto_log=OFF
        phase2_log.csv    with proto_log=ON
      Distinct run_id prefixes so the resume logic (which skips
      OK/DOWNLOADED run_ids) never confuses the two passes.

      Shapes, all at 200ms, node1 = fixed leader:
        baseline      0-0-0-0
        leader        0-200-0-0
        1 follower    200-0-0-0
        2 followers   200-0-200-0
        3 followers   200-0-200-200
        all four      200-200-200-200

      3 reps each: the measured noise floor is 2.35% median / 5.72%
      p90, so n=1 cannot separate a 5% effect from noise.
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
    'sb_users': 1000, 'sb_prob_choose_mtx': 0.9, 'sb_skew_factor': 0.1,
}

# Phase 2 operating point: the recommended baseline. Small blocks give
# ~280 rounds/s, i.e. many propose/vote pairs per run to time.
P2_BS, P2_MA = 200, 400

SHAPES = [
    ('baseline',  (0, 0, 0, 0)),
    ('leader',    (0, 200, 0, 0)),
    ('foll1',     (200, 0, 0, 0)),
    ('foll2',     (200, 0, 200, 0)),
    ('foll3',     (200, 0, 200, 200)),
    ('all4',      (200, 200, 200, 200)),
]


def row(run_id, bs, ma, lats=(0, 0, 0, 0)):
    r = dict(FIXED)
    r['run_id'] = run_id
    r['block_size'] = bs
    r['max_async'] = ma
    for i in range(4):
        r[f'lat_node{i}'] = lats[i]
    return r


def write(path, rows):
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{path}: {len(rows)} rows')


def main():
    # ---- Phase 1: block_size ladder, proto_log=ON ----
    p1 = [
        row('P1_bs200_ma8000', 200, 8000),
        row('P1_bs800_ma8000', 800, 8000),
        row('P1_bs3200_ma8000', 3200, 8000),
        row('P1_bs200_ma400', 200, 400),   # the operating point we run
    ]
    write('phase1_batchsize.csv', p1)

    # ---- Phase 2: same rows, two builds, distinct run_id prefixes ----
    for prefix, path in (('P2N', 'phase2_nolog.csv'),
                         ('P2L', 'phase2_log.csv')):
        rows = []
        for tag, lats in SHAPES:
            for rep in (1, 2, 3):
                rows.append(row(f'{prefix}_{tag}_r{rep}', P2_BS, P2_MA, lats))
        write(path, rows)


if __name__ == '__main__':
    main()
