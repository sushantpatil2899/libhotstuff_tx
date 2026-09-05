"""Promote DOWNLOADED rows in the experiment CSV to OK using metrics.json
written by the parser daemon.

Lives in its own module (not in ``remote.py``) so the parser daemon can
import it without pulling fabric/paramiko. Pure CSV + filesystem; no
network.

Locking: shares an flock-based sidecar lock with the experiment loop's
per-row appender (``benchmark.csv_writer.append_row``) so we never swap
the CSV inode out from under an in-flight append.
"""
from __future__ import annotations

import csv
import json
import os

from benchmark.csv_writer import csv_lock


def reconcile_csv(csv_path: str,
                  run_logs_dir: str = 'results/run_logs') -> int:
    """Walk ``run_logs_dir``, fold metrics.json / PARSE_ERROR into csv_path rows.

    Updates each row that matches a run_log subdir's name (run_id):
      - subdir has metrics.json AND row.status != 'OK' -> set status='OK',
        copy metric fields into the row.
      - subdir has PARSE_ERROR AND row.status not in ('OK','PARSE_ERROR') ->
        set status='PARSE_ERROR: <first line>'.

    The CSV is rewritten atomically (temp + ``os.replace``) under an
    exclusive flock on the sidecar lock file. Idempotent: running twice
    in a row makes no changes the second time.

    Returns the number of rows upgraded.
    """
    if not os.path.exists(csv_path):
        return 0

    with csv_lock(csv_path):
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        if not rows:
            return 0

        rows_by_id = {r.get('run_id', ''): r for r in rows if r.get('run_id')}

        if not os.path.isdir(run_logs_dir):
            return 0

        upgraded = 0
        for entry in sorted(os.listdir(run_logs_dir)):
            run_dir = os.path.join(run_logs_dir, entry)
            if not os.path.isdir(run_dir):
                continue
            row = rows_by_id.get(entry)
            if row is None:
                continue
            metrics_path = os.path.join(run_dir, 'metrics.json')
            error_path = os.path.join(run_dir, 'PARSE_ERROR')
            if os.path.exists(metrics_path) and row.get('status') != 'OK':
                try:
                    with open(metrics_path) as mf:
                        metrics = json.load(mf)
                except (OSError, json.JSONDecodeError):
                    continue
                for k, v in metrics.items():
                    if k in fieldnames:
                        row[k] = v
                row['status'] = 'OK'
                upgraded += 1
            elif os.path.exists(error_path):
                status = row.get('status', '') or ''
                if status == 'OK' or status.startswith('PARSE_ERROR'):
                    continue
                try:
                    with open(error_path) as ef:
                        err_text = ef.read().strip().splitlines()[0][:200]
                except OSError:
                    err_text = 'unknown'
                row['status'] = f'PARSE_ERROR: {err_text}'
                upgraded += 1

        if upgraded == 0:
            return 0

        tmp_path = csv_path + '.tmp'
        with open(tmp_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        os.replace(tmp_path, csv_path)
        return upgraded
