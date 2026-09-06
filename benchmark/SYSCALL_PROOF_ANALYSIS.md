# Does sendto() scale with commits or with rounds? Direct measurement.

Follow-up to a fair challenge: the earlier claim that "network-send
syscalls are per-command" was inferred from reading source code
(`client_request_cmd_handler` registered per `MsgReqCmd`, response
dequeued one command at a time), not measured. Inference from source
code is not proof of runtime behavior. This settles it with actual
counts.

## Method

For each of 5 (block_size, max_async) combinations — chosen at
extremes plus the recommended baseline — `strace_probe.py`:

1. Boots 4 replicas + 1 client directly (bypassing the CSV row loop,
   which has no hook for precisely-timed mid-run instrumentation).
2. Lets load stabilize for 15s.
3. Attaches `strace -c -f -U calls,name -p <leader-pid>` to the leader
   for exactly 30 wall-clock seconds, giving an **exact count** of
   every syscall the leader made in that window (`sendto` specifically,
   since that's the flagged one).
4. Independently counts commits from the client's timestamped log
   (`[hotstuff info] <latency>` lines, one per committed command) whose
   timestamp falls inside that same 30-second window — ground truth
   for how many commands were actually committed, read directly off
   the client's own clock, not derived from the (possibly
   strace-slowed) leader.
5. Both clocks are on the same CloudLab LAN with `chronyd` running
   (confirmed running via `ps` earlier); window start/end are read
   directly from the client's own `date` command to sidestep any
   timezone mismatch entirely (its clock displays MDT, not UTC — this
   was caught and fixed during the first run, which had wrongly shown
   0 commits before the fix).

## Result

| run | block_size | max_async | sendto (30s window) | commits (30s window) | implied rounds | **sendto/commit** | sendto/round |
|---|---:|---:|---:|---:|---:|---:|---:|
| bs100_ma8000 | 100 | 8000 | 821,407 | 784,197 | 7,842 | **1.047** | 104.7 |
| bs3200_ma8000 | 3200 | 8000 | 701,312 | 758,394 | 237 | **0.925** | 2,959.1 |
| bs100_ma100 | 100 | 100 | 1,133,266 | 1,012,381 | 10,124 | **1.119** | 111.9 |
| bs3200_ma100 | 3200 | 100 | 1,318,440 | 1,053,566 | 329 | **1.251** | 4,005.0 |
| bs200_ma600 | 200 | 600 | 1,036,795 | 857,890 | 4,289 | **1.209** | 241.7 |

**`sendto` per commit stays in a tight band (0.92-1.25) across a 32x
range of block_size and an 80x range of max_async.** `sendto` per
round, by contrast, ranges from 104.7 to 4,005 — a 38x spread that
tracks block_size almost exactly (block_size 100 → ~105-112;
block_size 200 → ~242; block_size 3200 → ~2,959-4,005; each roughly
`(sendto/commit) x block_size`, as expected if sendto count depends on
commits and is essentially independent of round count).

This is now **directly counted, not inferred**: the leader's dominant
network-send syscall traffic tracks the number of committed commands,
not the number of consensus rounds. Bundling more commands into fewer,
bigger rounds does not reduce this traffic — it stays pinned at
roughly one send per commit regardless of how those commits are
grouped into blocks. That is the concrete, measured reason `block_size`
cannot move the throughput ceiling: the dominant per-unit cost this
sweep can find is denominated in commits, and no block-size choice
changes the number of commits you need to send responses for.

## What this does and doesn't establish

- **Established**: the *count* of `sendto` calls scales with commits,
  not rounds, at these 5 points, spanning the full range this session
  tested. This directly falsifies the alternative hypothesis (sendto
  scales with rounds) — if it were true, sendto/round would have
  stayed roughly constant and sendto/commit would have scaled inversely
  with block_size, which is not what happened.
- **Not established**: this doesn't identify *which* code path
  generates that one-ish sendto per commit (client response vs. some
  other per-command message), or explain the 0.92-1.25 spread's own
  variance — the call-graph tooling needed for that (reliable perf
  unwinding, or targeted strace -e trace=network with source
  correlation) wasn't part of this measurement. What it settles is the
  question actually in dispute: per-command, not per-round.

Raw strace summaries and the exact client log slices used for each
count are saved under `results/strace/` for independent verification.
