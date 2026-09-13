#!/usr/bin/env python3
"""Per-second compute counters for one host, written as JSON lines.

Runs on a replica or client host during a benchmark run, launched by
``CloudLabBench._run_single`` when a row sets ``sample_compute``. It needs
only the Python standard library and must run as root, because the RAPL
energy counter is root-readable only.

Every sample records RAW CUMULATIVE counters, never rates. Rates are
derived afterwards from differences between samples, so a late or missed
tick does not corrupt a value, only widens the interval it covers.

Recorded each second:
  procs     per process named --proc (matched on /proc/PID/comm exactly):
            utime+stime ticks, voluntary / involuntary context switches,
            RSS, allowed CPU list (process, and the distinct lists across
            its threads), and per-thread ticks with each thread's name
  host_cpu  /proc/stat aggregate cpu line (ticks by state)
  psi       /proc/pressure/cpu "some" and "full" totals (microseconds)
  energy    RAPL package energy (microjoules) and its wrap-around range
  self      this sampler's own ticks, so its overhead can be reported

Exits after --seconds, so a sampler whose kill was missed cannot outlive
the next run by much.
"""
import argparse
import json
import os
import sys
import time

CLK_TCK = os.sysconf('SC_CLK_TCK')
RAPL = '/sys/class/powercap/intel-rapl:0'


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def _stat_ticks(text):
    """utime + stime from a /proc/<pid>[/task/<tid>]/stat line.

    The comm field is parenthesised and may contain spaces, so split on
    the LAST ')'. After it, field 3 (state) is index 0, so utime (field 14)
    is index 11 and stime (field 15) index 12.
    """
    rest = text.rsplit(')', 1)[1].split()
    return int(rest[11]) + int(rest[12])


def _proc(pid):
    stat = _read(f'/proc/{pid}/stat')
    status = _read(f'/proc/{pid}/status')
    if stat is None or status is None:
        return None
    out = {'ticks': _stat_ticks(stat), 'threads': {}}
    for line in status.splitlines():
        k, _, v = line.partition(':')
        if k == 'voluntary_ctxt_switches':
            out['vcs'] = int(v)
        elif k == 'nonvoluntary_ctxt_switches':
            out['nvcs'] = int(v)
        elif k == 'VmRSS':
            out['rss_kb'] = int(v.split()[0])
        elif k == 'Cpus_allowed_list':
            out['cpus'] = v.strip()
    try:
        tids = os.listdir(f'/proc/{pid}/task')
    except OSError:
        tids = []
    thread_cpus = set()
    for tid in tids:
        t = _read(f'/proc/{pid}/task/{tid}/stat')
        comm = _read(f'/proc/{pid}/task/{tid}/comm')
        if t is not None:
            out['threads'][tid] = [(comm or '?').strip(), _stat_ticks(t)]
        ts = _read(f'/proc/{pid}/task/{tid}/status') or ''
        for line in ts.splitlines():
            if line.startswith('Cpus_allowed_list:'):
                thread_cpus.add(line.split(':', 1)[1].strip())
    # Distinct affinity lists across the process's threads: one entry when
    # every thread inherited the same mask, which is what pinning must show.
    out['thread_cpus'] = sorted(thread_cpus)
    return out


def _psi():
    text = _read('/proc/pressure/cpu') or ''
    out = {}
    for line in text.splitlines():
        kind = line.split()[0]
        total = [f for f in line.split() if f.startswith('total=')]
        if total:
            out[kind] = int(total[0].split('=')[1])
    return out


def _host_cpu():
    text = _read('/proc/stat') or ''
    first = text.splitlines()[0].split() if text else []
    return [int(x) for x in first[1:9]] if first and first[0] == 'cpu' else []


def sample(names):
    procs = {}
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        comm = _read(f'/proc/{pid}/comm')
        if comm is not None and comm.strip() in names:
            p = _proc(pid)
            if p is not None:
                p['comm'] = comm.strip()
                procs[pid] = p
    energy = _read(f'{RAPL}/energy_uj')
    erange = _read(f'{RAPL}/max_energy_range_uj')
    self_stat = _read(f'/proc/{os.getpid()}/stat')
    return {
        'wall': time.time(),
        'procs': procs,
        'host_cpu': _host_cpu(),
        'psi': _psi(),
        'energy_uj': int(energy) if energy else None,
        'energy_range_uj': int(erange) if erange else None,
        'self_ticks': _stat_ticks(self_stat) if self_stat else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--proc', action='append', required=True,
                    help='process name to track (repeatable)')
    ap.add_argument('--seconds', type=float, required=True)
    ap.add_argument('--interval', type=float, default=1.0)
    args = ap.parse_args()
    names = set(args.proc)
    print(json.dumps({'header': {'clk_tck': CLK_TCK,
                                 'ncpu': os.cpu_count(),
                                 'procs': sorted(names),
                                 'interval': args.interval}}), flush=True)
    t0 = time.monotonic()
    n = 0
    while True:
        s = sample(names)
        s['t'] = round(time.monotonic() - t0, 3)
        print(json.dumps(s, separators=(',', ':')), flush=True)
        n += 1
        if s['t'] >= args.seconds:
            break
        # Schedule against the start time, not the previous sample, so
        # slow samples do not accumulate drift.
        time.sleep(max(0.0, t0 + n * args.interval - time.monotonic()))


if __name__ == '__main__':
    sys.exit(main())
