"""libhotstuff log parser.

Reads the per-client stderr logs that ``hotstuff-client`` emits when
the binary is built with ``-DHOTSTUFF_ENABLE_BENCHMARK=ON``. Each
committed command produces one line of the form::

    YYYY-MM-DD HH:MM:SS.uuuuuu [hotstuff info] <latency_seconds>

(see ``examples/hotstuff_client.cpp`` and ``scripts/thr_hist.py`` —
the latter is the upstream reference parser this one is modelled on).

Metrics produced:

  - tps:                 commits per second, aggregated across clients.
                         Numerator is total committed commands, denominator
                         is the union wall-clock window (max client
                         timestamp - min client timestamp) so it accounts
                         for natural startup skew between tmux launches.
  - latency_ms_mean:     arithmetic mean of per-command latencies (ms).
  - latency_ms_p50/p95/p99: order statistics on per-command latencies (ms).
  - duration_s:          union window in seconds.
  - n_committed:         total committed-command count.

Replica logs are inspected only to confirm the binaries reached steady
state (``** starting the event loop...`` line). They are not used to
derive metrics — the client-side timestamps are authoritative for
end-to-end commits.
"""
from __future__ import annotations

import math
import os
import re
from datetime import datetime
from glob import glob
from statistics import mean


# Matches the per-commit line shown above. group(1) = timestamp prefix,
# group(2) = latency (seconds). The leading [^[] discards lines that
# begin with '[' (replica-app tagged log lines that may end up in the
# same stream in test scenarios).
_RE_COMMIT = re.compile(
    r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) \[hotstuff info\] '
    r'([0-9.]+)\s*$'
)

# Sanity signal from replica logs. salticidae prints this once per
# replica when its network event loop comes up. The earlier regex
# ('starting the event loop') was a guess from Narwhal and never
# matched anything libhotstuff emits.
_RE_REPLICA_BOOTED = re.compile(r'\[net info\] starting all threads')


class ParseError(Exception):
    pass


def _parse_ts(s: str) -> float:
    """``YYYY-MM-DD HH:MM:SS.uuuuuu`` -> POSIX float seconds."""
    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S.%f').timestamp()


def _percentile(sorted_values, q: float) -> float:
    """Linear-interpolation percentile (numpy default). q in [0, 100].

    Avoids a numpy dependency on the orchestrator.
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (len(sorted_values) - 1) * (q / 100.0)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(sorted_values[lo])
    frac = pos - lo
    return float(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac)


class LogParser:
    """One parser instance per run directory.

    Construct via :meth:`process`. The instance retains every parsed
    sample so callers can call :meth:`result_dict` or :meth:`result`
    without re-reading the files.
    """

    def __init__(self, client_samples, replica_booted, meta=None):
        # client_samples: list of (timestamps_sorted, latencies_sorted) per
        # client. Inside each pair the lists are sorted independently
        # (timestamps by event time, latencies for percentile math).
        self.client_samples = client_samples
        self.replica_booted = replica_booted  # int, count of replicas seen booting
        self.meta = meta or {}

    # ---------- I/O ----------

    @staticmethod
    def _read_client_log(path):
        timestamps = []
        latencies = []
        with open(path, 'r', errors='replace') as f:
            for line in f:
                m = _RE_COMMIT.search(line)
                if not m:
                    continue
                try:
                    ts = _parse_ts(m.group(1))
                    lat = float(m.group(2))
                except (ValueError, OverflowError):
                    continue
                timestamps.append(ts)
                latencies.append(lat)
        timestamps.sort()
        latencies.sort()
        return timestamps, latencies

    @staticmethod
    def _read_replica_log(path):
        with open(path, 'r', errors='replace') as f:
            for line in f:
                if _RE_REPLICA_BOOTED.search(line):
                    return True
        return False

    @classmethod
    def process(cls, directory, meta=None):
        """Parse every client + replica log under ``directory``.

        Args:
            directory: typically ``results/run_logs/<run_id>``. Must
                contain ``client-*.log`` files. Replica logs are
                optional but recommended for the sanity check.
            meta: optional dict with run-level metadata (carried through
                to ``result_dict`` for context — e.g. run_id).
        """
        if not os.path.isdir(directory):
            raise ParseError(f'log directory does not exist: {directory}')

        client_paths = sorted(glob(os.path.join(directory, 'client-*.log')))
        if not client_paths:
            raise ParseError(
                f'no client-*.log files found under {directory}'
            )

        client_samples = []
        for p in client_paths:
            client_samples.append(cls._read_client_log(p))

        total = sum(len(ts) for ts, _ in client_samples)
        if total == 0:
            raise ParseError(
                f'parsed {len(client_paths)} client log(s) under {directory} '
                'but found zero commit lines — did you build with '
                'HOTSTUFF_ENABLE_BENCHMARK=ON?'
            )

        replica_paths = sorted(glob(os.path.join(directory, 'replica-*.log')))
        booted = 0
        for p in replica_paths:
            if cls._read_replica_log(p):
                booted += 1

        return cls(client_samples, booted, meta=meta)

    # ---------- Metric helpers ----------

    def _aggregate(self):
        all_ts = []
        all_lat = []
        for ts, lat in self.client_samples:
            all_ts.extend(ts)
            all_lat.extend(lat)
        all_ts.sort()
        all_lat.sort()
        return all_ts, all_lat

    def _throughput(self, all_ts):
        n = len(all_ts)
        if n < 2:
            return 0.0, 0.0
        window = all_ts[-1] - all_ts[0]
        if window <= 0:
            return 0.0, 0.0
        return n / window, window

    # ---------- Public API ----------

    def result_dict(self):
        all_ts, all_lat = self._aggregate()
        tps, window = self._throughput(all_ts)
        lat_mean_ms = (mean(all_lat) * 1_000) if all_lat else 0.0
        return {
            'tps': round(tps, 2),
            'latency_ms_mean': round(lat_mean_ms, 3),
            'latency_ms_p50': round(_percentile(all_lat, 50) * 1_000, 3),
            'latency_ms_p95': round(_percentile(all_lat, 95) * 1_000, 3),
            'latency_ms_p99': round(_percentile(all_lat, 99) * 1_000, 3),
            'duration_s': round(window, 2),
            'n_committed': len(all_ts),
            'n_clients': len(self.client_samples),
            'n_replicas_booted': self.replica_booted,
        }

    def result(self):
        d = self.result_dict()
        run_id = self.meta.get('run_id', '?')
        return (
            '\n'
            '-----------------------------------------\n'
            f' SUMMARY (run_id={run_id}):\n'
            '-----------------------------------------\n'
            f' Clients parsed:        {d["n_clients"]}\n'
            f' Replicas seen booted:  {d["n_replicas_booted"]}\n'
            f' Commits:               {d["n_committed"]:,}\n'
            f' Window (s):            {d["duration_s"]}\n'
            '\n'
            f' Throughput (tps):      {d["tps"]:,.2f}\n'
            f' Latency mean (ms):     {d["latency_ms_mean"]}\n'
            f' Latency p50 (ms):      {d["latency_ms_p50"]}\n'
            f' Latency p95 (ms):      {d["latency_ms_p95"]}\n'
            f' Latency p99 (ms):      {d["latency_ms_p99"]}\n'
            '-----------------------------------------\n'
        )
