#!/usr/bin/env bash
# cloudlab_bootstrap.sh
#
# One-shot bootstrap for a fresh CloudLab experiment. Run ON THE
# ORCHESTRATOR node after these manual prerequisites:
#
#   1. From your laptop, scp your private SSH key to the orchestrator:
#        scp ~/.ssh/id_ed25519 <user>@<orch>.<cluster>.cloudlab.us:~/.ssh/id_ed25519
#        ssh <user>@<orch>.<cluster>.cloudlab.us 'chmod 600 ~/.ssh/id_ed25519'
#   2. ssh into the orchestrator and clone the repo:
#        git clone <repo-url> ~/libhotstuff
#   3. Download manifest.xml from the CloudLab portal (Experiment ->
#      Manifest tab) and copy it to benchmark/manifest.xml on the
#      orchestrator.
#   4. Fill in benchmark/settings.json (cloudlab.username, repo.url,
#      repo.branch).
#
# Then:
#   sudo apt-get update && sudo apt-get install -y python3-pip git
#   cd ~/libhotstuff/benchmark
#   bash scripts/cloudlab_bootstrap.sh
#
# Idempotent. Re-run safely if a step fails.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BENCH_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
cd "${BENCH_DIR}"

MANIFEST="${BENCH_DIR}/manifest.xml"
SETTINGS="${BENCH_DIR}/settings.json"
KEY="${HOME}/.ssh/id_ed25519"

# ---------- Preflight ----------

if [[ ! -f "${MANIFEST}" ]]; then
    echo "ERROR: ${MANIFEST} not found." >&2
    echo "       Download from the CloudLab portal (Experiment -> Manifest)." >&2
    exit 1
fi
if [[ ! -f "${SETTINGS}" ]]; then
    echo "ERROR: ${SETTINGS} not found." >&2
    exit 1
fi
if [[ ! -f "${KEY}" ]]; then
    echo "ERROR: ${KEY} not found." >&2
    echo "       scp it from your laptop first (see header of this script)." >&2
    exit 1
fi

# ---------- 1/6  PATH ----------

echo "==> [1/6] Ensuring ~/.local/bin is on PATH"
if ! grep -qs '\$HOME/.local/bin' "${HOME}/.bashrc"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
fi
export PATH="${HOME}/.local/bin:${PATH}"

# ---------- 2/6  Python deps ----------

echo "==> [2/6] Installing Python deps (fabric, invoke, paramiko)"
# --break-system-packages is required on Ubuntu 24.04 PEP 668 envs.
# --user keeps everything under ~/.local so we never need sudo.
pip3 install --quiet --break-system-packages --user -r requirements.txt
hash -r
if ! command -v fab >/dev/null 2>&1; then
    echo "ERROR: 'fab' still not on PATH after pip install." >&2
    echo "       Check 'python3 -m pip show fabric' and verify Location." >&2
    exit 1
fi

# ---------- 3/6  Parse manifest ----------

echo "==> [3/6] Discovering replica hostnames from manifest.xml"
HOSTS=$(python3 - <<'PY'
from benchmark.manifest import Manifest
m = Manifest.load("manifest.xml")
print("\n".join(m.hostnames))
PY
)
USERNAME=$(python3 - <<'PY'
import json
with open("settings.json") as f:
    print(json.load(f)["cloudlab"]["username"])
PY
)

echo "    user:    ${USERNAME}"
echo "    hosts:"
printf '             %s\n' ${HOSTS}

# ---------- 4/6  Orchestrator known_hosts ----------

echo "==> [4/6] Pre-trusting github.com + replicas on this orchestrator"
mkdir -p "${HOME}/.ssh"
touch "${HOME}/.ssh/known_hosts"
chmod 600 "${HOME}/.ssh/known_hosts"
ssh-keyscan -t ed25519,rsa github.com 2>/dev/null >> "${HOME}/.ssh/known_hosts" || true
for h in ${HOSTS}; do
    ssh-keyscan -t ed25519,rsa "${h}" 2>/dev/null >> "${HOME}/.ssh/known_hosts" || true
done
sort -u "${HOME}/.ssh/known_hosts" -o "${HOME}/.ssh/known_hosts"

# ---------- 5/6  Per-replica SSH key + known_hosts ----------

echo "==> [5/6] Pushing SSH key + github trust to every replica"
# CloudLab sets the local hostname to the manifest alias (node0..node4)
# but manifest.hostnames returns physical hardware names (e.g. amd243).
# Comparing hostnames doesn't work — resolve each to an IP instead.
LOCAL_IPS=$(hostname -I 2>/dev/null | tr ' ' '\n' | sort -u)
is_self() {
    local host_ip
    host_ip=$(getent hosts "$1" 2>/dev/null | awk '{print $1}' | head -1)
    [[ -n "${host_ip}" ]] && grep -qx "${host_ip}" <<<"${LOCAL_IPS}"
}

for h in ${HOSTS}; do
    echo "    -> ${h}"
    if is_self "${h}"; then
        echo "       (orchestrator, skipping)"
        continue
    fi
    if ! ssh -o BatchMode=yes -o ConnectTimeout=10 \
         -o StrictHostKeyChecking=accept-new \
         "${USERNAME}@${h}" 'test -f ~/.ssh/id_ed25519' 2>/dev/null; then
        scp -q -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
            "${KEY}" "${USERNAME}@${h}:~/.ssh/id_ed25519"
    fi
    ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
        "${USERNAME}@${h}" '
        chmod 600 ~/.ssh/id_ed25519
        mkdir -p ~/.ssh && touch ~/.ssh/known_hosts && chmod 600 ~/.ssh/known_hosts
        ssh-keyscan -t ed25519,rsa github.com 2>/dev/null >> ~/.ssh/known_hosts
        sort -u ~/.ssh/known_hosts -o ~/.ssh/known_hosts
    '
done

# ---------- 6/6  Sanity ----------

echo "==> [6/6] Sanity check — passwordless SSH + git reachability"
for h in ${HOSTS}; do
    if is_self "${h}"; then continue; fi
    printf '    %s ssh:    ' "${h}"
    ssh -o BatchMode=yes -o ConnectTimeout=5 "${USERNAME}@${h}" 'echo OK' \
        || { echo "FAIL"; exit 1; }
    printf '    %s github: ' "${h}"
    ssh -o BatchMode=yes "${USERNAME}@${h}" \
        'ssh -o BatchMode=yes -o ConnectTimeout=5 -T git@github.com 2>&1 | grep -q "successfully authenticated" && echo OK || echo FAIL'
done

cat <<MSG

Bootstrap complete. Next steps:

  fab install-cloudlab        # build libhotstuff on every node (~5-10 min)
  fab experiment-cloudlab     # run the CSV-driven sweep
  fab parser-daemon           # in a second screen window

If 'fab install-cloudlab' ever fails after a code change that touches
build flags, wipe the stale CMake cache on every replica before retrying:

  for h in $(python3 -c 'from benchmark.manifest import Manifest; print(" ".join(Manifest.load("manifest.xml").hostnames))'); do
      ssh "${USERNAME}@\$h" 'rm -f ~/libhotstuff/CMakeCache.txt && rm -rf ~/libhotstuff/CMakeFiles'
  done

MSG
