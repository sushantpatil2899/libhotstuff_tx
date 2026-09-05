#!/usr/bin/env bash
# clean_remote_build.sh
#
# Wipe stale CMake state on every replica. Use whenever you change build
# flags in benchmark/benchmark/commands.py — cmake reuses CMakeCache.txt
# even when the command line changes, so new flags are silently ignored.
#
#   bash scripts/clean_remote_build.sh
#
# Add --hard to also delete the whole libhotstuff/ tree on each replica
# (forces a fresh git clone on the next `fab install-cloudlab`).
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BENCH_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
cd "${BENCH_DIR}"

MODE="cache"
if [[ "${1:-}" == "--hard" ]]; then MODE="hard"; fi

USERNAME=$(python3 - <<'PY'
import json
with open("settings.json") as f:
    print(json.load(f)["cloudlab"]["username"])
PY
)
HOSTS=$(python3 - <<'PY'
from benchmark.manifest import Manifest
print("\n".join(Manifest.load("manifest.xml").hostnames))
PY
)

# CloudLab sets the local hostname to the manifest alias (node0..node4)
# but manifest.hostnames returns physical hardware names (e.g. amd243).
# Comparing hostnames doesn't work. Resolve each manifest name to an IP
# and check against our local IPs to detect self.
LOCAL_IPS=$(hostname -I 2>/dev/null | tr ' ' '\n' | sort -u)
is_self() {
    local host_ip
    host_ip=$(getent hosts "$1" 2>/dev/null | awk '{print $1}' | head -1)
    [[ -n "${host_ip}" ]] && grep -qx "${host_ip}" <<<"${LOCAL_IPS}"
}

# `make clean` deletes the .o files — without it, an incremental rebuild
# silently skips recompilation when only CXX_FLAGS changed, and the old
# binary (without the new -D defines) survives.
REMOTE_CMD='(cd ~/libhotstuff && (make clean 2>/dev/null || true) && rm -f CMakeCache.txt && find . -name CMakeFiles -prune -exec rm -rf {} + 2>/dev/null; true)'
[[ "${MODE}" == "hard" ]] && REMOTE_CMD='rm -rf ~/libhotstuff'
LABEL='cleaned build (.o + CMake state)'
[[ "${MODE}" == "hard" ]] && LABEL='wiped'

for h in ${HOSTS}; do
    printf '%-50s ' "${h}"
    if is_self "${h}"; then
        bash -c "${REMOTE_CMD}" && echo "${LABEL} (local)"
    else
        ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
            "${USERNAME}@${h}" "${REMOTE_CMD}" \
            && echo "${LABEL}"
    fi
done
