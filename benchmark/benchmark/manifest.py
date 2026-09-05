"""CloudLab GENI rspec manifest parser.

Extracts per-node (private_ip, public_hostname) pairs from a manifest.xml
downloaded from the CloudLab portal (Experiment -> Manifest tab).

Detects multi-site experiments automatically from the
``component_manager_id`` attribute on each ``<node>``. Multi-site setups
must fall back to public hostnames for protocol traffic because private
LAN IPs are not routable across CloudLab aggregates.
"""
import xml.etree.ElementTree as ET

from benchmark.utils import Print


class ManifestError(Exception):
    pass


class Manifest:
    GENI_NS = 'http://www.geni.net/resources/rspec/3'

    def __init__(self, hosts, hostnames, multi_site):
        assert len(hosts) == len(hostnames) and len(hosts) > 0
        self.hosts = hosts            # private IPs (experiment LAN)
        self.hostnames = hostnames    # SSH-reachable public hostnames
        self.multi_site = multi_site  # auto-detected from component_manager_id

    @classmethod
    def load(cls, filename='manifest.xml'):
        try:
            tree = ET.parse(filename)
        except ET.ParseError as e:
            raise ManifestError(f'Failed to parse {filename}: {e}')
        except OSError as e:
            raise ManifestError(str(e))

        root = tree.getroot()
        ns = {'g': cls.GENI_NS}

        hosts, hostnames, sites = [], [], []

        for node in root.findall('g:node', ns):
            # Private IP from the experiment LAN interface.
            private_ip = None
            for iface in node.findall('g:interface', ns):
                for ip_el in iface.findall('g:ip', ns):
                    if ip_el.get('type') == 'ipv4':
                        private_ip = ip_el.get('address')
                        break
                if private_ip:
                    break

            # Public SSH hostname.
            hostname = None
            services = node.find('g:services', ns)
            if services is not None:
                login = services.find('g:login', ns)
                if login is not None:
                    hostname = login.get('hostname')

            site = node.get('component_manager_id', '')

            if private_ip and hostname:
                hosts.append(private_ip)
                hostnames.append(hostname)
                sites.append(site)

        if not hosts:
            raise ManifestError(
                f'No usable nodes found in {filename}. '
                'Each node needs an IPv4 interface address and a login hostname.'
            )

        unique_sites = {s for s in sites if s}
        multi_site = len(unique_sites) > 1
        if multi_site:
            Print.warn(
                f'Multi-site experiment detected across {len(unique_sites)} '
                'sites — public hostnames will be used for protocol config'
            )

        return cls(hosts, hostnames, multi_site)
