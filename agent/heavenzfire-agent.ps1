#Requires -Version 5.1
<#
.SYNOPSIS  Run the HeavenzFire local agent: think-act-observe loop on your machine.
.DESCRIPTION
  Checks Ollama + the heavenzfire model, ensures the capsule exists, then
  starts agent.py with your task. The agent reasons, calls tools, observes
  results, and continues until done. Destructive actions pause for your
  approval in this console. Nothing leaves the machine.

  Usage: .\heavenzfire-agent.ps1 "summarize the notes in .\notes"
#>
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$TaskArgs
)

$ErrorActionPreference = 'Stop'
$AgentRoot = $PSScriptRoot
$AgentPy = Join-Path $AgentRoot 'agent.py'
$CapsuleRoot = 'C:\sixteen\capsule'
$Model = if ($env:HF_AGENT_MODEL) { $env:HF_AGENT_MODEL } else { 'heavenzfire' }

if (-not (Test-Path -LiteralPath $AgentPy -PathType Leaf)) {
    throw "agent.py not found next to this script: $AgentPy"
}

# 1. Python present?
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $py) {
    throw "python not found in PATH. Install Python 3.10+ first."
}

# 2. Ollama present?
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    throw "ollama not found in PATH. Install Ollama first: https://ollama.com"
}

# 3. Model present?
$models = & ollama list 2>$null
if (-not ($models -match "(?m)^$([regex]::Escape($Model))\s")) {
    throw "model '$Model' not found. Build it first: ollama create $Model -f Modelfile"
}

# 4. Capsule present? (seeded by heavenzfire-chat.ps1; the agent reads it)
if (-not (Test-Path -LiteralPath (Join-Path $CapsuleRoot 'memory.md'))) {
    Write-Host "capsule not found at $CapsuleRoot" -ForegroundColor Yellow
    Write-Host "run .\heavenzfire-chat.ps1 once to seed it, or set HF_CAPSULE_DIR."
}

# 5. Task required
$Task = ($TaskArgs -join ' ').Trim()
if (-not $Task) {
    Write-Host "usage: .\heavenzfire-agent.ps1 `"your task here`""
    Write-Host ""
    Write-Host "examples:"
    Write-Host '  .\heavenzfire-agent.ps1 "list .\notes and summarize them"'
    Write-Host '  .\heavenzfire-agent.ps1 "check git status and tell me what changed"'
    exit 2
}

$env:HF_AGENT_DIR = Join-Path 'C:\sixteen' 'agent'
Write-Host "starting agent (model: $Model) ..." -ForegroundColor Cyan
& $py.Path $AgentPy $Task
exit $LASTEXITCODE
