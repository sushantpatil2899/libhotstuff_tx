"""Async log-parsing daemon for the CSV-driven CloudLab benchmark.

The benchmark runner (``run_from_csv``) writes raw logs into
``results/run_logs/<run_id>/`` and touches a ``READY`` marker when the
dir is complete. This daemon polls that tree and parses any READY dir
using ``LogParser``, writing the metric dict to ``metrics.json``. The
runner's reconciler then promotes ``DOWNLOADED`` rows to ``OK`` and fills
the metric columns.

Decoupling parsing from the run loop hides multi-minute parse latency on
large runs — the next benchmark can start immediately after logs are
downloaded instead of blocking on a serial parse.

Usage (in a separate ``screen`` window on the orchestrator)::

    cd ~/libhotstuff/benchmark
    python3 -m benchmark.parser_daemon \\
        --run-logs-dir results/run_logs \\
        --csv-path results/final_results.csv \\
        --poll-interval 10
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import traceback

from benchmark.logs import LogParser, ParseError


READY_MARKER = 'READY'
METRICS_FILE = 'metrics.json'
ERROR_MARKER = 'PARSE_ERROR'
META_FILE = 'meta.json'
RESULT_FILE = 'result.txt'


_running = True
_main_pid = os.getpid()


def _reset_signals_in_child():
    """Reset signal handlers to SIG_DFL in forked pool workers.

    Pool workers inherit SIGINT/SIGTERM/SIGHUP handlers from the parent.
    Resetting to SIG_DFL lets the kernel terminate them cleanly instead
    of either ignoring the signal (deadlock) or skipping queue cleanup
    (semaphore leak).
    """
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, signal.SIG_DFL)


def _handle_signal(signum, frame):
    global _running
    print(f'[parser-daemon] caught signal {signum}, shutting down after this pass')
    _running = False


os.register_at_fork(after_in_child=_reset_signals_in_child)


def _atomic_write(path, content):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(content)
    os.replace(tmp, path)


def _process_dir(run_dir):
    """Parse one READY run dir. Returns 'ok', 'error', or 'skip'."""
    ready_path = os.path.join(run_dir, READY_MARKER)
    metrics_path = os.path.join(run_dir, METRICS_FILE)
    error_path = os.path.join(run_dir, ERROR_MARKER)
    meta_path = os.path.join(run_dir, META_FILE)

    if not os.path.exists(ready_path):
        return 'skip'
    if os.path.exists(metrics_path) or os.path.exists(error_path):
        try:
            os.remove(ready_path)
        except OSError:
            pass
        return 'skip'

    meta = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError):
            meta = {}

    print(f'[parser-daemon] parsing {run_dir}')
    t0 = time.time()
    try:
        logger = LogParser.process(run_dir, meta=meta)
        metrics = logger.result_dict()
        _atomic_write(metrics_path, json.dumps(metrics, indent=2))
        try:
            _atomic_write(os.path.join(run_dir, RESULT_FILE), logger.result())
        except Exception as txt_err:
            print(f'[parser-daemon] (warn) failed to write result.txt for '
                  f'{run_dir}: {txt_err}')
        os.remove(ready_path)
        dt = time.time() - t0
        print(f'[parser-daemon] OK {run_dir} in {dt:.1f}s — '
              f'tps={metrics.get("tps")} '
              f'lat={metrics.get("latency_ms_mean")}ms')
        return 'ok'
    except (ParseError, OSError, ValueError, IndexError, AttributeError,
            AssertionError, KeyError) as e:
        tb = traceback.format_exc()
        try:
            _atomic_write(error_path, f'{type(e).__name__}: {e}\n\n{tb}')
        except OSError:
            pass
        try:
            os.remove(ready_path)
        except OSError:
            pass
        print(f'[parser-daemon] FAIL {run_dir}: {type(e).__name__}: {e}')
        return 'error'


def _reconcile_if_possible(csv_path, run_logs_dir):
    """Best-effort call to the reconciler. Never raises."""
    if not csv_path or not os.path.exists(csv_path):
        return
    try:
        from benchmark.reconciler import reconcile_csv
        n = reconcile_csv(csv_path, run_logs_dir=run_logs_dir)
        if n:
            print(f'[parser-daemon] reconciled {n} row(s) into {csv_path}')
    except Exception as e:
        print(f'[parser-daemon] (warn) reconcile failed: {e}')


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Async log parser for the CloudLab benchmark.'
    )
    parser.add_argument('--run-logs-dir', default='results/run_logs',
                        help='Directory holding per-run log subdirs '
                             '(default: results/run_logs)')
    parser.add_argument('--csv-path', default='results/final_results.csv',
                        help='Path to the final_results CSV. Reconciled '
                             'after each batch of parses '
                             '(default: results/final_results.csv)')
    parser.add_argument('--poll-interval', type=int, default=10,
                        help='Seconds between scans (default: 10)')
    parser.add_argument('--once', action='store_true',
                        help='Single pass and exit (for testing)')
    args = parser.parse_args(argv)

    global _main_pid
    _main_pid = os.getpid()
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, _handle_signal)

    print(f'[parser-daemon] watching {args.run_logs_dir}, '
          f'polling every {args.poll_interval}s, '
          f'reconciling {args.csv_path} after each batch')

    while _running:
        parsed_any = False
        if os.path.isdir(args.run_logs_dir):
            for entry in sorted(os.listdir(args.run_logs_dir)):
                if not _running:
                    break
                run_dir = os.path.join(args.run_logs_dir, entry)
                if not os.path.isdir(run_dir):
                    continue
                outcome = _process_dir(run_dir)
                if outcome in ('ok', 'error'):
                    parsed_any = True

        if parsed_any:
            _reconcile_if_possible(args.csv_path, args.run_logs_dir)

        if args.once:
            break

        slept = 0
        while _running and slept < args.poll_interval:
            time.sleep(1)
            slept += 1

    print('[parser-daemon] exited')


if __name__ == '__main__':
    sys.exit(main())
