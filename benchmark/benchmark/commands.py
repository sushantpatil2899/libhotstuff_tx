"""Shell command strings for the CloudLab harness.

Every method returns a shell string the harness sends to a remote host
via Fabric (or runs locally for config generation). Centralising them
here keeps remote.py focused on orchestration rather than escaping
quirks.
"""
from os.path import join

from benchmark.utils import PathMaker


class CommandMaker:

    # ---------- Environment / build ----------

    @staticmethod
    def apt_install():
        """Install everything needed to build libhotstuff + secp256k1.

        - ``build-essential cmake``: C++ toolchain + CMake (>= 3.9 required).
        - ``libssl-dev libuv1-dev``: declared in the upstream README.
        - ``autoconf automake libtool pkg-config``: secp256k1 is built as
          an ExternalProject via autogen.sh / configure / make, so the
          autotools stack must be present.
        - ``git tmux``: clone the repo + background the replica/client
          processes the same way Narwhal does.
        - ``python3 python3-pip``: scripts/gen_conf.py is Python.
        """
        return (
            'sudo apt-get update && '
            'sudo apt-get -y install '
            'build-essential cmake '
            'libssl-dev libuv1-dev '
            'autoconf automake libtool pkg-config '
            'git tmux python3 python3-pip'
        )

    @staticmethod
    def clone(repo_url, repo_name):
        """Clone the repo if absent, otherwise fetch+reset to remote master."""
        assert isinstance(repo_url, str)
        assert isinstance(repo_name, str)
        return (
            f'(test -d {repo_name}/.git || git clone {repo_url} {repo_name})'
        )

    @staticmethod
    def submodule_update(repo_name):
        """Initialise + update all submodules (secp256k1, salticidae, minirun)."""
        assert isinstance(repo_name, str)
        return (
            f'(cd {repo_name} && git submodule update --init --recursive)'
        )

    @staticmethod
    def git_sync(repo_name, branch):
        """Pull the latest commit on ``branch``. Hard reset to remote so a
        stale local change never blocks a rerun."""
        assert isinstance(repo_name, str)
        assert isinstance(branch, str)
        return (
            f'(cd {repo_name} && git fetch -f && '
            f'git checkout -f {branch} -- && '
            f'git reset --hard origin/{branch} && '
            f'git submodule update --init --recursive)'
        )

    @staticmethod
    def cmake_configure(repo_name, *, benchmark=True, normal_log=False,
                        proto_log=False, two_step=False):
        """Run cmake in the repo root.

        ``benchmark=True`` enables ``HOTSTUFF_ENABLE_BENCHMARK`` which is
        what makes the client emit the per-command timestamp lines we
        parse in logs.py — required for meaningful results.

        ``normal_log=False`` disables the default per-event INFO logs on
        replicas. They would otherwise tank performance under load.

        ``two_step`` switches the safety rule from 3-chain to 2-chain.
        Default off (matches upstream).
        """
        flags = []
        flags.append('-DCMAKE_BUILD_TYPE=Release')
        flags.append(f'-DHOTSTUFF_NORMAL_LOG={"ON" if normal_log else "OFF"}')
        flags.append(f'-DHOTSTUFF_PROTO_LOG={"ON" if proto_log else "OFF"}')
        flags.append(f'-DHOTSTUFF_TWO_STEP={"ON" if two_step else "OFF"}')
        # CMAKE_CXX_FLAGS carries two things:
        #   - "-include cstdint": GCC 13+ (Ubuntu 24.04) no longer transitively
        #     pulls <cstdint> into salticidae/ref.h, which references
        #     std::uint8_t. Forcing the include avoids patching the submodule.
        #   - "-DHOTSTUFF_ENABLE_BENCHMARK": this macro is NOT a CMake option
        #     and is NOT wired through src/config.h.in. It's only #ifdef'd in
        #     examples/hotstuff_client.cpp + hotstuff_app.cpp. Setting it as a
        #     compiler define is the only way to enable per-command latency
        #     emission that logs.py parses.
        cxx_extra = ['-include cstdint']
        if benchmark:
            cxx_extra.append('-DHOTSTUFF_ENABLE_BENCHMARK')
        flags.append(f'"-DCMAKE_CXX_FLAGS={" ".join(cxx_extra)}"')
        flag_str = ' '.join(flags)
        return f'(cd {repo_name} && cmake {flag_str} .)'

    @staticmethod
    def make(repo_name, jobs=None):
        """Build all targets (libhotstuff, examples, hotstuff-keygen,
        hotstuff-tls-keygen)."""
        assert isinstance(repo_name, str)
        j = f' -j{int(jobs)}' if jobs else ''
        return f'(cd {repo_name} && make{j})'

    # ---------- Per-run config generation (local on orchestrator) ----------

    @staticmethod
    def gen_conf(repo_name, *, ips_file, prefix, block_size, pace_maker,
                 nworker, repnworker, clinworker, repburst, cliburst,
                 pport=10000, cport=20000,
                 sb_users=1000, sb_prob_choose_mtx=0.9, sb_skew_factor=0.1):
        """Invoke ``scripts/gen_conf.py`` on the orchestrator to produce
        ``<prefix>.conf`` + per-replica ``<prefix>-sec<i>.conf`` files.

        Caller is responsible for writing ``ips_file`` (one IP per line,
        in replica-index order) before calling this. ``repo_name`` is the
        path to the local libhotstuff checkout (so the script can find
        the keygen binaries built by ``make``).

        The three ``sb_*`` args are SmallBank workload parameters. They
        land as ``sb-users`` / ``sb-prob-choose_mtx`` / ``sb-skew-factor``
        lines in the generated ``<prefix>.conf`` — which both
        ``hotstuff-app`` and ``hotstuff-client`` load automatically as
        their hardcoded default conf file (see ``PathMaker.conf_prefix``),
        so no extra CLI flag is needed at launch time on either side.
        """
        return (
            f'python3 {join(repo_name, "scripts", "gen_conf.py")} '
            f'--prefix {prefix} '
            f'--ips {ips_file} '
            f'--keygen {join(repo_name, "hotstuff-keygen")} '
            f'--tls-keygen {join(repo_name, "hotstuff-tls-keygen")} '
            f'--block-size {int(block_size)} '
            f'--pace-maker {pace_maker} '
            f'--nworker {int(nworker)} '
            f'--repnworker {int(repnworker)} '
            f'--clinworker {int(clinworker)} '
            f'--repburst {int(repburst)} '
            f'--cliburst {int(cliburst)} '
            f'--pport {int(pport)} '
            f'--cport {int(cport)} '
            f'--sb-users {int(sb_users)} '
            f'--sb-prob-choose_mtx {float(sb_prob_choose_mtx)} '
            f'--sb-skew-factor {float(sb_skew_factor)}'
        )

    # ---------- Per-run launch + teardown (on remote hosts) ----------

    @staticmethod
    def run_replica(repo_dir, conf_file, *, max_rep_msg=None,
                    max_cli_msg=None):
        """Launch a single ``hotstuff-app`` replica from $HOME.

        Configs are scp'd into the remote ``$HOME`` (Fabric default), so
        we invoke the binary by its repo-relative path and reference the
        conf by basename. We do not ``cd`` into the repo, otherwise the
        conf would have to be uploaded there.

        Wrapped in ``bash -lc 'ulimit -s unlimited && ...'`` because the
        bootstrapping replica can build a deep promise-resolution chain
        that overflows the default 8 MiB stack — same workaround as in
        ``scripts/run_demo.sh``.
        """
        extra = ''
        if max_rep_msg is not None:
            extra += f' --max-rep-msg {int(max_rep_msg)}'
        if max_cli_msg is not None:
            extra += f' --max-cli-msg {int(max_cli_msg)}'
        bin_path = join(repo_dir, 'examples', 'hotstuff-app')
        return (
            f"bash -lc 'ulimit -s unlimited && "
            f"./{bin_path} --conf {conf_file}{extra}'"
        )

    @staticmethod
    def run_client(repo_dir, conf_file, *, cid, iter_count, max_async,
                   max_cli_msg=None):
        """Launch one ``hotstuff-client`` process from $HOME.

        Same conf placement convention as ``run_replica``. ``iter_count``
        of ``-1`` means run forever — the harness kills it after
        ``duration`` seconds. ``cid`` must be unique across concurrent
        clients or commands collide on hash.
        """
        extra = ''
        if max_cli_msg is not None:
            extra += f' --max-cli-msg {int(max_cli_msg)}'
        bin_path = join(repo_dir, 'examples', 'hotstuff-client')
        return (
            f"bash -lc './{bin_path} --conf {conf_file} "
            f"--cid {int(cid)} --iter {int(iter_count)} "
            f"--max-async {int(max_async)}{extra}'"
        )

    @staticmethod
    def kill():
        """Stop every libhotstuff process on this host.

        The client buffers per-command latency samples in memory and only
        flushes them to stderr when its salticidae SigEvent for SIGINT /
        SIGTERM runs the shutdown lambda. So we send SIGTERM first, give
        the binaries time to flush their buffers, then SIGKILL anything
        still alive as a safety net. PID files left by ``_background_run``
        get swept here.
        """
        return (
            'pkill -SIGTERM -x hotstuff-client 2>/dev/null; '
            'pkill -SIGTERM -x hotstuff-app 2>/dev/null; '
            'sleep 2; '
            'pkill -SIGKILL -x hotstuff-client 2>/dev/null; '
            'pkill -SIGKILL -x hotstuff-app 2>/dev/null; '
            'rm -f /tmp/hotstuff_pid_* 2>/dev/null; '
            'true'
        )

    @staticmethod
    def cleanup():
        """Wipe generated config artefacts from a remote host's home dir.

        Run before scp-ing fresh configs for a new experiment row.
        """
        return (
            f'rm -f {PathMaker.main_conf_file()} '
            f'{PathMaker.conf_prefix()}-sec*.conf {PathMaker.nodes_file()}'
        )

    @staticmethod
    def clean_logs():
        """Wipe the per-host logs dir."""
        return f'rm -rf {PathMaker.logs_path()} && mkdir -p {PathMaker.logs_path()}'
