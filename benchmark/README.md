# libhotstuff CloudLab benchmark harness

CSV-driven runner that drives libhotstuff benchmarks across a CloudLab
experiment. One row in `experiments.csv` = one experiment row; the
runner generates configs, launches replicas + clients over SSH, captures
logs, and writes throughput / latency to the output CSV.

## Layout

```
benchmark/
├── benchmark/          Python package
│   ├── commands.py     shell-command builders for remote + local steps
│   ├── config.py       BenchParameters / ProtocolParameters schemas
│   ├── csv_writer.py   flock-protected CSV append
│   ├── instance.py     CloudLabInstanceManager (manifest-backed)
│   ├── logs.py         libhotstuff client-stderr parser
│   ├── manifest.py     parses CloudLab GENI rspec XML
│   ├── notifier.py     throttled email notifier (optional)
│   ├── parser_daemon.py async log parser (separate screen window)
│   ├── reconciler.py   promotes DOWNLOADED rows to OK
│   ├── remote.py       CloudLabBench orchestrator
│   ├── retry.py        retry decorator for transient SSH errors
│   ├── settings.py     loads settings.json
│   └── utils.py        PathMaker + Print + progress_bar
├── fabfile.py          fab task surface
├── manifest.xml        downloaded from CloudLab portal (you provide)
├── settings.json       repo URL + username (you fill in)
├── experiments.csv     input — sample sweep across test parameters
├── notifier.example.json  template for ~/.hotstuff_notifier.json
├── requirements.txt    fabric, invoke, paramiko
├── logs/               per-run logs (transient)
└── results/
    ├── experiment_results.csv  output (created by run)
    └── run_logs/<run_id>/      archived per-run logs + meta.json / READY
                                 / metrics.json / result.txt
```

## Test parameter set

Bench parameters (how each run is executed):

| Column         | Default | Meaning                                            |
|----------------|---------|----------------------------------------------------|
| `run_id`       | required | unique label; lets the runner skip completed rows |
| `nodes`        | 4       | replica count (BFT minimum 4)                     |
| `num_clients`  | required | `hotstuff-client` processes to launch             |
| `iter_count`   | -1      | per-client `--iter`; -1 = run forever              |
| `max_async`    | required | per-client `--max-async` (offered-load knob)      |
| `duration`     | 60      | seconds before tmux kill                          |

Protocol parameters (written into `hotstuff.conf` via `scripts/gen_conf.py`):

| Column         | Default     | Meaning                                |
|----------------|-------------|----------------------------------------|
| `block_size`   | 400         | commands batched per block             |
| `pace_maker`   | rr          | round-robin or `dummy`                 |
| `nworker`      | 4           | signature-verification threads         |
| `repnworker`   | 4           | replica-network I/O threads            |
| `clinworker`   | 4           | client-network I/O threads             |
| `repburst`     | 1000        | replica-network burst size             |
| `cliburst`     | 1000        | client-network burst size              |
| `max_rep_msg`  | 4194304     | max inter-replica message size (bytes) |
| `max_cli_msg`  | 65536       | max client message size (bytes)        |

Any column omitted from the CSV falls back to the default. Build-time
flags (HOTSTUFF_ENABLE_BENCHMARK, HOTSTUFF_NORMAL_LOG, HOTSTUFF_TWO_STEP)
are not runtime parameters — they're set by `install_cloudlab`.

## Result columns

The runner appends these to each row of the output CSV:

| Column                | Meaning                                       |
|-----------------------|-----------------------------------------------|
| `tps`                 | commits / second across all clients           |
| `latency_ms_mean`     | mean per-command latency                      |
| `latency_ms_p50/95/99`| order statistics                              |
| `duration_s`          | union wall window across client samples       |
| `n_committed`         | total commit-line count                       |
| `n_clients`           | number of client logs parsed                  |
| `n_replicas_booted`   | replicas that emitted the boot marker         |
| `status`              | `OK` / `DOWNLOADED` / `PARAM_ERROR: …` / etc. |

Rows are written with `status=DOWNLOADED` as soon as logs are collected;
the parser daemon later promotes them to `OK` and fills metric columns.

## Usage

```bash
# One-time per CloudLab experiment:
#   - download manifest.xml from the CloudLab portal
#   - edit settings.json (cloudlab.username, repo URL, branch)
#   - on the orchestrator, install Python deps and rust:
pip3 install -r requirements.txt

# Build libhotstuff on every node:
fab install-cloudlab

# In one screen window, run the experiments:
fab experiment-cloudlab \
    --input-csv=experiments.csv \
    --output-csv=results/experiment_results.csv

# In a second screen window, parse logs asynchronously as they finish:
fab parser-daemon \
    --csv-path=results/experiment_results.csv

# Look at one run's parsed result.txt for sanity:
fab logs --run-id=E0_baseline
```

## Status semantics

| Status             | Meaning                                                    |
|--------------------|------------------------------------------------------------|
| `OK`               | logs parsed, metric columns filled                         |
| `DOWNLOADED`       | logs in `results/run_logs/<run_id>/`, parser will pick up  |
| `PARAM_ERROR: …`   | CSV row failed validation; never executed                  |
| `NOT_ENOUGH_NODES` | manifest has fewer nodes than `nodes` requires             |
| `CONFIG_ERROR: …`  | gen_conf.py failed or scp upload failed                    |
| `RUN_ERROR: …`     | runtime failure during execution; logs may be partial      |
| `PARSE_ERROR: …`   | parser saw the dir but couldn't extract metrics            |

A re-run of `fab experiment-cloudlab` skips any row whose status is
`OK` or `DOWNLOADED`, so interrupted sweeps resume cleanly.

## Topology assumptions

`_select_hosts` takes the first `nodes` entries from manifest.xml as
replicas; any extras become dedicated client hosts (unless
`collocate_client=true` in the row, which falls back to one client per
replica machine). For single-site CloudLab experiments, replica-to-
replica traffic uses the experiment LAN private IPs; for multi-site
experiments the harness automatically switches to public hostnames
because private IPs are not routable across CloudLab aggregates.
