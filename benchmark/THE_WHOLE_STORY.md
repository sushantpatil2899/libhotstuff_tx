# What we learned about SmallBank on HotStuff

A single account of the whole study: what we set out to measure, the first
attempt that produced confident and wrong answers, how we rebuilt it, what
each phase found, and what is still unexplained. Every number here comes
from a run whose logs we still have.

---

## 1. What the thing under test is

Four server machines ("replicas") agree on the order of banking
transactions, so that the four of them behave like one bank even if one
misbehaves. A fifth machine runs the customers ("clients"), which send
transactions and wait for answers.

| | |
|---|---|
| Machines | 5 x CloudLab `d6515`: 32 cores, 64 hardware threads, 125 GB RAM |
| Replicas | 4. The system tolerates 1 failing. A block of transactions is agreed once 3 of the 4 accept it |
| Clients | On one separate machine. A client counts a transaction as done when **2** replicas confirm it |
| Workload | SmallBank: 1,000,000 accounts; 9 of every 10 transactions change balances |
| Leader | One replica proposes blocks. The others vote |

Two numbers describe every run:

- **Throughput** — transactions finished per second.
- **Latency** — how long one transaction takes, from send to confirmed.

One property matters throughout and is easy to miss: **each client is
allowed only a fixed number of unanswered transactions at a time**. It
sends a new one only when an old one comes back. So the system is never
asked for more work than that cap, and

> throughput = (transactions allowed in flight) ÷ (latency)

We confirmed this holds in the runs themselves: with 2,000 allowed in
flight the measured product was 1,999; with 4,000 it was 3,999; with 8,000
it was 7,998; with 32,000 it was 31,999. Any throughput result in this
study is therefore also a latency result.

---

## 2. Act one: the first attempt, and why we threw it away

The first pass measured what looked like a clean ceiling of about
**46,000–56,000 transactions per second**, and produced three tidy
conclusions:

1. Adding worker threads does nothing (+5.2% at best).
2. Block size does nothing.
3. The leader is pinned at one saturated core, so that is the ceiling.

Then came the network experiment — slowing down links between replicas —
and the answer was striking: **slowing the leader made throughput slightly
better**, and slowing more replicas made it better still. That is the
opposite of how the protocol is supposed to work, and it was not a fluke
sample: it was 384 runs, repeated, with a measured noise level of about
2%, agreeing in every direction we checked.

**All of it was wrong, and one broken instrument caused it.**

At shutdown, the client wrote one line per completed transaction, and the
harness gave it two seconds before killing it. It never finished. Every
client log in the entire study was about **21.6 MB, roughly 416,000
records** — the same size whether the workload was tiny or huge, delayed or
undelayed. So every "result" was computed from roughly the first **9
seconds** of each 60-second run, mostly start-up.

The signal was visible the whole time and we explained it away: one run
reported an average latency of **3.11 ms** while a 50 ms delay was
injected, which is physically impossible — a delay of 50 ms forces
hundreds of milliseconds of round trips on the commit path.

Two smaller defects sat in the same client: it read a record after
deciding the record did not exist, and it counted any two replies as
confirmation rather than two *different* replicas confirming.

**What an independent instrument showed.** Counting agreement rounds in
the replicas' own logs — never touching the client's numbers — the same
experiment said the exact opposite, and matched the textbook behaviour
(one client, 200 ms):

| what was slowed | rounds in 60 s | throughput, from the replicas | what the client had reported |
|---|---|---|---|
| nothing | 26,463 | 87,125 | 44,070 |
| one follower | 27,724 | 88,707 | 42,855 |
| **the leader** | **153** | **501** | 48,915 |
| two followers | 153 | 500 | 47,578 |
| three followers | 152 | 498 | 47,290 |

A 174-fold collapse had been reported as a 10% improvement. Two further
instruments agreed: the leader's own vote timings showed votes arriving
401 ms after it proposed, and the network counters showed the delayed
links carrying exactly the ~150 rounds' worth of traffic.

**The lesson, and what we changed.** Repeating runs and checking effect
sizes does not protect you from a broken instrument, because the error is
in every repeat equally. Only a second, independent instrument does. From
this point on:

- Throughput was counted over a **fixed window** (from 10 seconds in to 2
  seconds before the end), not from first-to-last transaction.
- Every run recorded a **per-second count**, so a run that silently stopped
  committing could be detected instead of being reported as fast.
- **Every injected condition was verified inside every run**: the network
  delay by pinging all replica pairs (5,440 pairs measured; links meant to
  be free measured 0.10 ms, links meant to add 400 ms measured 400.14 ms,
  no packet loss), CPU limits by reading each replica's allowed cores each
  second, and injected failures by recording the killed process's state.
- Old documents were kept with retraction notices rather than deleted, and
  29 runs whose throughput had been computed the flawed way were re-measured.

---

## 3. Act two: rebuilding the foundation

We then measured properly, and picked four operating points to carry
through every later phase. Threads were fixed at 4 (more made no
difference) and 9 of 10 transactions write.

| name | block size | clients | in flight per client | total in flight | throughput | latency |
|---|---|---|---|---|---|---|
| **B1** | 200 | 2 | 1,000 | 2,000 | 165,125 | 12.1 ms |
| **B2** | 800 | 4 | 1,000 | 4,000 | 301,718 | 13.3 ms |
| **B3** | 1,600 | 8 | 1,000 | 8,000 | 444,759 | 18.0 ms |
| **B4** | 3,200 | 8 | 4,000 | 32,000 | 458,388 | 69.8 ms |

**Is it saturated?** Yes, and we measured where. Taking B2's shape and
piling on work:

| transactions allowed in flight | throughput |
|---|---|
| 4,000 | 308,783 |
| 16,000 | 328,967 |
| 64,000 | 334,422 |
| 256,000 | 329,547 |

Sixty-four times the load buys 8% and then stops. At B3's shape, more load
actively hurts: 447,053 falls to 308,526. So B4 is near the best this
4-machine system ever produced (about 459,000), and pushing past these
points only inflates latency.

---

## 4. Act three: slow networks

We added delay to specific replicas and verified it in every run.

**One slow follower is nearly free — or free.**

| | no delay | 50 ms | 200 ms |
|---|---|---|---|
| B1 | 165,681 | 160,911 | 165,285 |
| B2 | 303,619 | 310,474 | 313,500 |
| B3 | 446,626 | 397,534 (−11%) | 404,071 (−10%) |
| B4 | 455,198 | 404,197 (−11%) | 403,543 (−11%) |

At B1 and B2 the change is too small to separate from normal run-to-run
variation. At B3 and B4 it costs about a tenth of throughput — and
crucially, **200 ms costs no more than 50 ms**. The penalty is for being
slow at all, not for how slow.

**Slowing the leader, or two or more followers, collapses the system.**

| | 50 ms | 100 ms | 150 ms | 200 ms |
|---|---|---|---|---|
| B1 leader slowed | 1,971 | 993 | 665 | 501 |
| B3 leader slowed | 15,402 | 7,867 | 5,287 | 4,067 |

Latency goes from milliseconds to **1.0, 2.0, 3.0, 4.0 seconds** — exactly
the round trips the delay forces. Slowing two followers, or three, gives
the same numbers as slowing the leader.

**Why this is the expected behaviour.** Agreement needs 3 of 4 replicas.
With one follower slow, the leader still has two fast partners and never
waits. With the leader slow, or two followers slow, every agreement must
cross a slow link. The system behaves exactly as designed — which is
precisely what the broken first attempt had "disproven".

**What to do about it:** put the leader on the best-connected machine. One
badly-connected follower is affordable; a badly-connected leader is not.

---

## 5. Act four: weak machines

We restricted replicas to fewer CPU cores (8, 6, 4, 3, 2, 1), verifying the
restriction every second of every run.

- **8 cores changed nothing anywhere** — in all 24 combinations. The
  replicas never used more than 5.6 cores even when allowed 64.
- **Squeezing the leader hurts most.** At 1 core: **−23.6%** (B1),
  **−40.5%** (B2), **−56.8%** (B3), **−55.9%** (B4), with latency up to
  159 ms at B4.
- **Squeezing one follower is close to free**, even at 1 core: between
  −0.6% and +0.7% at B2–B4, and at B1 it measured *better* (+4.9%).
- At 1 core every restricted replica was genuinely maxed out (using 0.91–1.00
  cores, with the machine reporting 87–98% CPU pressure), so the limit was
  real and not an artifact of the restriction.

**What to do about it:** the leader's machine is the one that needs the
cores. Followers can run on modest hardware. Anything above ~6 cores per
replica is spare capacity for this workload.

---

## 6. Act five: failures

We killed the leader outright (instant death) or froze it (alive but
answering nothing), 40 seconds into each 120-second run, and separately did
the same to a follower. The system replaces a silent leader after a
timeout, which we also varied: 11 seconds (the built-in default), then 5,
2 and 1.

**Killing a follower costs nothing.** No stop in service at any setting, in
160 runs.

**Killing the leader stops everything for exactly the timeout.**

| timeout | how long transactions stopped | throughput afterwards (B1) | normal |
|---|---|---|---|
| 11 s | 11 s | 145,171 | 162,694 |
| 5 s | 5 s | 145,439 | 165,805 |
| 2 s | 2 s | 143,473 | 167,463 |
| 1 s | 1 s | 145,273 | 164,943 |

Two clean results:

1. **The outage tracks the timeout one-for-one**, down to 1 second, and the
   replacement leader appears one timeout after the failure, to the second.
2. **The timeout does not change the throughput you end up with.** At every
   setting the system settles about 11–14% below normal at B1, B3 and B4
   (for example B4: 379,206 against 434,083 normally).

**Shortening the timeout had no measured downside.** With a 1-second
timeout, no run lost throughput and normal runs did not become unstable.
That is a directly actionable finding: the default of 11 seconds costs 10
seconds of total outage for nothing.

Three oddities came out of this phase, and we chased all three to the
bottom. They turned out to be the most interesting results in the study.

---

## 7. Act six: three strange things, explained

### 7.1 One configuration ran *faster* after a failure

B2 gained **+8%** after losing its leader and **+19%** after losing a
follower, every time. No other configuration did.

The cause is not the protocol: **B2's own clients were the limit.** Each of
its 4 client processes had a thread pegged at 96–99% of a core. With a
replica gone, each client has one fewer replica to talk to per transaction,
so it works faster — and the system, which was waiting on the clients, gets
more work.

We proved it by giving the same load to twice as many client processes,
changing nothing else:

| | 4 replicas | after losing one | gain |
|---|---|---|---|
| B2 as defined (4 clients x 1,000) | 303,602 | 363,110 | **+19.6%** |
| same load, 8 clients x 500 | **366,178** | 368,085 | **+0.5%** |
| bs400 as defined (2 clients x 1,000) | 161,429 | 202,586 | +25.5% |
| same load, 4 clients x 500 | **264,308** | 268,196 | **+1.5%** |

So the "gain after failure" disappears once the clients can keep up — and
B2's normal throughput is set by its client configuration, not by the
protocol. **Any B2 number in this study partly measures the load
generator.** We chose to keep B2 as defined, because every earlier phase
used it and changing it would break comparability.

### 7.2 A leader failure silently loses transactions

After some leader failures, exactly **one block** of transactions — 200 at
B1, 3,200 at B4 — was never completed, never reported as failed, and would
have left a real customer waiting forever. It happened in 45 of 143 runs.

Following individual transactions through the logs, the sequence is:

1. A new leader takes over and re-proposes everything it knows is pending.
2. Transactions arriving **1–4 milliseconds later** are only in that new
   leader's own pending buffer.
3. When the buffer fills, they are **taken out of the buffer** to form one
   block.
4. That block's turn to be proposed is **discarded** — the internal wait it
   depends on is cancelled by the next scheduling step.
5. They are now in no buffer and no block, and **the client never re-sends**
   (there is no retry anywhere in the client).

The counts match exactly: lost transactions = discarded blocks × block
size. One run discarded two blocks and lost exactly 400.

Reassuringly, this costs **no throughput** — we ran healthy systems at
exactly the reduced load and they lost nothing (B4 gave 439,438 at the
reduced load against 434,083 normally). It is a correctness gap, not a
performance one.

**What to do about it:** give the client a retry. It is the difference
between "slower for a moment" and "some transactions never happen".

### 7.3 Why B3 and B4 lose two outages instead of one

B1 and B2 lose one timeout of service; B3 and B4 lose two. The reason is
that the **first replacement leader stalls** within about 15 milliseconds
of taking over, and is itself replaced a timeout later.

It is not a voting problem — every block it proposed was voted by all three
survivors and accepted. It simply runs out of transactions to propose:
during a stalled reign the clients complete **600** transactions, against
**10.4 million** in a reign that gets going.

What decides it is not block size but **how many client processes there
are**. We crossed the two, at fixed load:

| block size | client processes | first replacement leader survived |
|---|---|---|
| large (1,600) | **2** | 3 of 4 |
| small (200) | **2** | 1 of 4 |
| small (200) | **8** | **0 of 4** |
| large (3,200) | **8** | 0 of 4 |

Across 56 leader-failure runs: with 2 client processes it survived 10 times
out of 18, with 4 processes 7 of 10, and **with 8 processes never — 0 of
28**.

And the 17 runs that never recovered at all are this same failure
repeating: they rotated through **7 to 22 leaders**, each proposing almost
nothing (0 to 13 blocks) before being replaced.

---

## 8. What we can say about this system

1. **It is fast when healthy**: roughly 165,000 to 459,000 transactions per
   second on four machines, at 12 to 70 ms.
2. **It is limited by one thing at a time, and often that thing is the
   client.** At the smaller configurations the load generator, not the
   protocol, sets the number.
3. **The leader is the asset to protect.** A slow-networked leader costs
   99% of throughput; a slow follower costs 10% or nothing. A CPU-starved
   leader costs up to 57%; a starved follower costs nothing.
4. **Losing a follower is a non-event.** No outage, no lost work, in 160
   runs.
5. **Losing the leader costs exactly one timeout of silence** plus a
   permanent 11–14% drop, and the timeout is a tunable we can safely
   shorten to 1 second.
6. **Recovery, not detection, is the weak part.** Detection works to the
   second. What follows is fragile: the replacement leader may stall, a
   block of customer transactions may vanish, and in about 1 run in 10 the
   system never gets going again.

**Things worth changing, in order of value for effort:**

- Add a client retry. Removes silent transaction loss entirely.
- Lower the leader-replacement timeout from 11 s to ~1 s. Shortens every
  outage with no measured cost.
- Let a new leader propose a partial block instead of waiting for a full
  one. This is the exact reason first replacement leaders stall.
- Run enough client processes that the load generator is not the ceiling.
- Place the leader on the best machine and the best network link.

---

## 9. Open questions

**Answered during the study** (each was a surprise first):

| question | answer |
|---|---|
| Why does B2 speed up after a failure? | Its clients were the bottleneck; with enough client processes the gain vanishes (+19.6% → +0.5%) |
| Where does the lost block go? | Assembled into a block whose turn to be proposed is discarded; no client retry |
| Does that lost block explain the throughput drop? | No. Healthy systems at the same reduced load lose nothing |
| Why two outages at B3 and B4? | The first replacement leader runs dry and is replaced |
| Why do some runs never recover? | The same running-dry, repeating across 7–22 leaders |
| Is the benchmark saturated? | Yes; 64x more load buys 8% and then nothing |

**Still unanswered:**

1. **Why the number of client processes decides whether a replacement
   leader survives.** Neither per-client load nor total load separates the
   cases: two configurations with the same 8,000 in flight behave
   oppositely.
2. **Why the first hand-over's discarded block is harmless** while the
   second one's loses transactions. Every run shows the first discard, and
   runs that lose nothing have only that one.
3. **The losses we recorded in runs with a single hand-over** (9 of 24 at
   B1) were never reproduced under instrumentation, so they are counted but
   not verified.
4. **Why one particular follower (replica 3) consistently uses the most
   CPU**, and why restricting it sometimes helped.
5. **Why a run occasionally stops committing with no fault injected** —
   5 times in 33 runs at B4, 3 times in 185 at B3, never at B1 or B2. The
   replica logs of those runs contain no error.
6. **Why throughput settles 11–14% below normal after a leader failure**,
   given the lost block accounts for none of it.

---

## 10. How to check any of this

| phase | runs | sweep definition | results |
|---|---|---|---|
| First attempt (retracted) | 384 + early grids | `netem_factorial.csv` | `INVESTIGATION_RECORD.md` |
| Measurement rebuild + audit | 29 re-measured | `audit_stalls.py` | `BASELINE_ANALYSIS.md` 13 |
| Baselines, load, write ratio | 1,445 | `stage_a..h.csv` | `BASELINE_ANALYSIS.md` |
| Network delay | 340 + 150 | `stage_n/o/p/q.csv` | `BASELINE_ANALYSIS.md` 12–14 |
| Fewer cores | 750 | `stage_u/k.csv` | `COMPUTE_ANALYSIS.md` |
| Failures | 529 | `stage_l/lt/m*.csv` | `FAILURE_ANALYSIS.md` |

Conventions used everywhere after the rebuild: throughput counted over a
fixed window; runs that stopped committing counted separately and excluded
from the figures; the injected condition verified inside every run; and no
mechanism written down without a measurement behind it. Where a prediction
of ours was refuted by the data, the refutation is recorded next to it.

**2,795 completed runs** are kept on disk with their logs, across every
sweep after the rebuild. The first attempt's runs are retained only as the
record of how it went wrong; its two reports carry retraction notices and
are superseded by `INVESTIGATION_RECORD.md`.
