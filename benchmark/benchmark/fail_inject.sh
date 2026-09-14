#!/bin/bash
# Inject a failure into this host's replica after a delay, and record it.
#
#   fail_inject.sh <delay_seconds> <crash|freeze>
#
# crash  = SIGKILL: the process ends, and its connections close.
# freeze = SIGSTOP: the process stays alive, with connections open, but runs
#          nothing.
#
# Launched by CloudLabBench._run_single right after the clients are booted,
# so the delay is measured from client start. Prints one JSON object: the
# signal sent, the PID, the wall-clock time of injection, and the process
# state one second later ("gone" or "Z" for a crash, "T" for a freeze).
# That state is the per-run evidence that the injection took effect.
delay=$1
kind=$2
case "$kind" in
    crash) sig=KILL ;;
    freeze) sig=STOP ;;
    *) printf '{"error":"unknown failure type %s"}\n' "$kind"; exit 1 ;;
esac
sleep "$delay"
pid=$(pgrep -x hotstuff-app | head -1)
t=$(date +%s.%N)
if [ -n "$pid" ]; then
    kill -"$sig" "$pid"
    rc=$?
else
    rc=-1
fi
sleep 1
if [ -z "$pid" ]; then
    st=noprocess
elif [ -r "/proc/$pid/stat" ]; then
    st=$(awk '{print $3}' "/proc/$pid/stat")
else
    st=gone
fi
printf '{"type":"%s","signal":"%s","pid":"%s","kill_rc":%s,"injected_epoch":%s,"state_after_1s":"%s"}\n' \
    "$kind" "$sig" "$pid" "$rc" "$t" "$st"
