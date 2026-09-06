# Leader CPU profile — correcting the "single thread" claim, finding the real cost

## Correction to the earlier finding

Earlier sessions today sampled leader/follower CPU with `ps -eo pid,%cpu`
and saw ~100-120%, concluding "a single thread is saturating one core."
That conclusion was wrong in its mechanism. `ps -eo %cpu` for a
multi-threaded process reports the **sum across all its threads**, not
one thread's usage. A proper per-thread breakdown
(`ps -eLo tid,%cpu,psr,comm`) during a max_async=8000 run shows the
opposite of "one thread maxed out":

| tid | %cpu | core (psr) |
|---:|---:|---:|
| 54176 (main) | 15.7% | 51 |
| 54211 | 11.9% | 12 |
| 54207 | 9.8% | 29 |
| 54208 | 9.6% | 4 |
| 54212 | 7.8% | 24 |
| 54188 | 4.4% | 16 |
| 54187 | 3.4% | 17 |
| 54194 | 2.9% | 48 |
| 54186 | 2.5% | 18 |
| 54196, 54195 | 1.7% each | 14, 62 |
| 54185 | 1.0% | 19 |

Twelve active threads, each on a **different physical core**, none
above 16%. Work is already spread across cores. The process's total
CPU consumption (summing these) is roughly 0.7-1.2 cores' worth — not
one core maxed, just under one core's worth of *total* demand spread
thin. This is why scaling `nworker`/`repnworker`/`clinworker` (Phase 0,
and the 96-run combined sweep) did nothing: there was never a
CPU-starved thread waiting for more workers. The ceiling isn't a
parallelism problem.

## What `perf record` actually shows

40s CPU profile (`perf record -F 99 -p <leader-pid> -g`, 5,086 samples)
during a sustained max_async=8000 run. Self-time by shared object:

| Component | Self time | What it is |
|---|---:|---|
| `[kernel.kallsyms]` | 41.45% | Syscalls, TCP/IP stack, NIC interrupt handling, epoll |
| `hotstuff-app` (own code) | 28.68% | Includes secp256k1 crypto (statically linked), message dispatch |
| `libc.so.6` | 22.60% | Mostly `malloc`/`cfree`/`operator new` — heap churn |
| `libstdc++.so.6` | 3.47% | C++ runtime (allocation, exceptions) |
| `libcrypto.so.3` / `libssl.so.3` | 2.75% / 0.17% | OpenSSL (TLS is off, so this is minimal — most crypto is the statically-linked secp256k1 below) |
| `libuv.so.1` | 0.82% | Event loop itself — barely shows up |

Flat leaf-function view, top individual costs:

| Function | Self % | Category |
|---|---:|---|
| `secp256k1_fe_mul_inner` | 6.23% | ECDSA field-arithmetic (signing/verification) |
| `secp256k1_fe_sqr_inner` | 4.27% | same |
| `cfree` | 3.67% | heap deallocation |
| `malloc` | 3.32% | heap allocation |
| `secp256k1_scalar_reduce_512` | 1.73% | ECDSA scalar math |
| `entry_SYSCALL_64` | 1.87% | syscall entry/exit overhead |
| `srso_return_thunk` + `srso_safe_ret` | 1.44% + 1.33% | **AMD SRSO (Speculative Return Stack Overflow) mitigation** — a kernel/microcode security tax on every function return, not application logic |
| `tcp_sendmsg_locked`, `__sys_sendto`, `tcp_write_xmit`, `ep_send_events`, `ep_poll_callback`, `mlx5_eq_comp_int` | ~0.5-1% each | network send/poll path |
| `HotStuffApp::client_request_cmd_handler`, `MsgNetwork::on_read`, `ConnPool::Conn::_send_data`, etc. | ~0.5-1% each | actual application message handling |

Rolling these up: **secp256k1 crypto ≈ 13%**, **heap
allocation/deallocation ≈ 9%**, **kernel networking/syscalls ≈ 9%** (plus
a long tail of smaller kernel symbols making up the rest of that 41.45%
DSO total), **SRSO mitigation tax ≈ 2.8%**, and only **~6%** is
identifiable HotStuff/salticidae application logic (dispatch,
deserialization). No SmallBank-specific symbol (e.g. transaction
execution) appears meaningfully in the profile — the workload's actual
banking logic is cheap; everything above it in the stack is not.

## Answer: can it use other cores instead of relying on one?

The premise needs correcting, but the underlying question — "why
doesn't more parallelism help" — has a real answer: **the process
already uses many cores (12+ threads, one core each); the problem is
that the total amount of work per message is small and dominated by
fixed per-message costs that don't get cheaper with more worker
threads.** Every command needs its own signature check (secp256k1),
its own heap allocations (fresh buffers per message), and its own
syscall (send its own response). Adding more `nworker`/`clinworker`
threads gives you more places to run these fixed-cost operations in
parallel, but doesn't reduce how many of them there are per command —
and since the aggregate demand is under 1 core's worth already, there
was never a queue of waiting work for extra threads to drain. This
also explains why `block_size` never mattered: batching more commands
into one consensus *round* doesn't reduce the number of per-command
signature checks, allocations, or client-response sends, which appear
to scale with command count, not round count.

**What would actually move the ceiling** (research directions, not
config flags):
1. **Reduce allocations per message** — reuse buffers instead of
   fresh `std::vector`/`operator new` per command (~9% of CPU).
2. **Batch syscalls** — coalesce multiple outgoing messages per
   `sendmsg`/`sendmmsg` call instead of one syscall per message
   (~9%+ of CPU is syscall/network-stack entry/exit overhead, on top
   of the actual bytes-on-wire cost).
3. **Batch or cache crypto verification** — if many commands from the
   same client can be verified together, or if verification results
   can be amortized across a block, the ~13% secp256k1 cost drops.
4. **SRSO mitigation** (~2.8%) is a kernel/CPU security tax
   (Spectre-class), disableable via `mitigations=off` at boot — a real
   but small lever, and only appropriate to touch in a fully
   controlled, non-production research testbed like this one; not
   something to flip lightly.

None of these are config-file changes — they're source-level
engineering work in `examples/hotstuff_client.cpp`/`hotstuff_app.cpp`
and `salticidae`, out of scope for a benchmarking session, but this is
the concrete, evidence-backed list of what to target if pushing the
ceiling higher becomes the goal.
