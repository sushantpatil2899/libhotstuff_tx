"""Per-peer network latency injection via Linux `tc` (traffic control).

Each replica is assigned an integer latency in milliseconds (0 =
unrestricted). The *link* between any two replicas gets a single
effective delay = max(latency_a, latency_b), applied symmetrically: it
doesn't matter who sends, node A's traffic to node B and node B's
traffic to node A both incur the same delay, computed identically on
both ends independently.

Mechanism: on each replica host, a `prio` qdisc with one band per
distinct peer (delay = the pairwise max for that peer) plus one
default band (0ms) for everything else -- including client traffic,
since the pairwise scheme only ever targets the 3 other replica IPs.
`u32` filters route by destination IP into the right band. This never
touches application code; the replica binary has no idea its network
is being shaped.

No hardcoded interface name -- `ip route get <peer-ip>` reports
whichever device the kernel would actually use to reach that peer,
so this works regardless of NIC naming on a given CloudLab hardware
type.
"""
from __future__ import annotations

from typing import Dict, List, Tuple


class NetemError(Exception):
    pass


def compute_pairwise_delays(node_latencies: Dict[int, int]) -> Dict[Tuple[int, int], int]:
    """{node_idx: latency_ms} -> {(a, b): max(lat_a, lat_b)} for every
    unordered pair a<b where at least one side is nonzero. Pairs where
    both sides are 0 are omitted (no rule needed -- default band covers
    them).
    """
    idxs = sorted(node_latencies)
    pairs = {}
    for i, a in enumerate(idxs):
        for b in idxs[i + 1:]:
            d = max(node_latencies[a], node_latencies[b])
            if d > 0:
                pairs[(a, b)] = d
    return pairs


def discover_iface(conn, peer_ip):
    """Ask the kernel on ``conn``'s host which device it would use to
    reach `peer_ip`. Works for any interface naming scheme.

    Takes the caller's pooled Fabric ``Connection`` rather than opening
    its own SSH session. An earlier version shelled out to `ssh` per
    call; each such call left a lingering connection on the host, ~2 per
    host per row, which reached ~480/host over a 300-row sweep and
    eventually stalled it. Going through the pool also means failures
    surface as paramiko/Fabric exceptions, which ``retry_on_ssh_error``
    knows how to retry -- ``subprocess.TimeoutExpired`` was not in its
    ``TRANSIENT_EXCEPTIONS``, so those failures killed the row outright.
    """
    r = conn.run(f'ip route get {peer_ip}', hide=True, warn=True)
    stdout = r.stdout or ''
    tokens = stdout.split()
    for token, nxt in zip(tokens, tokens[1:]):
        if token == 'dev':
            return nxt
    raise NetemError(
        f'could not determine outbound interface on {conn.host} toward '
        f'{peer_ip}: {stdout!r} {(r.stderr or "")!r}'
    )


PING_MARK = '@@PING'


def ping_command(peer_ips: List[str], count: int = 5,
                 interval: float = 0.2) -> str:
    """One shell command that pings every IP in ``peer_ips`` in parallel.

    Each ping writes to its own temp file; only after all have finished
    are the files printed, one after another, each under a
    ``@@PING <ip>`` header. An earlier version printed each ping's output
    from its own background subshell: bash's printf does not emit that
    in a single write, and on the cluster 1 in 12 probes interleaved,
    putting one link's statistics under another link's header.

    0.2s is the smallest interval iputils allows without root. ``-W 2``
    bounds the wait per reply, well above the largest round trip injected
    here (2 x 200ms).
    """
    pings = ' '.join(
        f'ping -n -q -c {count} -i {interval} -W 2 {ip} > "$d/{ip}" 2>&1 &'
        for ip in peer_ips)
    dumps = ' '.join(
        f'echo "{PING_MARK} {ip}"; cat "$d/{ip}";' for ip in peer_ips)
    return f'd=$(mktemp -d); {pings} wait; {dumps} rm -rf "$d"'


def parse_ping(output: str) -> Dict[str, dict]:
    """Parse ``ping_command`` output into {ip: stats}.

    stats: sent, received, loss_pct, and min/avg/max/mdev in ms. The four
    RTT fields are None when no reply arrived, since ping then prints no
    ``rtt`` line.
    """
    out: Dict[str, dict] = {}
    ip = None
    for line in output.splitlines():
        line = line.strip()
        if line.startswith(PING_MARK):
            ip = line.split()[1]
            out[ip] = {'sent': None, 'received': None, 'loss_pct': None,
                       'min': None, 'avg': None, 'max': None, 'mdev': None}
        elif ip is None:
            continue
        elif 'packets transmitted' in line:
            f = [x.strip() for x in line.split(',')]
            out[ip]['sent'] = int(f[0].split()[0])
            out[ip]['received'] = int(f[1].split()[0])
            out[ip]['loss_pct'] = float(
                next(x for x in f if 'packet loss' in x).split('%')[0])
        elif line.startswith('rtt ') or line.startswith('round-trip'):
            vals = line.split('=')[1].strip().split()[0].split('/')
            for k, v in zip(('min', 'avg', 'max', 'mdev'), vals):
                out[ip][k] = float(v)
    return out


def teardown_command(iface: str) -> str:
    """Idempotent: safe to run even if no qdisc was ever set up."""
    return f'sudo tc qdisc del dev {iface} root 2>/dev/null; true'


def check_clean_command(iface: str) -> str:
    """Prints the current root qdisc. Caller checks the output doesn't
    mention 'prio' or 'netem' (our own leftover) before applying new
    rules -- self-healing (teardown runs first regardless) but this
    surfaces an anomaly if a previous run's teardown didn't take."""
    return f'tc qdisc show dev {iface}'


def setup_commands(my_idx: int, peer_ips: Dict[int, str],
                   pairwise_delays: Dict[Tuple[int, int], int],
                   iface: str) -> List[str]:
    """Build this host's tc setup commands for its own index `my_idx`.

    peer_ips: {node_idx: ip} for every OTHER replica (not including
    my_idx). pairwise_delays: the full dict from compute_pairwise_delays
    (this function picks out only the pairs touching my_idx).
    """
    my_peers = {}  # peer_idx -> delay_ms, only pairs touching my_idx and >0
    for (a, b), d in pairwise_delays.items():
        if a == my_idx and b in peer_ips:
            my_peers[b] = d
        elif b == my_idx and a in peer_ips:
            my_peers[a] = d

    if not my_peers:
        return []  # nothing to do; default (no qdisc) already means 0 delay

    cmds = [teardown_command(iface)]
    n_bands = len(my_peers) + 1  # one per delayed peer + one default
    # priomap: 16 entries, each a 0-indexed band number. Point every TOS
    # value at the LAST band (the 0ms default) so only traffic explicitly
    # matched by a u32 filter below gets diverted into a delayed band.
    default_band_0idx = n_bands - 1
    priomap = ' '.join([str(default_band_0idx)] * 16)
    cmds.append(
        f'sudo tc qdisc add dev {iface} root handle 1: prio '
        f'bands {n_bands} priomap {priomap}'
    )
    # Band numbers in tc are 1-based; band n_bands is the default (0ms).
    for band, (peer_idx, delay) in enumerate(sorted(my_peers.items()), start=1):
        cmds.append(
            f'sudo tc qdisc add dev {iface} parent 1:{band} '
            f'handle {band}0: netem delay {int(delay)}ms'
        )
        cmds.append(
            f'sudo tc filter add dev {iface} parent 1:0 protocol ip '
            f'u32 match ip dst {peer_ips[peer_idx]}/32 flowid 1:{band}'
        )
    cmds.append(
        f'sudo tc qdisc add dev {iface} parent 1:{n_bands} '
        f'handle {n_bands}0: netem delay 0ms'
    )
    return cmds
