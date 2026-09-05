"""Shared, lock-protected CSV append + reconcile primitives.

Both the experiment loop (``remote.py``) and the parser-daemon reconciler
(``reconciler.py``) write to the same CSV. The reconciler does a
read-modify-replace via ``os.replace``, which atomically swaps a NEW inode
into the path. If the experiment loop is holding a long-lived file
descriptor on the OLD inode at that moment, every subsequent write goes
to the orphaned inode and is lost when the process exits.

To eliminate that race entirely, every writer (the experiment loop's
per-row append and the reconciler's tmp+replace) acquires an exclusive
``fcntl.flock`` on a sidecar ``.lock`` file whose inode is stable (never
replaced). The lock file is created lazily and is harmless to leave on
disk: ``flock`` is advisory, dies with the holder, and the file itself
contains nothing.

Lives in its own module (no fabric/paramiko deps) so the parser daemon
can import it without pulling the network stack.
"""
from __future__ import annotations

import csv
import fcntl
import os
from contextlib import contextmanager
from typing import Iterable, Mapping


def _lock_path(csv_path: str) -> str:
    return csv_path + '.lock'


@contextmanager
def csv_lock(csv_path: str):
    """Acquire an exclusive flock on the sidecar lock file for ``csv_path``.

    Both ``append_row()`` and ``reconcile_csv()`` wrap their critical
    sections with this lock so they serialise against each other.
    """
    lp = _lock_path(csv_path)
    with open(lp, 'a') as lock_fd:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)


def append_row(csv_path: str, fieldnames: Iterable[str],
               row: Mapping[str, object]) -> None:
    """Atomically append one CSV row, writing the header if the file is
    new or zero-length.

    Holds the sidecar flock for the entire open->write->close window so
    a concurrent reconciler cannot swap the inode in between.
    """
    fieldnames = list(fieldnames)
    with csv_lock(csv_path):
        new_file = (
            not os.path.exists(csv_path)
            or os.path.getsize(csv_path) == 0
        )
        with open(csv_path, 'a', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            if new_file:
                w.writeheader()
            w.writerow(row)
