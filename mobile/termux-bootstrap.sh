#!/data/data/com.termux/files/usr/bin/bash
# HeavenzFire phone-first bootstrap for Termux.
# Installs development tools and clones Muse-Capsule; does not configure
# network listeners, create credentials, install background services, or
# run model-generated shell actions.

set -eu

if [ -z "${PREFIX:-}" ] || [ ! -x "${PREFIX}/bin/pkg" ]; then
  echo "ERROR: This script must run inside Termux on Android."
  exit 1
fi

echo "HeavenzFire / Muse-Capsule — Termux bootstrap"
echo "This will install Git, Python, Node.js LTS, and the OpenSSH client,"
echo "then clone the public Muse-Capsule repository into:"
ROOT="$HOME/HeavenzFire/Muse-Capsule"
echo "  $ROOT"
echo
printf "Continue? [y/N] "
read -r answer
case "$answer" in
  y|Y|yes|YES) ;;
  *) echo "Cancelled; no changes made."; exit 0 ;;
esac

pkg update
pkg install -y git python nodejs-lts openssh

mkdir -p "$HOME/HeavenzFire"
if [ -e "$ROOT" ]; then
  if [ -d "$ROOT/.git" ]; then
    echo
    echo "Existing Git checkout found at $ROOT"
    echo "Leaving it untouched to avoid overwriting local work."
    echo "Review it manually, then run:"
    echo "  python \"$ROOT/agent/agent.py\" --capsule-check"
    exit 0
  else
    echo "ERROR: $ROOT already exists but is not a Git checkout."
    echo "Move or rename it manually if you want to clone into that path."
    exit 1
  fi
fi

git clone https://github.com/HeavenzFire/Muse-Capsule.git "$ROOT"

echo
echo "=== Installed tool versions ==="
git --version
python --version
node --version
npm --version
ssh -V 2>&1 || true

echo
echo "=== Capsule integrity check ==="
python "$ROOT/agent/agent.py" --capsule-check

echo
echo "Bootstrap complete."
echo "This sets up source development only. It does not install or start Ollama,"
echo "does not prove a local model runs on Android, and does not connect to ZDH."
