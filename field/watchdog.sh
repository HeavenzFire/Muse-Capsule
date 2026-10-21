#!/usr/bin/env bash
# Unified Field watchdog: if the field is down — or a VM redeploy wiped
# the systemd unit entirely — resurrect it from the recovery script.
# Silent when healthy. Logs only when it acts.
FIELD=/home/hatch/workspace/field
LOG=$FIELD/logs/watchdog.log
mkdir -p "$FIELD/logs"

down=0
for p in 18080 18081 18082 18090 18091; do
  (echo > /dev/tcp/127.0.0.1/$p) 2>/dev/null || down=1
done
[ "$down" -eq 0 ] && exit 0

echo "[watchdog $(date -Is)] field incomplete — resurrecting" >> "$LOG"
if [ ! -f /etc/systemd/system/unified-field.service ]; then
  bash "$FIELD/boot.sh" >> "$LOG" 2>&1
else
  systemctl restart unified-field >> "$LOG" 2>&1 || bash "$FIELD/boot.sh" >> "$LOG" 2>&1
fi
sleep 8
still=0
for p in 18080 18081 18082 18090 18091; do
  (echo > /dev/tcp/127.0.0.1/$p) 2>/dev/null || still=1
done
if [ "$still" -eq 0 ]; then
  echo "[watchdog $(date -Is)] field restored" >> "$LOG"
else
  echo "[watchdog $(date -Is)] RESTORE INCOMPLETE — needs a mind" >> "$LOG"
fi
