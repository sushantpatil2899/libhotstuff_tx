#!/usr/bin/env python3
"""Stage MI: block size or client count -- what decides the second rotation?

FAILURE_ANALYSIS.md 7 recorded that a leader failure costs one impeachment
timeout at B1 and B2 and two at B3 and B4. Measured from the Stage L logs
(40 leader-failure runs), the reason is what the first new leader does:

  B1 (block 200, 2 clients)    kept going in 6 of 10 runs
  B2 (block 800, 4 clients)    kept going in 7 of 10
  B3 (block 1,600, 8 clients)  kept going in 0 of 10
  B4 (block 3,200, 8 clients)  kept going in 0 of 10

When it keeps going there is no second rotation and no second outage. When
it stalls it proposes a median of 8-11 blocks, commits stop within ~10 ms
of the hand-over, and it is impeached one timeout later.

B1 and B2 differ from B3 and B4 in **both** block size and client count, so
no existing sweep can say which decides it. This one crosses them, at a
fixed 8,000 requests in flight:

  bs200  c2  ma1000   2,000 in flight   B1 as measured (control)
  bs200  c8  ma1000   8,000             small blocks, many clients
  bs1600 c2  ma4000   8,000             large blocks, few clients
  bs3200 c8  ma4000  32,000             B4 as measured (control)

Stated before running, so the result can refute it:

  P5  If block size decides, the first new leader keeps going in bs200 c8
      (like B1) and stalls in bs1600 c2 (like B3/B4). If client count
      decides, the opposite. If both cells behave alike, neither does on
      its own.

No diagnostic build: this uses the protocol log that every failure sweep
already produces. Leader crash only -- crash and freeze were
indistinguishable in Stages L and LT. Default 11 s impeachment timeout,
where the one-timeout and two-timeout cases separate most clearly.
4 cells x 4 reps = 16 runs.
"""
import csv
import random

import make_stage_l_csv as L

CELLS = {
    'bs200c2': dict(bs=200, c=2, ma=1000),
    'bs200c8': dict(bs=200, c=8, ma=1000),
    'bs1600c2': dict(bs=1600, c=2, ma=4000),
    'bs3200c8': dict(bs=3200, c=8, ma=4000),
}
REPS = 4
SEED = 79


def main():
    rng = random.Random(SEED)
    rows = []
    for rep in range(1, REPS + 1):
        order = list(CELLS.items())
        rng.shuffle(order)
        for name, p in order:
            assert p['c'] * p['ma'] >= 5 * p['bs'], name
            rows.append(dict(L.FIXED, block_size=p['bs'], num_clients=p['c'],
                             max_async=p['ma'], fail_node=0, fail_type='crash',
                             run_id=f'MI_{name}_r{rep}'))
    with open('stage_mi.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=L.FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'{len(CELLS)} cells x {REPS} reps = {len(rows)} runs -> stage_mi.csv')


if __name__ == '__main__':
    main()
