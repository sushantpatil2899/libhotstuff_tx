#!/usr/bin/env python3
"""Stage U: compute usage of B3, unrestricted.

Reads each run's compute-*.jsonl (benchmark/compute_sampler.py) and turns
cumulative counters into rates over a steady window of the sampler
timeline: t = 15 s to 55 s. The sampler starts right after the replicas
boot; clients start about 3 s later and run for 60 s.

Per host (replica 1 is the fixed proposer):
  cores        CPU used by the tracked process(es), in cores (1.0 = one
               core busy for the whole second)
  busiest      mean utilisation of the single busiest thread, % of a core,
               and that thread's name
  busy thr     threads averaging over 5% of a core
  threads      thread count
  psi some     % of time some runnable task on the host waited for CPU
  nvcs/s       involuntary context switches per second (process)
  vcs/s        voluntary context switches per second (process)
  rss MB       resident memory (process)
  host cores   CPU used by everything on the host, in cores
  watts        RAPL package power (whole socket)
  sampler      the sampler's own CPU, in cores
Also reports package power in the first 2 s of each file, before clients
start, as a less-loaded reference.

Runs with sample_compute=false are the overhead check: their throughput is
compared with the sampled runs'.
"""
import glob
import json
import os
import re
import statistics as st
from collections import defaultdict

W0, W1 = 15.0, 55.0


def load(path):
    lines = [json.loads(l) for l in open(path) if l.strip()]
    head = lines[0]['header']
    return head, [x for x in lines[1:] if 't' in x]


def window(samples):
    inside = [s for s in samples if W0 <= s['t'] <= W1]
    return (inside[0], inside[-1]) if len(inside) >= 2 else (None, None)


def host_metrics(path):
    head, S = load(path)
    tck = head['clk_tck']
    a, b = window(S)
    if a is None:
        return None
    dt = b['t'] - a['t']
    pids = set(a['procs']) & set(b['procs'])
    cores = sum(b['procs'][p]['ticks'] - a['procs'][p]['ticks']
                for p in pids) / tck / dt
    nvcs = sum(b['procs'][p].get('nvcs', 0) - a['procs'][p].get('nvcs', 0)
               for p in pids) / dt
    vcs = sum(b['procs'][p].get('vcs', 0) - a['procs'][p].get('vcs', 0)
              for p in pids) / dt
    rss = sum(b['procs'][p].get('rss_kb', 0) for p in pids) / 1024
    threads = {}
    for p in pids:
        ta, tb = a['procs'][p]['threads'], b['procs'][p]['threads']
        for tid in set(ta) & set(tb):
            threads[(p, tid)] = (tb[tid][0],
                                 (tb[tid][1] - ta[tid][1]) / tck / dt * 100)
    busiest = max(threads.values(), key=lambda x: x[1]) if threads else ('-', 0)
    busy = sum(1 for _, pct in threads.values() if pct > 5)
    ha, hb = a['host_cpu'], b['host_cpu']
    tot = sum(hb) - sum(ha)
    idle = (hb[3] + hb[4]) - (ha[3] + ha[4])
    host_cores = (tot - idle) / tck / dt
    psi = (b['psi'].get('some', 0) - a['psi'].get('some', 0)) / (dt * 1e6) * 100

    def watts(x, y):
        if x.get('energy_uj') is None or y.get('energy_uj') is None:
            return None
        d = y['energy_uj'] - x['energy_uj']
        if d < 0:
            d += x.get('energy_range_uj') or 0
        return d / 1e6 / (y['t'] - x['t'])

    early = [s for s in S if s['t'] <= 2.5]
    return {
        'cores': cores, 'busiest_pct': busiest[1], 'busiest_name': busiest[0],
        'busy_threads': busy, 'threads': len(threads), 'psi': psi,
        'nvcs': nvcs, 'vcs': vcs, 'rss_mb': rss, 'host_cores': host_cores,
        'watts': watts(a, b),
        'watts_early': watts(early[0], early[-1]) if len(early) >= 2 else None,
        'sampler_cores': ((b['self_ticks'] or 0) - (a['self_ticks'] or 0))
        / tck / dt,
        'nprocs': len(pids),
    }


runs = defaultdict(list)          # label -> [(run_id, metrics, hosts)]
for d in sorted(glob.glob('results/run_logs/U_*')):
    rid = os.path.basename(d)
    m = re.match(r'U_(sampled|plain)_r(\d+)$', rid)
    mp = os.path.join(d, 'metrics.json')
    if not m or not os.path.exists(mp):
        continue
    hosts = {}
    for f in sorted(glob.glob(os.path.join(d, 'compute-*.jsonl'))):
        name = os.path.basename(f)[len('compute-'):-len('.jsonl')]
        hm = host_metrics(f)
        if hm:
            hosts[name] = hm
    runs[m[1]].append((rid, json.load(open(mp)), hosts))

print('=== throughput: sampled vs not sampled (overhead check) ===')
for label in ('sampled', 'plain'):
    v = runs.get(label, [])
    if not v:
        continue
    t = [x[1].get('tps_steady', 0) for x in v]
    l = [x[1].get('latency_ms_mean_steady', 0) for x in v]
    stalls = sum(bool(x[1].get('stalled')) for x in v)
    print(f'  {label:<8} n={len(v)} stalled={stalls}  tps_steady median '
          f'{st.median(t):,.0f} (range {min(t):,.0f}-{max(t):,.0f})  '
          f'latency median {st.median(l):.1f} ms')

sampled = runs.get('sampled', [])
if sampled:
    names = sorted({h for _, _, hosts in sampled for h in hosts},
                   key=lambda n: (n.startswith('client'), n))
    print('\n=== per host, median over sampled runs (window t=15-55 s) ===')
    cols = [('cores', 'cores', '{:.2f}'), ('busiest_pct', 'busiest %', '{:.0f}'),
            ('busy_threads', 'busy thr', '{:.0f}'), ('threads', 'threads', '{:.0f}'),
            ('psi', 'psi some %', '{:.2f}'), ('nvcs', 'nvcs/s', '{:,.0f}'),
            ('vcs', 'vcs/s', '{:,.0f}'), ('rss_mb', 'rss MB', '{:,.0f}'),
            ('host_cores', 'host cores', '{:.2f}'), ('watts', 'watts', '{:.1f}'),
            ('watts_early', 'W pre-client', '{:.1f}'),
            ('sampler_cores', 'sampler', '{:.3f}')]
    label = {'replica-0': 'replica 0 (follower)', 'replica-1': 'replica 1 (LEADER)',
             'replica-2': 'replica 2 (follower)', 'replica-3': 'replica 3 (follower)'}
    print(f'  {"host":<24}' + ''.join(f'{c[1]:>13}' for c in cols))
    for n in names:
        vals = [hosts[n] for _, _, hosts in sampled if n in hosts]
        row = f'  {label.get(n, n):<24}'
        for key, _, fmt in cols:
            xs = [v[key] for v in vals if v.get(key) is not None]
            row += f'{fmt.format(st.median(xs)) if xs else "-":>13}'
        print(row)
    print('\n  busiest thread names per host:')
    for n in names:
        tn = sorted({hosts[n]['busiest_name'] for _, _, hosts in sampled
                     if n in hosts})
        print(f'    {label.get(n, n):<24} {tn}')
    print('\n=== per run: cores used (leader / followers / client host) ===')
    for rid, met, hosts in sampled:
        rep = ' '.join(f'{hosts[n]["cores"]:.2f}' for n in names if n in hosts)
        print(f'  {rid:<16} tps_steady {met.get("tps_steady", 0):>9,.0f}  '
              f'cores [{rep}]')
