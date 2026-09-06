#!/usr/bin/env python3
"""One-off diagnostic: does the kernel/syscall time scale with commits
(per-command) or with rounds (per-block/per-command / block_size)?

For a given (block_size, max_async), this:
  1. Generates configs and boots 4 replicas + 1 client (reusing the
     harness's own CommandMaker/config machinery, not fab's row loop --
     that loop has no hook for injecting a precisely-timed strace
     attach mid-run).
  2. Lets load stabilize for 15s.
  3. Attaches `strace -c -f` to the leader's hotstuff-app for exactly
     WINDOW seconds (blocking), producing an exact sendto/sendmsg count
     for that interval.
  4. Kills everything, downloads the client log.
  5. Counts commits whose timestamp falls inside [t_start, t_end] from
     the client log (same format logs.py parses) -- ground truth for
     how many commands were actually committed during the exact
     strace window, independent of any slowdown strace itself causes.
  6. Prints sendto count, commit count, implied round count
     (commits // block_size), and both ratios.

Usage:
    .venv/bin/python3 strace_probe.py --block-size 100 --max-async 8000 \
        --run-id STRACE_bs100_ma8000 --window 30
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from benchmark.manifest import Manifest
from benchmark.config import ProtocolParameters, write_ips_file
from benchmark.commands import CommandMaker
from benchmark.utils import PathMaker
from benchmark.settings import CloudLabSettings

_RE_COMMIT = re.compile(
    r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) \[hotstuff info\] '
    r'([0-9.]+)\s*$'
)


def sh_quote(s):
    """POSIX single-quote a string for embedding as ONE argv element in a
    remote shell command. run_replica/run_client already return a
    `bash -lc '...'`-wrapped string with its own embedded single quotes,
    so this must escape those (the standard `'\\''` trick) rather than
    naively wrapping in another pair of single quotes, which would
    terminate the outer quoting early and hand tmux a broken command.
    """
    return "'" + s.replace("'", "'\\''") + "'"


def ssh(host, user, cmd, timeout=None):
    full = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            f'{user}@{host}', cmd]
    return subprocess.run(full, capture_output=True, text=True, timeout=timeout)


def scp_to(host, user, local_path, remote_name):
    subprocess.run(
        ['scp', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
         local_path, f'{user}@{host}:{remote_name}'],
        check=True, capture_output=True,
    )


def remote_now(host, user):
    """The client's own clock, in the exact format its log timestamps use.

    Querying the client's local `date` instead of this machine's UTC
    clock sidesteps timezone entirely -- the client displays MDT
    (confirmed: `date -u` and `date` differ by 6h, `timedatectl` claims
    UTC but /etc/localtime disagrees), and the log's strftime() call
    uses localtime(), whatever that resolves to. Comparing like-for-like
    avoids depending on getting that resolution right from the outside.
    """
    r = ssh(host, user, "date '+%Y-%m-%d %H:%M:%S.%6N'")
    return datetime.strptime(r.stdout.strip(), '%Y-%m-%d %H:%M:%S.%f')


def scp_from(host, user, remote_path, local_path):
    subprocess.run(
        ['scp', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
         f'{user}@{host}:{remote_path}', local_path],
        check=True, capture_output=True,
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--block-size', type=int, required=True)
    p.add_argument('--max-async', type=int, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--window', type=int, default=30,
                    help='strace attach duration in seconds')
    p.add_argument('--settle', type=int, default=15,
                    help='seconds to let load stabilize before attaching strace')
    args = p.parse_args()

    settings = CloudLabSettings.load(
        os.path.join(os.path.dirname(__file__), 'settings.json')
    )
    manifest = Manifest.load(os.path.join(os.path.dirname(__file__), 'manifest.xml'))
    user = settings.cloudlab_username
    repo_name = settings.repo_name

    replica_hosts = manifest.hostnames[:4]
    replica_ips = manifest.hosts[:4]
    client_host = manifest.hostnames[4]
    leader_host = replica_hosts[1]  # fixed proposer index = 1

    proto = ProtocolParameters({
        'block_size': str(args.block_size),
        'pace_maker': 'dummy',
        'sb_users': '1000', 'sb_prob_choose_mtx': '0.9', 'sb_skew_factor': '0.1',
    })

    with tempfile.TemporaryDirectory() as tmp:
        ips_file = os.path.join(tmp, 'ips.txt')
        write_ips_file(ips_file, replica_ips)
        kwargs = proto.gen_conf_kwargs(ips_file=ips_file, prefix=PathMaker.conf_prefix())
        cmd = CommandMaker.gen_conf(repo_name=PathMaker.repo_root(), **kwargs)
        r = subprocess.run(cmd, shell=True, cwd=tmp, capture_output=True, text=True)
        if r.returncode != 0:
            print('gen_conf failed:', r.stderr)
            sys.exit(1)

        main_conf = os.path.join(tmp, PathMaker.main_conf_file())
        sec_confs = [os.path.join(tmp, PathMaker.replica_conf_file(i)) for i in range(4)]

        print(f'[{args.run_id}] cleaning + uploading configs...')
        all_hosts = list(dict.fromkeys(replica_hosts + [client_host]))
        for h in all_hosts:
            ssh(h, user, 'pkill -SIGKILL -x hotstuff-app 2>/dev/null; '
                          'pkill -SIGKILL -x hotstuff-client 2>/dev/null; '
                          'tmux kill-session -t hsrep0 2>/dev/null; '
                          'tmux kill-session -t hsrep1 2>/dev/null; '
                          'tmux kill-session -t hsrep2 2>/dev/null; '
                          'tmux kill-session -t hsrep3 2>/dev/null; '
                          'tmux kill-session -t hscli 2>/dev/null; '
                          f'rm -f {PathMaker.main_conf_file()} hotstuff-sec*.conf; true')
            scp_to(h, user, main_conf, PathMaker.main_conf_file())
        for i, h in enumerate(replica_hosts):
            scp_to(h, user, sec_confs[i], PathMaker.replica_conf_file(i))

        print(f'[{args.run_id}] booting replicas...')
        for i, h in enumerate(replica_hosts):
            rcmd = CommandMaker.run_replica(
                repo_dir=repo_name, conf_file=PathMaker.replica_conf_file(i),
            )
            inner = f"{rcmd} > replica-{i}.log 2>&1"
            ssh(h, user, f"tmux new-session -d -s hsrep{i} {sh_quote(inner)}")
        time.sleep(3)

        print(f'[{args.run_id}] booting client (max_async={args.max_async})...')
        ccmd = CommandMaker.run_client(
            repo_dir=repo_name, conf_file=PathMaker.main_conf_file(),
            cid=0, iter_count=-1, max_async=args.max_async,
        )
        inner_c = f"{ccmd} > client-0.log 2>&1"
        ssh(client_host, user, f"tmux new-session -d -s hscli {sh_quote(inner_c)}")

        print(f'[{args.run_id}] settling {args.settle}s...')
        time.sleep(args.settle)

        print(f'[{args.run_id}] finding leader PID on {leader_host}...')
        pid_r = ssh(leader_host, user, "pgrep -x hotstuff-app | head -1")
        pid = pid_r.stdout.strip()
        if not pid:
            print('Could not find hotstuff-app PID on leader'); sys.exit(1)
        print(f'[{args.run_id}] leader PID={pid}')

        trace_remote = f'/tmp/{args.run_id}.trace'
        t_start = remote_now(client_host, user)
        print(f'[{args.run_id}] strace window starting at {t_start.isoformat()} '
              f'(client clock) for {args.window}s...')
        ssh(leader_host, user,
            f'sudo timeout -s INT {args.window} strace -c -f -U calls,name '
            f'-p {pid} -o {trace_remote}',
            timeout=args.window + 20)
        t_end = remote_now(client_host, user)
        print(f'[{args.run_id}] strace window ended at {t_end.isoformat()} (client clock)')

        # Let the run keep going a moment, then tear down.
        time.sleep(2)
        print(f'[{args.run_id}] tearing down...')
        for h in all_hosts:
            ssh(h, user, 'pkill -SIGTERM -x hotstuff-client 2>/dev/null; '
                          'pkill -SIGTERM -x hotstuff-app 2>/dev/null; true')
        time.sleep(3)
        for h in all_hosts:
            ssh(h, user, 'pkill -SIGKILL -x hotstuff-client 2>/dev/null; '
                          'pkill -SIGKILL -x hotstuff-app 2>/dev/null; true')

        local_trace = os.path.join(tmp, 'trace.out')
        ssh(leader_host, user, f'sudo chmod 644 {trace_remote}')
        scp_from(leader_host, user, trace_remote, local_trace)

        local_client_log = os.path.join(tmp, 'client-0.log')
        scp_from(client_host, user, 'client-0.log', local_client_log)

        # ---- parse strace -U calls,name summary: "<calls> <name>" per line ----
        sendto_count = 0
        sendmsg_count = 0
        total_syscalls = 0
        with open(local_trace, 'r', errors='replace') as f:
            trace_text = f.read()
        for line in trace_text.splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            calls_str, name = parts
            if not calls_str.isdigit():
                continue
            calls = int(calls_str)
            if name == 'sendto':
                sendto_count = calls
            elif name == 'sendmsg':
                sendmsg_count = calls
            elif name == 'total':
                total_syscalls = calls

        # ---- parse client log for commits within [t_start, t_end] ----
        commit_count = 0
        with open(local_client_log, 'r', errors='replace') as f:
            for line in f:
                m = _RE_COMMIT.search(line)
                if not m:
                    continue
                try:
                    ts = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S.%f')
                except ValueError:
                    continue
                if t_start <= ts <= t_end:
                    commit_count += 1

        window_s = (t_end - t_start).total_seconds()
        implied_rounds = commit_count / args.block_size if args.block_size else 0
        commits_per_sec = commit_count / window_s if window_s else 0
        rounds_per_sec = implied_rounds / window_s if window_s else 0
        sendto_per_sec = sendto_count / window_s if window_s else 0

        print(f'\n==== RESULT {args.run_id} '
              f'(block_size={args.block_size}, max_async={args.max_async}) ====')
        print(f'strace window: {window_s:.2f}s')
        print(f'total syscalls in window: {total_syscalls}')
        print(f'sendto calls: {sendto_count}   sendmsg calls: {sendmsg_count}')
        print(f'commits in window (from client log timestamps): {commit_count}')
        print(f'implied rounds in window (commits / block_size): {implied_rounds:.1f}')
        print(f'commits/sec: {commits_per_sec:.1f}   rounds/sec: {rounds_per_sec:.1f}   '
              f'sendto/sec: {sendto_per_sec:.1f}')
        if commit_count:
            print(f'sendto per commit: {sendto_count / commit_count:.4f}')
        if implied_rounds:
            print(f'sendto per round:  {sendto_count / implied_rounds:.4f}')
        print(f'raw trace saved: {local_trace} -> copying to '
              f'results/strace/{args.run_id}.trace')
        os.makedirs('results/strace', exist_ok=True)
        subprocess.run(['cp', local_trace, f'results/strace/{args.run_id}.trace'])
        subprocess.run(['cp', local_client_log, f'results/strace/{args.run_id}_client.log'])


if __name__ == '__main__':
    main()
