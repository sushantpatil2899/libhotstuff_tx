"""Path conventions, printing helpers, and the shared exception type.

Adapted from the Narwhal benchmark harness. Paths reflect libhotstuff's
config-file and binary layout rather than Narwhal's Rust/JSON layout.
"""
import os
from os.path import join

# Absolute path to the libhotstuff repo root, derived from this file's
# location (<repo>/benchmark/benchmark/utils.py). Computed once at import
# time so paths stay correct regardless of the caller's cwd — needed
# because _generate_configs chdir's into a tempdir before invoking
# scripts/gen_conf.py.
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)


class BenchError(Exception):
    def __init__(self, message, error):
        assert isinstance(error, Exception)
        self.message = message
        self.cause = error
        super().__init__(message)


class PathMaker:
    """File-path conventions for the harness.

    All paths are relative to the benchmark/ working directory unless
    noted otherwise.
    """

    # ---- Repo layout (relative to benchmark/) ----

    @staticmethod
    def repo_root():
        return _REPO_ROOT

    @staticmethod
    def gen_conf_script():
        return join(_REPO_ROOT, 'scripts', 'gen_conf.py')

    @staticmethod
    def keygen_bin():
        return join(_REPO_ROOT, 'hotstuff-keygen')

    @staticmethod
    def tls_keygen_bin():
        return join(_REPO_ROOT, 'hotstuff-tls-keygen')

    @staticmethod
    def replica_bin():
        return join(_REPO_ROOT, 'examples', 'hotstuff-app')

    @staticmethod
    def client_bin():
        return join(_REPO_ROOT, 'examples', 'hotstuff-client')

    # ---- Generated config artefacts (local on orchestrator) ----

    @staticmethod
    def conf_prefix():
        # MUST be 'hotstuff' so the generated main conf is literally
        # 'hotstuff.conf'. examples/hotstuff_app.cpp and hotstuff_client.cpp
        # hardcode `Config config("hotstuff.conf")` as the primary conf
        # name salticidae loads from cwd; `--conf <file>` only adds an
        # extra. With any other prefix, replicas never see the
        # `replica = ...` list and crash with "replica idx out of range".
        return 'hotstuff'

    @staticmethod
    def main_conf_file():
        return f'{PathMaker.conf_prefix()}.conf'

    @staticmethod
    def replica_conf_file(i):
        assert isinstance(i, int) and i >= 0
        return f'{PathMaker.conf_prefix()}-sec{i}.conf'

    @staticmethod
    def nodes_file():
        return 'nodes.txt'

    # ---- Remote-side filenames (used by tmux launchers + scp) ----

    @staticmethod
    def remote_main_conf():
        return PathMaker.main_conf_file()

    @staticmethod
    def remote_replica_conf(i):
        return PathMaker.replica_conf_file(i)

    # ---- Local log + result directories ----

    @staticmethod
    def logs_path():
        return 'logs'

    @staticmethod
    def results_path():
        return 'results'

    @staticmethod
    def replica_log_file(i):
        assert isinstance(i, int) and i >= 0
        return join(PathMaker.logs_path(), f'replica-{i}.log')

    @staticmethod
    def client_log_file(c):
        assert isinstance(c, int) and c >= 0
        return join(PathMaker.logs_path(), f'client-{c}.log')

    @staticmethod
    def run_logs_path():
        return join(PathMaker.results_path(), 'run_logs')


class Color:
    HEADER = '\033[95m'
    OK_BLUE = '\033[94m'
    OK_GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class Print:
    @staticmethod
    def heading(message):
        assert isinstance(message, str)
        print(f'{Color.OK_GREEN}{message}{Color.END}')

    @staticmethod
    def info(message):
        assert isinstance(message, str)
        print(message)

    @staticmethod
    def warn(message):
        assert isinstance(message, str)
        print(f'{Color.BOLD}{Color.WARNING}WARN{Color.END}: {message}')

    @staticmethod
    def error(e):
        assert isinstance(e, BenchError)
        print(f'\n{Color.BOLD}{Color.FAIL}ERROR{Color.END}: {e}\n')
        causes, current_cause = [], e.cause
        while isinstance(current_cause, BenchError):
            causes += [f'  {len(causes)}: {e.cause}\n']
            current_cause = current_cause.cause
        causes += [f'  {len(causes)}: {type(current_cause)}\n']
        causes += [f'  {len(causes)}: {current_cause}\n']
        print(f'Caused by: \n{"".join(causes)}\n')


def progress_bar(iterable, prefix='', suffix='', decimals=1, length=30,
                 fill='█', print_end='\r'):
    total = len(iterable)
    if total == 0:
        return

    def _draw(iteration):
        formatter = '{0:.' + str(decimals) + 'f}'
        percent = formatter.format(100 * (iteration / float(total)))
        filled = int(length * iteration // total)
        bar = fill * filled + '-' * (length - filled)
        print(f'\r{prefix} |{bar}| {percent}% {suffix}', end=print_end)

    _draw(0)
    for i, item in enumerate(iterable):
        yield item
        _draw(i + 1)
    print()
