"""Lightweight settings loader for the CloudLab harness.

Reads ``settings.json``. No AWS or boto3 dependency; CloudLab nodes are
discovered from ``manifest.xml`` instead.
"""
from json import load, JSONDecodeError


class SettingsError(Exception):
    pass


class CloudLabSettings:
    def __init__(self, username, base_port, repo_name, repo_url, branch):
        ok = all(isinstance(x, str) for x in [username, repo_name, repo_url, branch])
        ok &= isinstance(base_port, int) and base_port > 1024
        if not ok:
            raise SettingsError('Invalid CloudLab settings types')

        self.cloudlab_username = username
        self.base_port = base_port
        self.repo_name = repo_name
        self.repo_url = repo_url
        self.branch = branch

    @classmethod
    def load(cls, filename='settings.json'):
        try:
            with open(filename, 'r') as f:
                data = load(f)
            return cls(
                data['cloudlab']['username'],
                data['port'],
                data['repo']['name'],
                data['repo']['url'],
                data['repo']['branch'],
            )
        except (OSError, JSONDecodeError) as e:
            raise SettingsError(str(e))
        except KeyError as e:
            raise SettingsError(f'Malformed settings: missing key {e}')
