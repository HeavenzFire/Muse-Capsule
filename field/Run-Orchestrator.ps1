# Run-Orchestrator.ps1 — start the orchestrator HTTP face on Windows.
# Place orchestrator_server.py beside this script (or set $ServerPath).
# The brain payload lives at C:\sixteen\brain; the swarm orchestrator
# package (the folder containing swarm_orchestrator\) at C:\sixteen\orchestrator.
# Adjust the two paths if your install laid them out differently —
# the health check at the end is the judge.
$ErrorActionPreference = "Stop"

$env:HF_BRAIN_DIR     = "C:\sixteen\brain"
$env:HF_SWARM_DIR     = "C:\sixteen\orchestrator"
$env:HF_ORCH_WORKDIR  = "C:\sixteen\orchestrator-data"

$ServerPath = Join-Path $PSScriptRoot "orchestrator_server.py"
if (-not (Test-Path $ServerPath)) { throw "orchestrator_server.py not found beside this script." }
if (-not (Test-Path (Join-Path $env:HF_SWARM_DIR "swarm_orchestrator"))) {
  throw "swarm_orchestrator package not found at $env:HF_SWARM_DIR — set HF_SWARM_DIR to the folder that contains it."
}

Write-Host "Starting orchestrator face on 127.0.0.1:18082 (Ctrl+C to stop)..."
python $ServerPath
