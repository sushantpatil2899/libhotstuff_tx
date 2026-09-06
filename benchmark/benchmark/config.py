"""Parameter schemas + config-generation helpers for the libhotstuff
harness.

Two dataclass-like wrappers:

  - ``BenchParameters`` captures everything that controls *how* a run is
    executed (replica count, client count, duration). These come from
    fixed defaults in fabfile.py plus per-row CSV columns.
  - ``ProtocolParameters`` captures every value written into
    ``hotstuff.conf`` via ``gen_conf.py``. Each field maps 1:1 to a CLI
    flag on ``hotstuff-app``.

The split keeps the conf-file generator (``gen_conf.py``) decoupled from
the orchestration loop: the loop knows about replica counts and
durations; the generator only knows about protocol parameters.
"""
from benchmark.utils import PathMaker


class ConfigError(Exception):
    pass


def _require(cond, msg):
    if not cond:
        raise ConfigError(msg)


def _parse_bool(value):
    """Parse a bool that may arrive as an actual bool (code default) or as
    a CSV-cell string ('true'/'false'/'1'/'0'/...).

    ``bool(raw.get('x', True))`` is a trap here: every non-empty CSV
    string — including the literal text ``"False"`` — is truthy in
    Python, so a CSV author writing ``collocate_client=False`` would
    silently get ``True``. This treats a small set of case-insensitive
    tokens as false and everything else (including real bools) via
    ``bool()``.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ('false', '0', 'no', '')
    return bool(value)


class BenchParameters:
    """How the experiment is *run*.

    Fields:
        nodes (int):        replica count for this experiment.
        num_clients (int):  number of ``hotstuff-client`` processes to
                            launch. Independent of the replica count;
                            placement is decided by remote.py.
        iter_count (int):   ``--iter`` value passed to each client. ``-1``
                            = run forever (kill on duration).
        max_async (int):    ``--max-async`` value per client.
        duration (int):     seconds the harness lets the run execute
                            before killing tmux.
        runs (int):         number of repeats of this row. Median is
                            generally what you report.
        collocate_client (bool):
                            if True, run one client on each replica host.
                            If False, clients land on dedicated non-replica
                            nodes from the manifest (extras after the
                            first ``nodes``).
    """

    REQUIRED = (
        'nodes', 'num_clients', 'iter_count', 'max_async', 'duration',
    )

    def __init__(self, raw):
        try:
            for k in self.REQUIRED:
                _require(k in raw, f'missing bench param: {k}')
            self.nodes = int(raw['nodes'])
            self.num_clients = int(raw['num_clients'])
            self.iter_count = int(raw['iter_count'])
            self.max_async = int(raw['max_async'])
            self.duration = int(raw['duration'])
            self.runs = int(raw.get('runs', 1))
            self.collocate_client = _parse_bool(raw.get('collocate_client', True))
        except (TypeError, ValueError) as e:
            raise ConfigError(f'bench param type error: {e}')

        _require(self.nodes >= 4, 'nodes must be >= 4 (BFT threshold)')
        _require(self.num_clients >= 1, 'num_clients must be >= 1')
        _require(self.max_async >= 1, 'max_async must be >= 1')
        _require(self.duration >= 1, 'duration must be >= 1')
        _require(self.runs >= 1, 'runs must be >= 1')


class ProtocolParameters:
    """What gets written into ``hotstuff.conf`` via ``gen_conf.py``.

    Every field maps to a ``gen_conf.py`` flag (which in turn becomes a
    line in the generated conf). Fields default to values that match
    libhotstuff's own benchmark configuration (``scripts/deploy``) so
    that omitting a column in the CSV yields a sensible run.
    """

    def __init__(self, raw):
        try:
            self.block_size = int(raw.get('block_size', 400))
            self.pace_maker = str(raw.get('pace_maker', 'rr'))
            self.nworker = int(raw.get('nworker', 4))
            self.repnworker = int(raw.get('repnworker', 4))
            self.clinworker = int(raw.get('clinworker', 4))
            self.repburst = int(raw.get('repburst', 1000))
            self.cliburst = int(raw.get('cliburst', 1000))
            self.max_rep_msg = int(raw.get('max_rep_msg', 4 << 20))  # 4 MiB
            self.max_cli_msg = int(raw.get('max_cli_msg', 65536))     # 64 KiB
            self.pport = int(raw.get('pport', 10000))
            self.cport = int(raw.get('cport', 20000))
            # SmallBank workload parameters. Defaults match this fork's own
            # gen_conf.py defaults except sb_users, which we deliberately
            # raise from the upstream default of 20 to 1000 — a keyspace
            # that small makes contention driven by the tiny account pool
            # rather than by sb_skew_factor, the knob actually meant to
            # control it.
            self.sb_users = int(raw.get('sb_users', 1000))
            self.sb_prob_choose_mtx = float(raw.get('sb_prob_choose_mtx', 0.9))
            self.sb_skew_factor = float(raw.get('sb_skew_factor', 0.1))
        except (TypeError, ValueError) as e:
            raise ConfigError(f'protocol param type error: {e}')

        _require(self.block_size >= 1, 'block_size must be >= 1')
        _require(self.pace_maker in ('rr', 'dummy'),
                 'pace_maker must be "rr" or "dummy"')
        for name in ('nworker', 'repnworker', 'clinworker',
                     'repburst', 'cliburst',
                     'max_rep_msg', 'max_cli_msg'):
            _require(getattr(self, name) >= 1, f'{name} must be >= 1')
        _require(self.sb_users >= 1, 'sb_users must be >= 1')
        _require(0.0 <= self.sb_prob_choose_mtx <= 1.0,
                 'sb_prob_choose_mtx must be in [0, 1]')
        _require(self.sb_skew_factor >= 0.0, 'sb_skew_factor must be >= 0')

    def gen_conf_kwargs(self, *, ips_file, prefix=None):
        """Build the kwargs dict for ``CommandMaker.gen_conf``."""
        return {
            'ips_file': ips_file,
            'prefix': prefix or PathMaker.conf_prefix(),
            'block_size': self.block_size,
            'pace_maker': self.pace_maker,
            'nworker': self.nworker,
            'repnworker': self.repnworker,
            'clinworker': self.clinworker,
            'repburst': self.repburst,
            'cliburst': self.cliburst,
            'pport': self.pport,
            'cport': self.cport,
            'sb_users': self.sb_users,
            'sb_prob_choose_mtx': self.sb_prob_choose_mtx,
            'sb_skew_factor': self.sb_skew_factor,
        }


class NetworkParameters:
    """Per-replica artificial network latency (ms), injected via `tc`
    on the orchestrator side -- these values never touch hotstuff.conf
    or the application at all, so they live in their own class rather
    than ProtocolParameters.

    ``lat_nodeN`` (N in 0..3) is that replica's own assigned latency.
    The *link* between any two replicas gets max(lat_a, lat_b),
    applied identically on both ends (see benchmark/netem.py) --
    0 means unrestricted, and a row that sets no lat_node* columns is
    a plain no-latency run.
    """

    def __init__(self, raw):
        try:
            self.node_latencies = {
                i: int(raw.get(f'lat_node{i}', 0)) for i in range(4)
            }
        except (TypeError, ValueError) as e:
            raise ConfigError(f'network param type error: {e}')
        for i, v in self.node_latencies.items():
            _require(v >= 0, f'lat_node{i} must be >= 0')

    @property
    def any_latency(self):
        return any(v > 0 for v in self.node_latencies.values())


def write_ips_file(path, ips):
    """Write a one-IP-per-line file (consumed by ``gen_conf.py --ips``).

    The order is significant — replica ``i`` in the manifest becomes
    the i-th entry in the generated ``hotstuff.conf``.
    """
    assert isinstance(ips, list) and all(isinstance(x, str) for x in ips)
    with open(path, 'w') as f:
        for ip in ips:
            f.write(ip + '\n')
