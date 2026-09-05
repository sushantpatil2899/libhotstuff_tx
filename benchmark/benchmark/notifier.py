"""Email notifier for the CloudLab benchmark runner.

Reads SMTP credentials from a JSON config file (default
``~/.hotstuff_notifier.json``) and sends notifications via Gmail SMTP
(or any SMTP server). Designed to never crash the experiment if email
fails — every send error is logged and swallowed.

Throttling: callers may pass a ``throttle_key`` so repeated events of the
same kind (e.g. ``run_failure``) only emit one email per
``throttle_seconds`` window. The first occurrence always sends.
"""
from __future__ import annotations

import json
import os
import smtplib
import socket
import ssl
import time
from email.message import EmailMessage
from typing import Optional


DEFAULT_CONFIG_PATH = os.path.expanduser('~/.hotstuff_notifier.json')
REQUIRED_FIELDS = ('smtp_host', 'smtp_port', 'smtp_user',
                   'smtp_password', 'to_address')


class EmailNotifier:
    """Sends email notifications. Becomes a no-op if config is missing."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.environ.get(
            'HOTSTUFF_NOTIFIER_CONFIG', DEFAULT_CONFIG_PATH
        )
        self.config = self._load_config(self.config_path)
        self.enabled = self.config is not None
        self.throttle_seconds = (
            self.config.get('throttle_seconds', 600) if self.enabled else 0
        )
        self._last_sent: dict[str, float] = {}
        self._hostname = socket.gethostname()

        if self.enabled:
            print(f'[notifier] enabled, sending to {self.config["to_address"]} '
                  f'via {self.config["smtp_host"]}:{self.config["smtp_port"]} '
                  f'(throttle {self.throttle_seconds}s)')
        else:
            print(f'[notifier] disabled — config not found at {self.config_path}. '
                  f'See benchmark/notifier.example.json for the format.')

    @staticmethod
    def _load_config(path: str) -> Optional[dict]:
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f'[notifier] failed to read {path}: {e}')
            return None
        missing = [f for f in REQUIRED_FIELDS if f not in cfg]
        if missing:
            print(f'[notifier] config {path} missing fields: {missing}')
            return None
        return cfg

    def notify(self, subject: str, body: str,
               throttle_key: Optional[str] = None) -> bool:
        """Send an email. Returns True if sent, False if throttled or disabled."""
        if not self.enabled:
            return False

        if throttle_key is not None:
            now = time.monotonic()
            last = self._last_sent.get(throttle_key, 0.0)
            if now - last < self.throttle_seconds:
                return False
            self._last_sent[throttle_key] = now

        msg = EmailMessage()
        msg['Subject'] = f'[libhotstuff/{self._hostname}] {subject}'
        msg['From'] = self.config['smtp_user']
        msg['To'] = self.config['to_address']
        msg.set_content(body)

        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(self.config['smtp_host'],
                              int(self.config['smtp_port']),
                              timeout=30) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.ehlo()
                s.login(self.config['smtp_user'],
                        self.config['smtp_password'])
                s.send_message(msg)
            print(f'[notifier] sent: {subject}')
            return True
        except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
            # Never let email failures kill the experiment.
            print(f'[notifier] send failed for "{subject}": {e}')
            return False
