# SmallBank saturation study — run plan

Adapted from an earlier (pre-SmallBank) Fabric harness for this exact
kind of sweep. See `README.md` for the harness's general mechanics
(CSV schema, status semantics, topology assumptions) — this file is
just the sequence of phases for *this* study.

**Where this runs**: every command below runs from this laptop's local
checkout, not from any CloudLab node. `fab` drives all 5 manifest
hosts over SSH; node4 (the client host) runs nothing but the
`hotstuff-client` process itself, so it isn't sharing CPU/network with
the orchestration loop. Repo: `github.com/sushantpatil2899/libhotstuff_tx`
(a private fork — the original is Heena Nagda's and this session has
no write access there, so all pushes go here, not upstream).

## Fixed for the whole study

`nodes=4` (BFT f=1) · `pace_maker=dummy` · TLS off (harness never
turns it on) · `iter_count=-1` with `duration=60` (wall-clock window,
not a literal command count) · `collocate_client=false` (client runs
on the dedicated 5th manifest node, not co-located with a replica) ·
`sb_users=1000` · `repburst=1000`, `cliburst=1000` · `max_rep_msg`/
`max_cli_msg` at harness defaults (4 MiB / 64 KiB — SmallBank payloads
are tiny, never the bottleneck).

`sb_prob_choose_mtx` (0.9) and `sb_skew_factor` (0.1) stay at default
through Phase 0 and Phase 1 — they're deferred to Phase 2, after the
load/block-size knee is known, so they can be swept around that
anchor instead of blind.

Every phase below runs at **1 rep per config** to move fast today.
Once you know which configs actually matter (the knee, and whichever
thread config wins Phase 0), re-run just those specific rows with 2
more reps (`_r2`, `_r3` suffixes on `run_id`) for the numbers you'd
actually report.

## Phase 0 — thread calibration (`calibration.csv`, 8 runs)

Default threads (nworker=4, repnworker=4, clinworker=4) vs. scaled
(nworker=16, clinworker=16, repnworker=8 — headroom on the d6515's 32
cores), each probed at max_async ∈ {100, 400, 900, 1300}, block_size
fixed at 200.

```bash
fab install-cloudlab
fab experiment-cloudlab --input-csv=calibration.csv \
    --output-csv=results/calibration_results.csv
```

**Decision rule**: if the scaled config's tps is materially higher
(use the same ≥10% growth threshold their old harness used) at any
probed max_async, threads were under-provisioned — use the scaled
values for Phase 1. Otherwise keep defaults.

## Phase 1 — block_size × max_async grid (`main_grid.csv`, 40 runs)

Generate the grid with whichever thread config Phase 0 picked:

```bash
python3 make_grid_csv.py --out main_grid.csv \
    --nworker <winner> --repnworker <winner> --clinworker <winner>
fab experiment-cloudlab --input-csv=main_grid.csv \
    --output-csv=results/main_grid_results.csv
```

block_size ∈ {100, 200, 400, 800} × max_async ∈ {10, 25, 50, 100, 175,
250, 400, 600, 900, 1300}. This is the actual throughput/latency
saturation curve — plot tps and latency_ms_mean against max_async, one
line per block_size, and look for two things separately (per your
concern about false saturation, and per Phase 3's watch on client-side
saturation):

- **Throughput knee**: where tps stops growing with more offered load.
- **Latency knee**: where latency_ms_mean starts growing convexly —
  can occur *before* the throughput knee.
- **Does the knee move with block_size?** If yes, whichever block_size
  gives the highest-throughput knee is the real ceiling; a fixed wrong
  default would have under-reported it.

## Phase 2 — workload knobs (deferred until Phase 1 lands)

OFAT sweep of `sb_prob_choose_mtx` ∈ {0.1, 0.5, 0.9} and
`sb_skew_factor` ∈ {0, 0.5, 0.99}, each at 3 max_async points
bracketing whatever Phase 1's knee turned out to be (anchor − one
step, anchor, anchor + one step) — not a full re-sweep. Generate once
Phase 1's knee is known; not written yet.

## Phase 3 — client-side saturation check

At the max_async values near Phase 1's knee, watch whether the single
client machine (node4) is CPU-bound before the replicas are: sample
`mpstat`/`top` on node4 during the run and compare against replica-side
CPU. If node4 is pegged while replica CPU has headroom, throughput
plateaus are a client-host artifact — bump `num_clients` (multiple
processes on node4) and re-run at that max_async; if aggregate tps
rises, the earlier plateau was client-bound, not system saturation.
Keep raising `num_clients` until it stops helping — that point is your
real system ceiling, independent of client capacity.

## Local build (this laptop, macOS)

The orchestrator only needs `hotstuff-keygen`/`hotstuff-tls-keygen`
locally (for `gen_conf.py`) — `hotstuff-app`/`hotstuff-client` build
and run on the remote CloudLab nodes via `fab install-cloudlab`, not
here. Two macOS-only snags, already worked around in this checkout:

1. Homebrew keeps `openssl@3` and `libuv` out of the default include
   path. Export before configuring:
   ```bash
   export CPATH="$(pwd)/../.macos_compat:/opt/homebrew/opt/openssl@3/include:/opt/homebrew/opt/libuv/include"
   export LIBRARY_PATH="/opt/homebrew/opt/openssl@3/lib:/opt/homebrew/opt/libuv/lib"
   ```
2. `src/hotstuff_keygen.cpp`/`hotstuff_tls_keygen.cpp` use GNU
   `<error.h>`, which doesn't exist on macOS libc. `.macos_compat/error.h`
   (repo root, gitignored — never touches the tracked source, never
   seen by the Linux CloudLab build) shims the one function actually
   called. `CPATH` above must include that directory.

Then from the repo root: `cmake -DCMAKE_BUILD_TYPE=Release . && make
hotstuff-keygen hotstuff-tls-keygen`. Verified working (both binaries
run and the full `gen_conf.py` → `hotstuff.conf` + 4×`hotstuff-sec*.conf`
path was smoke-tested against `manifest.xml`'s real replica IPs).

## Notes carried over from the old harness

- **FD leak**: Fabric hit `[Errno 24] Too many open files` after ~100
  rows in one long sweep before. If a phase run dies with that error,
  `ulimit -n 4096` and re-run the same `fab experiment-cloudlab`
  command — it skips rows already marked `OK`/`DOWNLOADED`.
- **Orchestrator is this laptop, not node4.** `fab` runs locally here
  and drives all 5 CloudLab nodes over SSH; `collocate_client=false`
  routes every `hotstuff-client` process to node4 (manifest index 4),
  which then runs nothing but that client process — no SSH/Fabric
  overhead competing with it locally, so a client-saturation reading
  on node4 isn't contaminated by the harness's own control-plane
  traffic. `_REPO_ROOT` in `utils.py` resolves automatically from this
  file's own location, so `gen_conf.py` and the local keygen binaries
  are found in this checkout without any path configuration — this
  checkout just needs to be built once (`cmake . && make`) so
  `hotstuff-keygen`/`hotstuff-tls-keygen` exist at the repo root.
- `manifest.xml` here is trimmed from what CloudLab exports: the
  encrypted `<emulab:password>` RPC token, `<rspec_tour>`, and
  `<data_set>` blocks were dropped — `manifest.py` only reads `<node>`/
  `<link>` elements, so nothing functional was lost, and it keeps a
  credential-shaped blob out of a file this plan commits to git.
