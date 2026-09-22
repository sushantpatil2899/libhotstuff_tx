# What we learned about SmallBank on HotStuff

A single account of the whole study: what we set out to measure, the first
attempt that produced confident and wrong answers, how we rebuilt it, what
each phase found, and what is still unexplained. Every number here comes
from a run whose logs we still have. Each phase leads with a table of
throughput and latency, and the discussion follows it.

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

We confirmed this in the runs themselves: with 2,000 allowed in flight the
measured product was 1,999; with 4,000 it was 3,999; with 8,000 it was
7,998; with 32,000 it was 31,999. **Every throughput result in this study
is therefore also a latency result**, which is why both appear in every
table below.

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
better**, and slowing more replicas better still. That is the opposite of
how the protocol is supposed to work, and it was not a fluke sample: 384
runs, repeated, with a measured noise level of about 2%, agreeing in every
direction we checked.

**All of it was wrong, and one broken instrument caused it.**

At shutdown the client wrote one line per completed transaction, and the
harness gave it two seconds before killing it. It never finished. Every
client log in the entire study was about **21.6 MB, roughly 416,000
records** — the same size whether the workload was tiny or huge, delayed or
undelayed. So every "result" was computed from roughly the first **9
seconds** of each 60-second run, mostly start-up.

The signal was visible the whole time and we explained it away: one run
reported an average latency of **3.11 ms** while a 50 ms delay was
injected. That is impossible — 50 ms of delay forces hundreds of
milliseconds of round trips on the commit path.

Two smaller defects sat in the same client: it read a record after deciding
the record did not exist, and it counted any two replies as confirmation
rather than two *different* replicas confirming.

**What an independent instrument showed.** Counting agreement rounds in the
replicas' own logs — never touching the client's numbers — the same
experiment said the exact opposite (one client, 200 ms delay):

| what was slowed | rounds in 60 s | throughput, from the replicas | what the client had reported |
|---|---|---|---|
| nothing | 26,463 | 87,125 | 44,070 |
| one follower | 27,724 | 88,707 | 42,855 |
| **the leader** | **153** | **501** | 48,915 |
| two followers | 153 | 500 | 47,578 |
| three followers | 152 | 498 | 47,290 |

A 174-fold collapse had been reported as a 10% improvement. Two further
instruments agreed: the leader's own vote timings showed votes arriving
401 ms after it proposed, and the network counters showed the delayed links
carrying exactly the ~150 rounds' worth of traffic.

**The lesson, and what we changed.** Repeating runs and checking effect
sizes does not protect you from a broken instrument, because the error is
in every repeat equally. Only a second, independent instrument does. From
this point on:

- Throughput was counted over a **fixed window** (from 10 seconds in to 2
  seconds before the end), not from first-to-last transaction.
- Every run recorded a **per-second count**, so a run that silently stopped
  committing was detected instead of reported as fast.
- **Every injected condition was verified inside every run**: network delay
  by pinging all replica pairs (5,440 pairs measured; links meant to be
  free measured 0.10 ms, links meant to add 400 ms measured 400.14 ms, no
  packet loss), CPU limits by reading each replica's allowed cores every
  second, and injected failures by recording the killed process's state.
- Old reports were kept with retraction notices rather than deleted, and 29
  runs whose throughput had been computed the flawed way were re-measured.

---

## 3. Act two: rebuilding the foundation

Four operating points were chosen and carried through every later phase.
Threads were fixed at 4 (more made no difference) and 9 of 10 transactions
write.

| name | block size | clients | in flight per client | total in flight | throughput | latency |
|---|---|---|---|---|---|---|
| **B1** | 200 | 2 | 1,000 | 2,000 | 165,125 | 12.1 ms |
| **B2** | 800 | 4 | 1,000 | 4,000 | 301,718 | 13.3 ms |
| **B3** | 1,600 | 8 | 1,000 | 8,000 | 444,759 | 18.0 ms |
| **B4** | 3,200 | 8 | 4,000 | 32,000 | 458,388 | 69.8 ms |

**Is it saturated?** Yes. The four baselines show it directly: B4 is given
**four times** as much work in flight as B3, and returns 3% more
throughput for **3.9 times** the latency.

| | work in flight | throughput | latency |
|---|---|---|---|
| **B3** | 8,000 | 444,759 | 18.0 ms |
| **B4** | 32,000 | 458,388 | 69.8 ms |
| | 4x the work | **+3%** | **+288%** |

Pushing much harder confirms it. Keeping B2's shape and raising the work in
flight 64-fold, from 4,000 to 256,000, moved throughput from 310,922 to
332,402 — **+7%, then nothing** — while latency rose from 12.9 ms to 246.7
ms. (Those two runs come from the earlier measurement generation, so they
are comparable with each other but not with the fixed-window figures
elsewhere in this document.) At B3's shape more load actively *hurts*:
447,053 falls to 308,526.

So B4 is near the best this four-machine system ever produced (about
459,000), and everything past these points buys latency, not throughput.

---

## 4. Act three: slow networks

Delay was added to specific replicas and verified in every run. Each cell
is **throughput / latency**, the middle of 5 runs.

### 4.1 One slow follower

| | no delay | 50 ms | 100 ms | 150 ms | 200 ms |
|---|---|---|---|---|---|
| **B1** | 165,681 / 12.1 ms | 160,911 / 12.0 | 164,695 / 12.1 | 162,796 / 12.3 | 165,285 / 12.1 |
| **B2** | 303,619 / 13.2 ms | 310,474 / 12.9 | 305,494 / 13.1 | 305,572 / 13.1 | 313,500 / 12.8 |
| **B3** | 446,626 / 17.9 ms | 397,534 / 20.2 | 412,624 / 19.4 | 408,408 / 19.6 | 404,071 / 19.8 |
| **B4** | 455,198 / 70.3 ms | 404,197 / 79.1 | 401,783 / 79.6 | 410,183 / 78.0 | 403,543 / 79.3 |

At B1 and B2, **neither throughput nor latency moves** — the changes are
smaller than ordinary run-to-run variation. At B3 and B4 throughput drops
about a tenth and latency rises about a tenth (17.9 → 19.8 ms, 70.3 → 79.3
ms). And crucially, **200 ms costs no more than 50 ms**: the penalty is for
one replica being slow at all, not for how slow it is.

### 4.2 The leader slowed (or two, or three followers)

| | 50 ms | 100 ms | 150 ms | 200 ms |
|---|---|---|---|---|
| **B1** | 1,971 / 1.02 s | 993 / 2.01 s | 665 / 2.99 s | 501 / 3.97 s |
| **B2** | 7,789 / 0.52 s | 3,978 / 1.02 s | 2,653 / 1.53 s | 1,998 / 2.03 s |
| **B3** | 15,402 / 0.52 s | 7,867 / 1.03 s | 5,287 / 1.54 s | 4,067 / 2.05 s |
| **B4** | 30,022 / 1.07 s | 15,727 / 2.08 s | 10,753 / 3.09 s | 8,197 / 4.11 s |

Against each baseline's own no-delay figure that is a **93.3% to 99.7% loss
of throughput**, with latency going from 12–70 **milliseconds** to 0.5–4.1
**seconds**. Delaying two followers, or all three, produced the same
numbers as delaying the leader — the largest disagreement anywhere among
the three scenarios was 2.0%. And **doubling the delay halves throughput
and doubles latency**, in all four baselines and all three scenarios.

**Why this is the expected behaviour.** Agreement needs 3 of the 4
replicas. With one follower slow, the leader still has two fast partners
and never waits. With the leader slow, or two followers slow, every
agreement must cross a slow link, so every block waits a full round trip.
The system behaves exactly as designed — which is precisely what the broken
first attempt had "disproven".

**What to do about it:** put the leader on the best-connected machine. One
badly-connected follower is affordable; a badly-connected leader is not.

---

## 5. Act four: weak machines

Replicas were restricted to fewer CPU cores, verified every second of every
run. Below, each baseline's own unrestricted control, then what happens
when the **leader** is squeezed, and when **one follower** is squeezed to a
single core.

| | control | leader at 4 cores | leader at 2 cores | leader at 1 core | one follower at 1 core |
|---|---|---|---|---|---|
| **B1** | 170,806 / 11.7 ms | −1.3% / 11.9 ms | −7.0% / 12.6 ms | **−23.6%** / 15.3 ms | −3.2% / 12.1 ms |
| **B2** | 308,603 / 13.0 ms | −3.1% / 13.4 ms | −10.3% / 14.4 ms | **−40.5%** / 21.8 ms | −8.6% / 14.2 ms |
| **B3** | 441,805 / 18.1 ms | −11.6% / 20.5 ms | −26.7% / 24.7 ms | **−56.8%** / 41.9 ms | −11.7% / 20.3 ms |
| **B4** | 455,631 / 70.2 ms | −11.8% / 79.6 ms | −25.1% / 93.8 ms | **−55.9%** / 159.2 ms | −12.3% / 78.1 ms |

Three things stand out:

- **8 cores changed nothing anywhere** — in all 24 combinations tested. The
  replicas never used more than 5.6 cores even when allowed all 64, so
  everything above about 6 cores is spare capacity for this workload.
- **Squeezing the leader hurts, and hurts more the bigger the
  configuration**: a quarter of throughput at B1, more than half at B3 and
  B4, with latency more than doubling (70 → 159 ms at B4).
- **Squeezing one follower is close to free**: −3% to −12% throughput and
  little latency change. The other follower we tested was cheaper still —
  between −0.6% and +0.7% at B2–B4 and *better* at B1 (+4.9%, 9.9 ms
  against 11.7 ms).

At 1 core every restricted replica was genuinely maxed out (using
0.91–1.00 cores, the machine reporting 87–98% CPU pressure), so these are
real limits and not artifacts of how the restriction was applied.

**What to do about it:** the leader's machine needs the cores. Followers
can run on modest hardware.

---

## 6. Act five: failures

The leader was killed outright (instant death) or frozen (alive but
answering nothing) 40 seconds into a 120-second run, and separately a
follower was. The system replaces a silent leader after a timeout, which we
also varied: 11 seconds (the built-in default), then 5, 2 and 1.

### 6.1 What each kind of failure costs (11-second timeout)

| | no failure | leader killed | leader frozen | follower killed | follower frozen |
|---|---|---|---|---|---|
| **B1** | 162,694 / 12.3 ms | 145,171 / 13.8 ms | 144,978 / 12.6 ms | 168,084 / 11.9 ms | 168,596 / 11.9 ms |
| **B2** | 300,438 / 13.3 ms | 323,115 / 12.4 ms | 324,285 / 12.3 ms | 356,982 / 11.2 ms | 357,709 / 11.2 ms |
| **B3** | 430,719 / 18.6 ms | 385,197 / 20.8 ms | 373,860 / 21.4 ms | 425,303 / 18.8 ms | 421,446 / 19.0 ms |
| **B4** | 434,083 / 73.7 ms | 379,206 / 76.0 ms | 379,966 / 79.7 ms | 421,468 / 75.0 ms | 413,678 / 77.2 ms |

- **Losing a follower costs nothing** — no stop in service at all, in 160
  runs, and latency unchanged or slightly better.
- **Losing the leader costs 11–13% of throughput** at B1, B3 and B4, with
  latency up 8–12%, *after* the service has resumed.
- **Killing and freezing behave identically**, everywhere. A frozen leader
  keeps its network connections open and a killed one does not, and that
  made no measurable difference.
- **B2 went faster after every failure.** That anomaly is section 7.1.

### 6.2 What the replacement timeout changes

| timeout | service stopped for | B1 after the failure | B1 normal | B4 after the failure | B4 normal |
|---|---|---|---|---|---|
| 11 s | 11 s | 145,171 / 13.8 ms | 162,694 / 12.3 ms | 379,206 / 76.0 ms | 434,083 / 73.7 ms |
| 5 s | 5 s | 145,439 / 13.4 ms | 165,805 / 12.1 ms | 363,805 / 80.0 ms | 433,081 / 73.9 ms |
| 2 s | 2 s | 143,473 / 13.8 ms | 167,463 / 11.9 ms | 372,777 / 79.2 ms | 430,600 / 74.3 ms |
| 1 s | 1 s | 145,273 / 13.5 ms | 164,943 / 12.1 ms | 376,735 / 76.4 ms | 424,661 / 75.4 ms |

Two results, and the first one needs care to read. **The outage tracks the
timeout one-for-one**, down to 1 second, and the replacement leader appears
one timeout after the failure, to the second. **The timeout does not change
what the system settles at afterwards** — the figures above are the same at
every setting.

**But that table deliberately excludes the outage.** It is measured in a
window that starts 40 seconds after the failure, to answer "once it has
recovered, what does it give?". The cost of the outage itself is reported
separately, as its length.

### 6.3 The same runs measured across the whole run, outage included

Counting from 10 seconds into the run to 2 seconds before its end — so the
stoppage is inside the window — the timeout matters exactly as you would
expect:

| leader killed | 11 s timeout | 5 s | 2 s | 1 s | gain, 1 s vs 11 s |
|---|---|---|---|---|---|
| **B1** | 118,679 / 14.8 ms | 132,874 / 14.6 ms | 141,875 / 13.6 ms | 144,526 / 13.7 ms | **+21.8%** |
| **B2** | 273,290 / 14.6 ms | 282,064 / 14.2 ms | 286,528 / 14.0 ms | 301,779 / 13.2 ms | **+10.4%** |
| **B3** | 314,548 / 25.4 ms | 116,100 / 24.5 ms* | 367,952 / 21.7 ms | 379,459 / 21.1 ms | **+20.6%** |
| **B4** | 314,675 / 96.4 ms | 349,458 / 89.8 ms | 371,233 / 80.3 ms | 375,685 / 79.2 ms | **+19.4%** |
| **no failure, for comparison (B4)** | 441,751 / 72.3 ms | 437,332 / 73.2 ms | 436,738 / 73.3 ms | 427,259 / 74.9 ms | +0% |

\* B3's 5-second cell includes three runs (of five) that never recovered at
all, which is why it is so low. These whole-run figures include such runs;
the after-recovery figures in 6.1 and 6.2 exclude them.

So both statements are true, and they answer different questions:

- **Per second of working time**, the timeout changes nothing — the system
  recovers to the same speed whether it waited 11 seconds or 1.
- **Per run**, a shorter timeout is worth **10% to 22% more work done**,
  because the system spends 10 fewer seconds doing none. Average latency
  improves too, most visibly at B4: **96.4 ms down to 79.2 ms**, because the
  transactions stuck through an 11-second stoppage are the ones that drag
  the average up.

That is the directly actionable result: the default of 11 seconds costs
about a fifth of the run's work, and shortening it to 1 second had **no
measured downside** — no run lost throughput and normal runs did not become
unstable.

One more asymmetry, measured across all four timeouts: B1 and B2 lose
**one** timeout of service, while B3 and B4 lose **two** (about 22 seconds
at the 11-second setting). Section 7.3 is why.

---

## 7. Act six: three strange things, explained

### 7.1 One configuration ran *faster* after a failure

B2 gained **+8%** after losing its leader and **+19%** after losing a
follower, every time, while every other baseline lost throughput.

The cause is not the protocol: **B2's own clients were the limit.** Each of
its 4 client processes had a thread pegged at 96–99% of one core. With a
replica gone, each client has one fewer replica to talk to per transaction,
so it works faster — and the system, which was waiting on the clients, gets
more work. We proved it by giving the same load to twice as many client
processes, changing nothing else:

| | 4 replicas alive | after losing one replica | gain |
|---|---|---|---|
| B2 as defined (4 clients x 1,000) | 303,602 / 13.2 ms | 363,110 / 11.0 ms | **+19.6%** |
| same load, 8 clients x 500 | **366,178 / 10.9 ms** | 368,085 / 10.9 ms | **+0.5%** |
| bs400 as defined (2 clients x 1,000) | 161,429 / 12.4 ms | 202,586 / 9.9 ms | +25.5% |
| same load, 4 clients x 500 | **264,308 / 7.6 ms** | 268,196 / 7.5 ms | **+1.5%** |

Split across more client processes, the same load runs 21% and 64% faster
with all four replicas alive, and the "gain from a failure" disappears. So
**B2's normal throughput was set by its client configuration, not by the
protocol** — any B2 number in this study partly measures the load
generator. We kept B2 as defined, because every earlier phase used it and
changing it would break comparability.

### 7.2 A leader failure silently loses transactions

After some leader failures exactly **one block** of transactions — 200 at
B1, 3,200 at B4 — was never completed, never reported as failed, and would
have left a real customer waiting forever. It happened in 45 of 143 runs.

| | throughput / latency | transactions in flight |
|---|---|---|
| B4, no failure | 434,083 / 73.7 ms | 32,000 |
| B4, healthy, run at the reduced load | **439,438 / 65.5 ms** | 28,799 |
| B4, after a leader failure | 379,206 / 76.0 ms | 28,798 |
| B1, no failure | 162,694 / 12.3 ms | 2,000 |
| B1, healthy, run at the reduced load | **162,870 / 11.1 ms** | 1,799 |
| B1, after a leader failure | 144,978 / 12.6 ms | 1,799 |

The middle row of each group is the check that matters: a **healthy** system
given exactly the reduced amount of work loses nothing at all. So the lost
block costs no throughput — it is a correctness gap, not a performance one.

Following individual transactions through the logs, the sequence is:

1. A new leader takes over and re-proposes everything it knows is pending.
2. Transactions arriving **1–4 milliseconds later** are only in that new
   leader's own pending buffer.
3. When the buffer fills, they are **taken out of it** to form one block.
4. That block's turn to be proposed is **discarded** — the internal wait it
   depends on is cancelled by the next scheduling step.
5. They are now in no buffer and no block, and **the client never re-sends**
   (there is no retry anywhere in the client).

The counts match exactly: lost transactions = discarded blocks × block
size. One run discarded two blocks and lost exactly 400.

**What to do about it:** give the client a retry. It is the difference
between "slower for a moment" and "some transactions never happen".

### 7.3 Why B3 and B4 lose two outages instead of one

The **first replacement leader stalls** within about 15 milliseconds of
taking over, and is itself replaced a timeout later. It is not a voting
problem — every block it proposed was voted by all three survivors and
accepted. It simply runs out of transactions to propose:

| the first replacement leader | stalled reign | reign that kept going |
|---|---|---|
| blocks it proposed | 10 | 52,331 |
| its last proposal | 12.0 s after the failure | 24.0 s after the failure |
| transactions clients completed during it | **600** | **10,464,618** |

What decides which happens is not block size but **how many client
processes there are**. We crossed the two at fixed load:

| block size | client processes | first replacement leader survived |
|---|---|---|
| large (1,600) | **2** | 3 of 4 runs |
| small (200) | **2** | 1 of 4 |
| small (200) | **8** | **0 of 4** |
| large (3,200) | **8** | 0 of 4 |

Across 56 leader-failure runs: with 2 client processes it survived 10 times
out of 18, with 4 processes 7 of 10, and **with 8 processes never — 0 of
28**. B3 and B4 both run 8 clients, which is why they always pay a second
outage.

The 17 runs that never recovered at all are this same failure repeating:
they rotated through **7 to 22 leaders**, each proposing almost nothing (0
to 13 blocks) before being replaced.

---

## 8. What we can say about this system

1. **It is fast when healthy**: 165,000 to 459,000 transactions per second
   on four machines, at 12 to 70 ms.
2. **It is limited by one thing at a time, and often that thing is the
   client.** At the smaller configurations the load generator, not the
   protocol, set the number.
3. **The leader is the asset to protect.** A slow-networked leader costs
   93–99% of throughput; a slow follower costs 10% or nothing. A
   CPU-starved leader costs up to 57%; a starved follower costs ~10% or
   nothing.
4. **Losing a follower is a non-event** — no outage, no lost work, in 160
   runs.
5. **Losing the leader costs exactly one timeout of silence** plus a
   lasting 11–13% drop. The timeout is a tunable we can safely shorten to 1
   second, which is worth 10–22% more work over a run that contains a
   failure.
6. **Recovery, not detection, is the weak part.** Detection works to the
   second. What follows is fragile: the replacement leader may stall, a
   block of customer transactions may vanish, and in about 1 run in 10 the
   system never gets going again.

**Worth changing, in order of value for effort:**

- Add a client retry. Removes silent transaction loss entirely.
- Lower the leader-replacement timeout from 11 s to about 1 s. Worth
  10–22% more work over a run containing a failure, with no measured cost.
- Let a new leader propose a partial block instead of waiting for a full
  one. This is the exact reason first replacement leaders stall.
- Run enough client processes that the load generator is not the ceiling.
- Place the leader on the best machine and the best network link.

---

## 9. Open questions

Each one below gives the setup that produced it, what we saw, and either the
answer we established or a plain statement that it is unknown.

### 9.1 Answered

**Why did B2 speed up after a failure?**
*Setup:* B2 (blocks of 800, 4 client processes, 1,000 in flight each), one
replica killed or frozen 40 seconds into a 120-second run, repeated at four
different replacement timeouts.
*What we saw:* +8% throughput after losing the leader and +19% after losing
a follower, in all 20 B2 failure cells, while B1, B3 and B4 all lost
throughput.
*Answer:* B2's clients were the bottleneck, each pegged at 96–99% of a
core. Splitting the same load across 8 client processes raised four-replica
throughput from 303,602 to 366,178 and shrank the post-failure gain from
+19.6% to +0.5% (7.1).

**Where do the lost transactions go when the leader fails?**
*Setup:* leader killed or frozen at B1 and B4; clients were asked at
shutdown which transactions they were still waiting for.
*What we saw:* exactly one block — 200 at B1, 3,200 at B4 — never completed
and never reported, in 45 of 143 runs.
*Answer:* the new leader takes those transactions out of its pending buffer
to form a block, and that block's turn to be proposed is discarded. They
then exist in no buffer and no block, and the client never re-sends. Lost
transactions equalled discarded blocks × block size, exactly, including one
run that lost two blocks (7.2).

**Does that lost block explain the throughput drop after a leader failure?**
*Setup:* healthy four-replica runs at exactly the reduced amount of work a
failure leaves behind.
*What we saw:* the healthy system lost nothing (B4: 439,438 at the reduced
load against 434,083 at full load).
*Answer:* no. The drop is the system being slower under a replacement
leader, not the missing work (7.2).

**Why do B3 and B4 lose two outages while B1 and B2 lose one?**
*Setup:* leader killed at all four baselines and four timeouts, tracing what
the first replacement leader did.
*What we saw:* the first replacement leader either kept proposing for the
rest of the run, or stalled within 15 ms and was replaced a timeout later.
*Answer:* it stalls for want of transactions to propose, and what decides it
is the number of client processes — it survived 0 of 28 runs with 8 clients
and 17 of 28 with 2 or 4 (7.3).

**Why did some runs never recover at all?**
*Setup:* the 17 leader-failure runs out of 160 whose throughput stayed at
zero.
*What we saw:* they rotated through 7 to 22 leaders, each proposing 0 to 13
blocks.
*Answer:* the same stall as above, repeating at every leader instead of
breaking out of it once.

**Is the benchmark actually saturated, or just under-driven?**
*Setup:* B2's shape with the work in flight raised from 4,000 to 256,000.
*What we saw:* throughput went 308,783 → 328,967 → 334,422 → 329,547 while
latency went 12.9 ms → 777 ms.
*Answer:* saturated. Sixty-four times the load buys 8% and then nothing.

### 9.2 Still unknown

**Why does the number of client processes decide whether a replacement
leader survives?**
*Setup:* leader killed, with block size and client count crossed at a fixed
8,000 transactions in flight.
*What we saw:* 2 client processes survived in 3 of 4 runs with big blocks
and 1 of 4 with small ones; 8 client processes survived in 0 of 8. Neither
per-client load nor total load separates the cases — two configurations
with the same 8,000 in flight behave oppositely.

**Why is the first hand-over's discarded block harmless, when the second
one's loses transactions?**
*Setup:* leader killed at B1 and B4, logging each discarded block.
*What we saw:* every run discards a block at the first hand-over, including
the runs that lose nothing at all; only the second hand-over's discard
costs transactions.

**Are the losses in runs with a single hand-over the same mechanism?**
*Setup:* Stage L and LT leader-failure runs, 9 of 24 at B1 and 3 of 33 at
B2 lost a block with only one hand-over recorded.
*What we saw:* our instrumented runs never reproduced that case — all five
losses under instrumentation had two hand-overs. So those losses are
counted but their cause is unverified.

**Why does one particular follower consistently use the most CPU?**
*Setup:* all four replicas sampled every second at B3, unrestricted.
*What we saw:* one follower used 5.5 cores against 4.5 for the others, with
a third of their voluntary context switches and the lowest power draw. When
restricted to a single core it sometimes made the system *faster* (+4.9% at
B1).

**Why does a run occasionally stop committing with no fault injected?**
*Setup:* ordinary no-fault runs across every phase.
*What we saw:* 5 stalls in 33 runs at B4, 3 in 185 at B3, never at B1 or
B2. The replica logs of those runs contain no error or warning.

**Why does throughput settle 11–13% below normal after a leader failure?**
*Setup:* leader killed or frozen at B1, B3 and B4, measured 40 seconds
after the failure once service had resumed.
*What we saw:* a lasting shortfall at every timeout setting, even though
the lost block accounts for none of it and the replacement leader is voting
and committing normally.

---

Conventions used throughout, after the rebuild: throughput counted over a
fixed window; runs that stopped committing counted separately and excluded
from the figures; the injected condition verified inside every run; and no
mechanism written down without a measurement behind it. Where a prediction
of ours was refuted by the data, the refutation is recorded next to it.
