"""CloudLab manifest-backed instance manager.

No AWS / boto3 dependency. Node addresses come from ``manifest.xml``.
"""
from benchmark.utils import BenchError
from benchmark.settings import CloudLabSettings, SettingsError
from benchmark.manifest import Manifest, ManifestError


class CloudLabInstanceManager:
    def __init__(self, manifest, settings):
        assert isinstance(manifest, Manifest)
        assert isinstance(settings, CloudLabSettings)
        self.manifest = manifest
        self.settings = settings

    @classmethod
    def make(cls, manifest_file='manifest.xml', settings_file='settings.json'):
        try:
            manifest = Manifest.load(manifest_file)
            settings = CloudLabSettings.load(settings_file)
            return cls(manifest, settings)
        except ManifestError as e:
            raise BenchError('Failed to load CloudLab manifest', e)
        except SettingsError as e:
            raise BenchError('Failed to load CloudLab settings', e)

    def hosts(self):
        """Private/experiment-LAN IPs used for protocol traffic.

        For multi-site experiments these are not routable across sites,
        so callers should switch to ``ssh_hosts()`` (see
        ``manifest.multi_site``).
        """
        return list(self.manifest.hosts)

    def ssh_hosts(self):
        """Publicly-reachable hostnames used by Fabric ``Connection()`` calls."""
        return list(self.manifest.hostnames)
