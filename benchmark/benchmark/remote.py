"""CloudLab orchestrator for libhotstuff benchmarks.

Mirrors the Narwhal harness in structure (install -> per-row config
+ launch -> download -> async parse via daemon) but every shell
command, config file, and parser is libhotstuff-specific.

Flow of ``run_from_csv``:

  1. Parse manifest.xml, settings.json.
  2. One-time _update() on all hosts: git pull + cmake + make.
  3. For each CSV row:
       a) Build BenchParameters / ProtocolParameters, skip the row with
          PARAM_ERROR if either rejects it.
       b) _select_hosts(): split first N as replicas, rest as client
          hosts (or collocate if asked, or if no extras exist).
       c) _config(): write ips.txt locally, invoke gen_conf.py to
          produce hotstuff.gen.conf + hotstuff.gen-sec{i}.conf, scp
          main conf + per-replica conf to each replica, scp main conf
          to each client host.
       d) _run_single(): on each replica host tmux-launch hotstuff-app;
          on each client host tmux-launch the assigned hotstuff-client
          processes; poll for natural client exit up to `duration`
          seconds (the cap); tmux-kill anything still running.
       e) _download_logs(): scp replica-{i}.log + client-{c}.log back
          into results/run_logs/<run_id>/.
       f) Touch READY + meta.json; write a DOWNLOADED row to the CSV.
  4. On exit, reconcile once so any rows the daemon already parsed
     get promoted to OK.

Parsing is deferred to ``benchmark.parser_daemon`` in a separate
screen window; the daemon turns READY dirs into metrics.json, the
reconciler folds those into the output CSV.

Only collocate=True is currently exercised end-to-end. Split mode
(clients on dedicated nodes) is wired in but unverified.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import tempfile
from copy import deepcopy
from math import ceil
from time import sleep

from fabric import Connection, ThreadingGroup as Group
from fabric.exceptions import GroupException
from paramiko.ssh_exception import SSHException

from benchmark.commands import CommandMaker
from benchmark.config import (
    BenchParameters, ProtocolParameters, ConfigError, write_ips_file,
)
from benchmark.csv_writer import append_row as _csv_append_row
from benchmark.instance import CloudLabInstanceManager
from benchmark.notifier import EmailNotifier
from benchmark.retry import retry_on_ssh_error
from benchmark.utils import BenchError, PathMaker, Print, progress_bar


class FabricError(Exception):
    """Wraps a Fabric GroupException with a human-readable message."""

    def __init__(self, error):
        assert isinstance(error, GroupException)
        message = list(error.result.values())[-1]
        super().__init__(message)


class ExecutionError(Exception):
    pass


# ----------------------------------------------------------------------
# Result columns written into the output CSV. Order matters: this is
# also what the reconciler looks up in metrics.json.
# ----------------------------------------------------------------------
RESULT_COLUMNS = (
    'tps',
    'latency_ms_mean',
    'latency_ms_p50',
    'latency_ms_p95',
    'latency_ms_p99',
    'duration_s',
    'n_committed',
    'n_clients',
    'n_replicas_booted',
    'status',
)


class CloudLabBench:

    def __init__(self, ctx):
        self.manager = CloudLabInstanceManager.make()
        self.settings = self.manager.settings
        self.user = self.settings.cloudlab_username
        self.notifier = EmailNotifier()
        # One Fabric Connection per host, reused across calls. Creating
        # a new Connection per launch trips sshd's MaxStartups limit at
        # tens of clients (we saw this in Narwhal at workers=20).
        self._ssh_pool: dict[str, Connection] = {}

    # ------------------------------------------------------------------
    # SSH connection plumbing
    # ------------------------------------------------------------------

    def _conn(self, ssh_host: str) -> Connection:
        c = self._ssh_pool.get(ssh_host)
        if c is None:
            c = Connection(ssh_host, user=self.user)
            self._ssh_pool[ssh_host] = c
        return c

    def _reset_pool(self) -> None:
        for c in self._ssh_pool.values():
            try:
                c.close()
            except Exception:
                pass
        self._ssh_pool = {}

    @staticmethod
    def _check_stderr(output):
        if isinstance(output, dict):
            for x in output.values():
                if x.stderr:
                    raise ExecutionError(x.stderr)
        else:
            if output.stderr:
                raise ExecutionError(output.stderr)

    def _background_run(self, ssh_host, command, log_file):
        """nohup-launch ``command`` on ``ssh_host`` with stdout+stderr
        redirected directly to ``log_file``. PID written to /tmp so
        the existing pkill-by-name in ``kill()`` still works, and we
        have a backup handle if pkill races a still-binding process.

        Previously used tmux+tee, but the tmux PTY buffer became a
        throughput bottleneck above ~30k commit lines/s — the client
        blocked on stderr writes once the PTY filled. Direct file
        redirect goes through kernel block-buffered I/O (page cache),
        which sustains MB/s easily.
        """
        name = os.path.splitext(os.path.basename(log_file))[0]
        # Single-line: background nohup the inner command, capture PID.
        # `< /dev/null` avoids tying stdin to the SSH channel.
        # The PID file is best-effort housekeeping; ``kill()`` uses
        # ``pkill -x hotstuff-client`` / ``pkill -x hotstuff-app`` as
        # the authoritative kill mechanism.
        cmd = (
            f'nohup {command} > {log_file} 2>&1 < /dev/null & '
            f'echo $! > /tmp/hotstuff_pid_{name}'
        )
        c = self._conn(ssh_host)
        output = c.run(cmd, hide=True)
        self._check_stderr(output)

    def _count_alive_clients(self, client_pairs, num_clients):
        """Count ``hotstuff-client`` processes still running across the
        unique client hosts assigned to this run.

        Used by ``_run_single`` to detect when finite-``iter_count``
        clients have all exited naturally, so we don't sleep past their
        completion and don't SIGTERM still-flushing processes.

        On any SSH error, conservatively assume all clients are alive
        (returns ``num_clients``) so the caller keeps waiting rather
        than killing prematurely.
        """
        hosts = sorted({h for h, _ in client_pairs[:num_clients]})
        total = 0
        for host in hosts:
            try:
                c = self._conn(host)
                # ``pgrep -c`` always writes the count to stdout and exits
                # 1 when the count is zero. ``warn=True`` keeps Fabric
                # from raising on the non-zero exit. No fallback shell
                # construct — that previously double-wrote "0" to stdout
                # and made int() raise, defaulting to "all alive".
                result = c.run(
                    'pgrep -c "^hotstuff-client$"',
                    hide=True, warn=True,
                )
                total += int((result.stdout or '0').strip() or '0')
            except Exception:
                return num_clients
        return total

    @staticmethod
    def _archive_logs(dest_dir):
        """Copy benchmark/logs/* to ``dest_dir`` for one-run archival."""
        src = PathMaker.logs_path()
        if not os.path.isdir(src):
            return
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)
        shutil.copytree(src, dest_dir)

    @staticmethod
    def _mark_log_dir_ready(dest_dir, run_id):
        """Write meta.json THEN touch READY (in that order).

        The daemon reads READY as 'dir is consistent'. Touching it last
        guarantees the daemon never opens a partially-populated dir.
        """
        os.makedirs(dest_dir, exist_ok=True)
        meta = {'run_id': str(run_id)}
        with open(os.path.join(dest_dir, 'meta.json'), 'w') as f:
            json.dump(meta, f)
        open(os.path.join(dest_dir, 'READY'), 'w').close()

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    def install(self):
        """One-time setup on every CloudLab node: apt deps, clone,
        submodules, cmake configure, make."""
        Print.info(
            'Installing build deps + cloning libhotstuff on every node...'
        )
        repo_name = self.settings.repo_name
        cmd = ' && '.join([
            CommandMaker.apt_install(),
            CommandMaker.clone(self.settings.repo_url, repo_name),
            CommandMaker.git_sync(repo_name, self.settings.branch),
            # benchmark=False: this fork (unlike upstream) already does
            # `#define HOTSTUFF_ENABLE_BENCHMARK` unconditionally in
            # hotstuff_client.cpp, so passing -DHOTSTUFF_ENABLE_BENCHMARK
            # here too would just be a harmless-but-noisy macro
            # redefinition warning on every build.
            CommandMaker.cmake_configure(repo_name, benchmark=False),
            CommandMaker.make(repo_name),
        ])
        hosts = self.manager.ssh_hosts()
        try:
            g = Group(*hosts, user=self.user)
            g.run(cmd, hide=True)
            Print.heading(f'Initialized testbed of {len(hosts)} nodes')
        except (GroupException, ExecutionError) as e:
            e = FabricError(e) if isinstance(e, GroupException) else e
            raise BenchError('Failed to install libhotstuff', e)

    @retry_on_ssh_error()
    def kill(self, hosts=None, delete_logs=False):
        """Tmux-kill on every host (or the subset given).

        Decorated with the same retry as _run_single/_download_logs —
        this was previously the one SSH-flaky operation in the row loop
        that caught GroupException and immediately rewrapped it as
        BenchError, which meant a transient blip here (observed in
        practice: "Error reading SSH protocol banner" during a 96-row
        sweep) killed the whole `fab experiment-cloudlab` run instead of
        retrying, even though _run_single itself is retry-decorated —
        because by the time the exception reached that outer decorator
        it was no longer a TRANSIENT_EXCEPTIONS type. Letting the raw
        GroupException propagate here (instead of converting it inline)
        is what makes this decorator's retry actually take effect.
        """
        hosts = hosts if hosts is not None else self.manager.ssh_hosts()
        pieces = [
            CommandMaker.clean_logs() if delete_logs else 'true',
            f'({CommandMaker.kill()} || true)',
        ]
        cmd = ' && '.join(pieces)
        g = Group(*hosts, user=self.user)
        g.run(cmd, hide=True)

    # ------------------------------------------------------------------
    # Per-run pipeline
    # ------------------------------------------------------------------

    def _select_hosts(self, bench: BenchParameters):
        """Return (replica_hosts, client_hosts) — both as lists of
        (ssh_hostname, protocol_ip) tuples in manifest order.

        Replica hosts come first (``bench.nodes`` entries). If extras
        exist in the manifest and ``collocate_client`` is False, those
        extras become client hosts; otherwise client processes share
        the replica machines.
        """
        ssh = self.manager.ssh_hosts()
        priv = self.manager.hosts()
        proto = ssh if self.manager.manifest.multi_site else priv

        if len(ssh) < bench.nodes:
            Print.warn(
                f'Need {bench.nodes} replicas but manifest has {len(ssh)} '
                'nodes'
            )
            return [], []

        replica_pairs = list(zip(ssh[:bench.nodes], proto[:bench.nodes]))
        extras = list(zip(ssh[bench.nodes:], proto[bench.nodes:]))

        if bench.collocate_client or not extras:
            return replica_pairs, replica_pairs[:]
        return replica_pairs, extras

    @retry_on_ssh_error()
    def _update(self, bench: BenchParameters):
        """git pull + rebuild on every replica + client host."""
        hosts = self.manager.ssh_hosts()
        Print.info(f'Updating + rebuilding on {len(hosts)} nodes '
                   f'(branch "{self.settings.branch}")...')
        repo = self.settings.repo_name
        cmd = ' && '.join([
            CommandMaker.git_sync(repo, self.settings.branch),
            CommandMaker.cmake_configure(repo, benchmark=False),
            CommandMaker.make(repo),
        ])
        g = Group(*hosts, user=self.user)
        g.run(cmd, hide=True)

    def _generate_configs(self, protocol: ProtocolParameters,
                          replica_ips: list[str], tmp_dir: str):
        """Run scripts/gen_conf.py on the orchestrator to produce
        hotstuff.gen.conf + hotstuff.gen-sec*.conf inside ``tmp_dir``.

        Returns the list of generated file paths so the caller can scp
        them to remote hosts.
        """
        ips_file = os.path.join(tmp_dir, 'ips.txt')
        write_ips_file(ips_file, replica_ips)

        kwargs = protocol.gen_conf_kwargs(
            ips_file=ips_file, prefix=PathMaker.conf_prefix(),
        )
        cmd = CommandMaker.gen_conf(
            repo_name=PathMaker.repo_root(), **kwargs,
        )
        # Run from inside tmp_dir so gen_conf.py drops its outputs there.
        Print.info('Generating configs locally via gen_conf.py...')
        try:
            subprocess.run(
                cmd, shell=True, cwd=tmp_dir, check=True,
                stderr=subprocess.PIPE, stdout=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as e:
            raise BenchError(
                'gen_conf.py failed; check that hotstuff-keygen and '
                'hotstuff-tls-keygen exist in the repo root',
                ExecutionError(e.stderr.decode('utf-8', 'replace')),
            )

        main_conf = os.path.join(tmp_dir, PathMaker.main_conf_file())
        sec_confs = [
            os.path.join(tmp_dir, PathMaker.replica_conf_file(i))
            for i in range(len(replica_ips))
        ]
        for p in [main_conf] + sec_confs:
            if not os.path.exists(p):
                raise BenchError(
                    f'gen_conf.py did not produce expected file: {p}',
                    FileNotFoundError(p),
                )
        return main_conf, sec_confs

    @retry_on_ssh_error()
    def _config(self, replica_pairs, client_pairs, protocol):
        """Generate configs locally, scp them to each remote host."""
        replica_ips = [ip for _, ip in replica_pairs]

        with tempfile.TemporaryDirectory() as tmp:
            main_conf, sec_confs = self._generate_configs(
                protocol, replica_ips, tmp,
            )

            # Push to each replica: main conf + that replica's per-conf.
            progress = progress_bar(
                replica_pairs, prefix='Uploading replica configs:',
            )
            for i, (ssh_host, _) in enumerate(progress):
                c = self._conn(ssh_host)
                c.run(f'{CommandMaker.cleanup()} || true', hide=True)
                c.put(main_conf, PathMaker.main_conf_file())
                c.put(sec_confs[i], PathMaker.replica_conf_file(i))

            # Push to each unique client host: main conf only.
            unique_client_hosts = sorted({h for h, _ in client_pairs})
            replica_hosts = {h for h, _ in replica_pairs}
            extras_only = [
                h for h in unique_client_hosts if h not in replica_hosts
            ]
            progress = progress_bar(
                extras_only, prefix='Uploading client configs:',
            )
            for ssh_host in progress:
                c = self._conn(ssh_host)
                c.run(f'{CommandMaker.cleanup()} || true', hide=True)
                c.put(main_conf, PathMaker.main_conf_file())

    @retry_on_ssh_error()
    def _run_single(self, replica_pairs, client_pairs, bench, protocol):
        """Boot replicas, boot clients, sleep duration, kill everything."""
        self._reset_pool()  # fresh connections for this run

        all_hosts = sorted({h for h, _ in replica_pairs + client_pairs})
        self.kill(hosts=all_hosts, delete_logs=True)

        repo = self.settings.repo_name

        # 1) Replicas
        Print.info('Booting replicas...')
        for i, (ssh_host, _) in enumerate(replica_pairs):
            cmd = CommandMaker.run_replica(
                repo_dir=repo,
                conf_file=PathMaker.replica_conf_file(i),
                max_rep_msg=protocol.max_rep_msg,
                max_cli_msg=protocol.max_cli_msg,
            )
            self._background_run(
                ssh_host, cmd, PathMaker.replica_log_file(i),
            )

        # Give replicas a moment to bind ports and accept peers before
        # we start hammering them with clients.
        sleep(3)

        # 2) Clients — round-robin across client_pairs.
        Print.info(f'Booting {bench.num_clients} client process(es)...')
        for c_idx in range(bench.num_clients):
            ssh_host, _ = client_pairs[c_idx % len(client_pairs)]
            cmd = CommandMaker.run_client(
                repo_dir=repo,
                conf_file=PathMaker.main_conf_file(),
                cid=c_idx,
                iter_count=bench.iter_count,
                max_async=bench.max_async,
                max_cli_msg=protocol.max_cli_msg,
            )
            self._background_run(
                ssh_host, cmd, PathMaker.client_log_file(c_idx),
            )

        # 3) Wait for clients to exit naturally (finite ``iter_count``)
        # OR ``duration`` cap, whichever comes first. ``duration`` is
        # now a safety cap rather than a fixed sleep — so finite-iter
        # runs finish promptly without wasting wall-clock, and
        # iter_count=-1 runs degrade gracefully to the old behavior
        # (cap hit, then kill).
        poll_interval = 2
        elapsed = 0
        Print.info(
            f'Waiting for {bench.num_clients} client(s) to finish '
            f'(cap {bench.duration}s, polling every {poll_interval}s)...'
        )
        while elapsed < bench.duration:
            alive = self._count_alive_clients(
                client_pairs, bench.num_clients,
            )
            if alive == 0:
                Print.info(
                    f'  All clients exited naturally after ~{elapsed}s.'
                )
                break
            sleep(poll_interval)
            elapsed += poll_interval
        else:
            Print.info(
                f'  Duration cap ({bench.duration}s) hit; '
                f'{alive} client(s) still running, will be killed.'
            )

        # 4) Stop everyone (no-op for clients that already exited).
        self.kill(hosts=all_hosts, delete_logs=False)

    @retry_on_ssh_error()
    def _download_logs(self, replica_pairs, client_pairs, bench):
        """scp replica + client logs into benchmark/logs/."""
        subprocess.run(
            CommandMaker.clean_logs(), shell=True, check=False,
            stderr=subprocess.DEVNULL,
        )
        os.makedirs(PathMaker.logs_path(), exist_ok=True)

        progress = progress_bar(
            replica_pairs, prefix='Downloading replica logs:',
        )
        for i, (ssh_host, _) in enumerate(progress):
            c = self._conn(ssh_host)
            local = PathMaker.replica_log_file(i)
            try:
                c.get(PathMaker.replica_log_file(i), local=local)
            except (OSError, FileNotFoundError) as e:
                Print.warn(f'replica {i} log fetch failed: {e}')

        progress = progress_bar(
            range(bench.num_clients), prefix='Downloading client logs:',
        )
        for c_idx in progress:
            ssh_host, _ = client_pairs[c_idx % len(client_pairs)]
            c = self._conn(ssh_host)
            local = PathMaker.client_log_file(c_idx)
            try:
                c.get(PathMaker.client_log_file(c_idx), local=local)
            except (OSError, FileNotFoundError) as e:
                Print.warn(f'client {c_idx} log fetch failed: {e}')

    # ------------------------------------------------------------------
    # CSV-driven entry point
    # ------------------------------------------------------------------

    def run_from_csv(self, input_file: str, output_file: str,
                     debug: bool = False) -> None:
        """Read ``input_file``, run each row, write ``output_file``."""
        Print.heading(f'Starting CSV-driven CloudLab benchmark: {input_file}')

        with open(input_file, 'r') as f:
            reader = csv.DictReader(f)
            input_columns = list(reader.fieldnames or [])
            rows = list(reader)

        if not rows:
            Print.warn('Input CSV is empty')
            return

        # Output schema = input columns + RESULT_COLUMNS (excluding any
        # collisions — input column wins on display order, result fills
        # in metric values).
        seen = set(input_columns)
        csv_fieldnames = list(input_columns) + [
            c for c in RESULT_COLUMNS if c not in seen
        ]

        # One-time build pass before the loop. Saves N-1 rebuilds.
        try:
            first_bench = BenchParameters(self._row_to_bench(rows[0]))
        except ConfigError as e:
            raise BenchError(f'First row has invalid bench params', e)
        try:
            self._update(first_bench)
        except (GroupException, ExecutionError, SSHException,
                OSError, EOFError) as e:
            e = FabricError(e) if isinstance(e, GroupException) else e
            self.notifier.notify(
                subject='Initial _update failed — experiment cannot start',
                body=(
                    f'Initial compile/update step failed before any runs '
                    f'could execute.\nError: {type(e).__name__}: {e}'
                ),
                throttle_key='startup_failure',
            )
            raise BenchError('Failed to update nodes', e)

        # Resume support — skip rows already OK or DOWNLOADED.
        completed_ids: set[str] = set()
        if os.path.exists(output_file):
            try:
                self._reconcile_csv(output_file)
            except Exception as rec_err:
                Print.warn(f'Reconciler at startup failed: {rec_err}')
            with open(output_file, 'r') as ef:
                for erow in csv.DictReader(ef):
                    rid = erow.get('run_id', '')
                    if rid and erow.get('status') in ('OK', 'DOWNLOADED'):
                        completed_ids.add(rid)
            if completed_ids:
                Print.info(
                    f'Resuming: skipping {len(completed_ids)} already-'
                    f'completed run(s).'
                )

        completed_count = 0
        failed_count = 0

        self.notifier.notify(
            subject=f'Experiment started: {len(rows)} rows in CSV',
            body=(
                f'Input: {input_file}\nOutput: {output_file}\n'
                f'Rows: {len(rows)}\n'
                f'Already completed: {len(completed_ids)}\n'
            ),
            throttle_key=None,
        )

        try:
            for idx, row in enumerate(rows):
                run_id = row.get('run_id') or str(idx + 1)
                if run_id in completed_ids:
                    Print.info(f'Skipping {run_id} (already completed)')
                    continue
                Print.heading(
                    f'\nRow {idx + 1}/{len(rows)} (run_id={run_id})'
                )

                try:
                    bench = BenchParameters(self._row_to_bench(row))
                    protocol = ProtocolParameters(self._row_to_protocol(row))
                except ConfigError as e:
                    Print.error(BenchError(f'PARAM_ERROR for {run_id}', e))
                    self._write_row(
                        output_file, csv_fieldnames, row,
                        status=f'PARAM_ERROR: {e}',
                    )
                    continue

                replica_pairs, client_pairs = self._select_hosts(bench)
                if not replica_pairs:
                    self._write_row(
                        output_file, csv_fieldnames, row,
                        status='NOT_ENOUGH_NODES',
                    )
                    continue

                run_log_dir = os.path.join(
                    PathMaker.run_logs_path(), str(run_id),
                )

                try:
                    self._config(replica_pairs, client_pairs, protocol)
                except (subprocess.SubprocessError, GroupException,
                        SSHException, OSError, EOFError) as e:
                    e = FabricError(e) if isinstance(e, GroupException) else e
                    Print.error(BenchError(f'CONFIG_ERROR for {run_id}', e))
                    self._write_row(
                        output_file, csv_fieldnames, row,
                        status=f'CONFIG_ERROR: {e}',
                    )
                    self.notifier.notify(
                        subject=f'Run {run_id} CONFIG_ERROR',
                        body=f'{type(e).__name__}: {e}',
                        throttle_key='run_failure',
                    )
                    continue

                try:
                    self._run_single(
                        replica_pairs, client_pairs, bench, protocol,
                    )
                    self._download_logs(replica_pairs, client_pairs, bench)
                    self._archive_logs(run_log_dir)
                    self._mark_log_dir_ready(run_log_dir, run_id)

                    self._write_row(
                        output_file, csv_fieldnames, row,
                        status='DOWNLOADED',
                    )
                    completed_count += 1
                    Print.info(
                        f'Run {run_id}: logs downloaded, queued for parse'
                    )
                    if completed_count and completed_count % 50 == 0:
                        self.notifier.notify(
                            subject=f'Milestone: {completed_count} runs downloaded',
                            body=f'{completed_count}/{len(rows)} so far.',
                            throttle_key=f'milestone_{completed_count}',
                        )

                except (subprocess.SubprocessError, GroupException,
                        SSHException, OSError, EOFError) as e:
                    try:
                        self.kill(
                            hosts=sorted({
                                h for h, _ in replica_pairs + client_pairs
                            })
                        )
                    except Exception as kill_err:
                        Print.error(BenchError(
                            f'kill() during cleanup of {run_id} also failed',
                            kill_err,
                        ))
                    if isinstance(e, GroupException):
                        e = FabricError(e)
                    Print.error(BenchError(f'Run {run_id} failed', e))
                    failed_count += 1
                    try:
                        self._archive_logs(run_log_dir)
                    except OSError as arch_err:
                        Print.error(BenchError(
                            f'Archiving logs for failed {run_id} also failed',
                            arch_err,
                        ))
                    self._write_row(
                        output_file, csv_fieldnames, row,
                        status=f'RUN_ERROR: {e}',
                    )
                    self.notifier.notify(
                        subject=f'Run {run_id} failed ({type(e).__name__})',
                        body=(
                            f'{completed_count} OK, {failed_count} failed '
                            f'out of {len(rows)}.\n{e}'
                        ),
                        throttle_key=f'run_failure_{type(e).__name__}',
                    )
                    continue

        except KeyboardInterrupt:
            self.notifier.notify(
                subject='Experiment INTERRUPTED (Ctrl-C)',
                body=(
                    f'Progress: {completed_count} OK, {failed_count} failed '
                    f'out of {len(rows)}.\nResume by re-running with the '
                    f'same output file: {output_file}'
                ),
                throttle_key=None,
            )
            raise

        # Final reconcile to promote any DOWNLOADED rows the daemon
        # already parsed.
        try:
            self._reconcile_csv(output_file)
        except Exception as rec_err:
            Print.warn(f'Final reconcile failed: {rec_err}')

        Print.heading(
            f'\nAll experiments done. Results: {output_file}'
        )
        self.notifier.notify(
            subject=(
                f'Experiment complete: {completed_count} OK, '
                f'{failed_count} failed'
            ),
            body=(
                f'Total rows: {len(rows)}\n'
                f'Completed this session: {completed_count}\n'
                f'Failed: {failed_count}\n'
                f'Output: {output_file}\n'
            ),
            throttle_key=None,
        )

    # ------------------------------------------------------------------
    # CSV row -> param dicts
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_bench(row: dict) -> dict:
        """Pluck the BenchParameters fields out of a CSV row."""
        return {
            'nodes': row.get('nodes', 4),
            'num_clients': row['num_clients'],
            'iter_count': row.get('iter_count', -1),
            'max_async': row['max_async'],
            'duration': row.get('duration', 60),
            'runs': row.get('runs', 1),
            'collocate_client': str(
                row.get('collocate_client', 'true')
            ).lower() in ('true', '1', 'yes'),
        }

    @staticmethod
    def _row_to_protocol(row: dict) -> dict:
        """Pluck the ProtocolParameters fields out of a CSV row.

        Missing columns fall back to the class defaults so a sparse CSV
        still produces a runnable config.
        """
        keys = ('block_size', 'pace_maker', 'nworker', 'repnworker',
                'clinworker', 'repburst', 'cliburst', 'max_rep_msg',
                'max_cli_msg', 'pport', 'cport')
        return {k: row[k] for k in keys if k in row and row[k] != ''}

    # ------------------------------------------------------------------
    # CSV write helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _write_row(output_file: str, csv_fieldnames: list[str],
                   input_row: dict, *, status: str) -> None:
        """Append one row to ``output_file``. Metric columns blank.

        Uses ``csv_writer.append_row`` for flock + lazy-header semantics.
        """
        out = dict(input_row)
        for col in RESULT_COLUMNS:
            if col == 'status':
                continue
            out.setdefault(col, '')
        out['status'] = status
        _csv_append_row(output_file, csv_fieldnames, out)

    @staticmethod
    def _reconcile_csv(csv_path: str,
                       run_logs_dir: str | None = None) -> int:
        from benchmark.reconciler import reconcile_csv
        if run_logs_dir is None:
            run_logs_dir = PathMaker.run_logs_path()
        n = reconcile_csv(csv_path, run_logs_dir=run_logs_dir)
        if n:
            Print.info(f'Reconciler: upgraded {n} row(s) in {csv_path}')
        return n
