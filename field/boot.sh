#!/usr/bin/env bash
# Install + start the Unified Field as a systemd service.
# The unit file itself lives outside ~ and dies with a VM redeploy;
# this script (in ~/workspace/field) is the recovery path: re-run it.
set -e
cat > /etc/systemd/system/unified-field.service <<'UNIT'
[Unit]
Description=Unified Field — brain, node+mesh, orchestrator, gateway
After=network.target

[Service]
Type=simple
ExecStart=/home/hatch/workspace/field/supervise.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
chmod +x /home/hatch/workspace/field/supervise.sh
systemctl daemon-reload
systemctl enable --now unified-field
systemctl --no-pager status unified-field | head -12
