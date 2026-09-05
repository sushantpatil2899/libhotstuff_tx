"""Fabric task surface for the CloudLab benchmark harness.

All tasks expect:
  - benchmark/manifest.xml downloaded from the CloudLab portal (Experiment
    -> Manifest tab) after the experiment is ready.
  - benchmark/settings.json filled in (cloudlab.username, repo URL, branch).
  - Your CloudLab SSH key in the agent or at ~/.ssh/id_ed25519 so Fabric
    can reach every node without prompting.
"""
from fabric import task

from benchmark.remote import CloudLabBench
from benchmark.utils import BenchError, Print


@task
def install_cloudlab(ctx):
    """One-time setup on every CloudLab node.

    Installs build deps (cmake, libssl-dev, libuv1-dev, autotools, tmux),
    clones the repo (or pulls if already cloned), inits submodules
    recursively, runs cmake with HOTSTUFF_ENABLE_BENCHMARK=ON +
    HOTSTUFF_NORMAL_LOG=OFF, and builds.

    Prerequisites:
      1. CloudLab experiment is ready.
      2. manifest.xml is downloaded into this directory.
      3. settings.json has your username + repo URL.
      4. The SSH key in your CloudLab profile is also added to the GitHub
         account that owns the fork (so `git clone <ssh-url>` works on
         the remote nodes).
    """
    try:
        CloudLabBench(ctx).install()
    except BenchError as e:
        Print.error(e)


@task
def experiment_cloudlab(ctx, input_csv='experiments.csv',
                       output_csv='results/experiment_results.csv',
                       debug=False):
    """Run CSV-driven experiments on CloudLab nodes.

    Reads experiment configurations from ``input_csv``, executes each
    one, and writes per-row results into ``output_csv`` (created if
    needed). Rows already marked OK or DOWNLOADED in the output CSV are
    skipped, so re-running the command resumes from where the previous
    invocation stopped.

    Usage:
        fab experiment-cloudlab
        fab experiment-cloudlab --input-csv=my.csv --output-csv=my.out.csv
    """
    try:
        CloudLabBench(ctx).run_from_csv(input_csv, output_csv,
                                       debug=bool(debug))
    except BenchError as e:
        Print.error(e)


@task
def parser_daemon(ctx, run_logs_dir='results/run_logs',
                 csv_path='results/experiment_results.csv',
                 poll_interval=10):
    """Run the async log parser in a separate screen window.

    Launch in a SEPARATE `screen` window from `fab experiment-cloudlab`
    so parsing never blocks the run loop.

    Usage on the orchestrator (after `fab experiment-cloudlab` is running):
        screen -S parser
        cd ~/libhotstuff/benchmark
        fab parser-daemon
        # Ctrl-A D to detach. Re-attach: screen -r parser
    """
    from benchmark import parser_daemon as pd
    pd.main([
        '--run-logs-dir', str(run_logs_dir),
        '--csv-path', str(csv_path),
        '--poll-interval', str(poll_interval),
    ])


@task
def reconcile_csv(ctx, csv_path='results/experiment_results.csv',
                 run_logs_dir='results/run_logs'):
    """Promote DOWNLOADED rows to OK using metrics.json from the daemon.

    Idempotent. Useful for a manual catch-up after the daemon has parsed
    everything but the runner is no longer active.
    """
    from benchmark.reconciler import reconcile_csv as _do
    n = _do(csv_path, run_logs_dir=run_logs_dir)
    Print.info(f'Reconciled {n} row(s)')


@task
def kill(ctx):
    """Stop every libhotstuff process on every node (tmux kill-server)."""
    try:
        CloudLabBench(ctx).kill()
    except BenchError as e:
        Print.error(e)


@task
def logs(ctx, run_logs_dir='results/run_logs', run_id=None):
    """Print a human-readable summary for one parsed run.

    Defaults to the most recent run if run_id is not given.
    """
    import os
    from benchmark.logs import LogParser, ParseError

    if not os.path.isdir(run_logs_dir):
        Print.warn(f'No run_logs at {run_logs_dir}')
        return

    if run_id is None:
        candidates = sorted(
            [d for d in os.listdir(run_logs_dir)
             if os.path.isdir(os.path.join(run_logs_dir, d))],
            key=lambda d: os.path.getmtime(os.path.join(run_logs_dir, d)),
            reverse=True,
        )
        if not candidates:
            Print.warn(f'No run subdirs under {run_logs_dir}')
            return
        run_id = candidates[0]
        Print.info(f'(using most recent run_id: {run_id})')

    target = os.path.join(run_logs_dir, str(run_id))
    try:
        print(LogParser.process(target, meta={'run_id': run_id}).result())
    except ParseError as e:
        Print.error(BenchError(f'Failed to parse {target}', e))
