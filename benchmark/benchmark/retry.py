"""Retry decorator for SSH-flaky operations.

Catches the transient network exceptions we have actually observed
(paramiko ``SSHException`` / ``OSError`` from broken sockets, EOF during
SFTP, and Fabric ``GroupException`` wrapping per-host SSH failures) and
re-tries with backoff. All other exceptions propagate immediately so
genuine bugs aren't masked.
"""
from __future__ import annotations

import functools
import socket
import time
from typing import Callable, Iterable, Optional

from fabric.exceptions import GroupException
from paramiko.ssh_exception import SSHException


TRANSIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    SSHException,
    GroupException,
    socket.error,   # alias of OSError on modern Python
    EOFError,
)


def retry_on_ssh_error(
    attempts: int = 3,
    backoff_seconds: Iterable[float] = (30, 60, 120),
    on_retry: Optional[Callable[[int, BaseException], None]] = None,
):
    """Decorate a method so transient SSH errors trigger retry with backoff.

    Args:
        attempts: total tries including the first (so ``attempts=3`` =
            initial + 2 retries).
        backoff_seconds: delays between retries. Length must be at least
            ``attempts - 1``; extras are ignored.
        on_retry: optional callback invoked as ``on_retry(attempt_no,
            exception)`` after each failure (before sleeping). Useful for
            notification hooks.
    """
    backoffs = tuple(backoff_seconds)
    if attempts < 1:
        raise ValueError('attempts must be >= 1')
    if len(backoffs) < attempts - 1:
        raise ValueError(
            f'backoff_seconds has {len(backoffs)} entries but '
            f'{attempts - 1} are needed for {attempts} attempts'
        )

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: Optional[BaseException] = None
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except TRANSIENT_EXCEPTIONS as e:
                    last_exc = e
                    if on_retry is not None:
                        try:
                            on_retry(attempt, e)
                        except Exception as cb_err:
                            print(f'[retry] on_retry callback raised: {cb_err}')
                    if attempt == attempts:
                        break
                    delay = backoffs[attempt - 1]
                    print(
                        f'[retry] {fn.__name__} attempt {attempt}/{attempts} '
                        f'failed with {type(e).__name__}: {e}. '
                        f'Sleeping {delay}s before retry.'
                    )
                    time.sleep(delay)
            assert last_exc is not None
            raise last_exc
        return wrapper
    return decorator
