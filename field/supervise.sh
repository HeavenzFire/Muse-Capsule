#!/usr/bin/env bash
# Unified Field supervisor — keeps the field's services alive.
# Started by the unified-field systemd unit (see field/boot.sh).
# The node brings its own mesh-daemon child up under its supervision.
FIELD=/home/hatch/workspace/field
LOG=$FIELD/logs
mkdir -p "$LOG"

run_forever() { # name workdir cmd...
  local name=$1 wd=$2; shift 2
  while true; do
    echo "[supervise] starting $name $(date -Is)" >> "$LOG/$name.log"
    ( cd "$wd" && exec "$@" ) >> "$LOG/$name.log" 2>&1
    echo "[supervise] $name exited rc=$? — restarting in 2s" >> "$LOG/$name.log"
    sleep 2
  done
}

run_forever brain       /home/hatch/workspace/prime-brain-build  python3 server.py &
run_forever node        /home/hatch/workspace/asus-node/bin      python3 node.py &
run_forever orchestrator /home/hatch/workspace/field             python3 orchestrator_server.py &
run_forever gateway     /home/hatch/workspace/sovereign-gateway python3 -m gateway.gateway &

wait
