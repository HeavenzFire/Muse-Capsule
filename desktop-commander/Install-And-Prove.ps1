# Install-And-Prove.ps1 - HeavenzFire Desktop Commander V1 + GPT connector
# ONE run does everything: install the commander, run its tests, birth
# its key (first run only - an existing key is NEVER re-born), start
# it, and run GPT's connection + execution proofs against it.
# Idempotent: re-running backs up replaced files and re-proves.
#
# Run it AS A FILE (pasting it into the prompt breaks $PSScriptRoot):
#   powershell -ExecutionPolicy Bypass -File <repo>\desktop-commander\Install-And-Prove.ps1
$ErrorActionPreference = 'Stop'

if (-not $PSScriptRoot) {
    throw 'Run this script with -File, do not paste it. $PSScriptRoot is empty in a paste.'
}

$Src       = $PSScriptRoot                                    # <repo>\desktop-commander
$RepoRoot  = Split-Path -Parent $Src                          # <repo>
$Dest      = Join-Path $env:USERPROFILE 'HeavenzFire\commander'
$Connector = Join-Path $RepoRoot 'interchange\desktop-connector'
$Executor  = Join-Path $Connector 'desktop_executor.py'

Write-Host "`n=== 0. Preconditions ==="
$py = $null
foreach ($cand in @('python', 'py')) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) { $py = $cand; break }
}
if (-not $py) { throw 'Python not found on PATH. Install Python 3.9+ (tick Add to PATH), then run this script again.' }
Write-Host "  python: $py"
if (-not (Test-Path $Executor)) { throw "Connector executor missing: $Executor - git pull the repo first." }

Write-Host "`n=== 1. Install Commander files ==="
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
foreach ($f in @('commander.py', 'test_commander.py', 'README.md')) {
    $target = Join-Path $Dest $f
    if (Test-Path $target) { Copy-Item $target "$target.bak-$stamp" }
    Copy-Item (Join-Path $Src $f) $target -Force
    Write-Host "  installed: $target"
}

Write-Host "`n=== 2. Commander test suite (installed copy) ==="
Push-Location $Dest
try {
    & $py test_commander.py
    if ($LASTEXITCODE -ne 0) { throw 'Commander tests FAILED. Do not proceed; keep this output.' }
} finally { Pop-Location }

Write-Host "`n=== 3. Key (preserve existing, birth only if missing) ==="
$KeyFile = Join-Path $Dest 'commander.key'
function Start-CommanderBriefly {
    $p = Start-Process -FilePath $py -ArgumentList 'commander.py' -WorkingDirectory $Dest -PassThru -WindowStyle Hidden
    return $p
}
if (Test-Path $KeyFile) {
    Write-Host '  existing commander.key preserved - NOT re-born.'
} else {
    $bp = Start-CommanderBriefly
    $deadline = (Get-Date).AddSeconds(15)
    while (-not (Test-Path $KeyFile) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 300 }
    if (-not $bp.HasExited) { Stop-Process -Id $bp.Id }
    if (-not (Test-Path $KeyFile)) { throw 'Key file did not appear on first start. Keep this output.' }
    Write-Host "  key born: $KeyFile"
}

Write-Host "`n=== 4. Start Commander server on 127.0.0.1:18077 ==="
function Test-CommanderUp {
    try {
        Invoke-WebRequest -Uri 'http://127.0.0.1:18077/status' -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        # A 401 here also proves the server is up (it demands the key).
        if ($_.Exception.Response) { return $true }
        return $false
    }
}
if (Test-CommanderUp) {
    Write-Host '  already running - left as is.'
} else {
    $sp = Start-Process -FilePath $py -ArgumentList 'commander.py' -WorkingDirectory $Dest -PassThru -WindowStyle Hidden
    Set-Content -Path (Join-Path $Dest 'commander-server.pid') -Value $sp.Id -Encoding ASCII
    $deadline = (Get-Date).AddSeconds(20)
    while (-not (Test-CommanderUp) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 400 }
    if (-not (Test-CommanderUp)) { throw 'Commander did not come up on 127.0.0.1:18077. Keep this output.' }
    Write-Host "  running, pid $($sp.Id) (recorded in commander-server.pid)"
}

Write-Host "`n=== 5. Verify Commander ledger ==="
& $py (Join-Path $Dest 'commander.py') --verify
if ($LASTEXITCODE -ne 0) { throw 'Ledger verification failed. Stop; do not retry blindly.' }

Write-Host "`n=== 6. GPT proof 1 - authenticated status ==="
# Note: the example packages carry host label 'vm' - the label is a
# name only; routing is by --commander-base / the local 18077 server.
$env:COMMANDER_KEY_FILE = $KeyFile
& $py $Executor (Join-Path $Connector 'examples\example_request.json') --out (Join-Path $Connector 'result-status.json')
if ($LASTEXITCODE -ne 0) { throw 'Status proof failed. Inspect result-status.json; do not retry blindly.' }
$statusResult = Get-Content (Join-Path $Connector 'result-status.json') -Raw | ConvertFrom-Json
if ($statusResult.status -ne 'ok') { throw "Status proof returned '$($statusResult.status)', not ok. Inspect result-status.json." }
Write-Host "  status: ok, ledger entries: $($statusResult.ledger_entries)"

Write-Host "`n=== 7. GPT proof 2 - harmless execution ==="
& $py $Executor (Join-Path $Connector 'examples\test-exec.json') --out (Join-Path $Connector 'result-exec.json')
if ($LASTEXITCODE -ne 0) { throw 'Execution proof failed. Inspect result-exec.json; do not retry blindly.' }
$execResult = Get-Content (Join-Path $Connector 'result-exec.json') -Raw | ConvertFrom-Json
if ($execResult.status -ne 'ok') { throw "Exec proof returned '$($execResult.status)', not ok." }
if ($execResult.output.exit_code -ne 0) { throw "Exec proof exit code $($execResult.output.exit_code), not 0." }
if ($execResult.output.stdout -notmatch 'gpt-desktop-roundtrip') { throw 'Exec proof stdout did not contain gpt-desktop-roundtrip.' }
Write-Host "  exec: ok, stdout gpt-desktop-roundtrip, exit code 0"

Write-Host "`n=== ALL AUTO STEPS PASSED ==="
Write-Host "  Commander:  http://127.0.0.1:18077 (loopback only, still running)"
Write-Host "  Stop it:    Stop-Process -Id (Get-Content (Join-Path '$Dest' 'commander-server.pid'))"
Write-Host "  Results:    $(Join-Path $Connector 'result-status.json')"
Write-Host "              $(Join-Path $Connector 'result-exec.json')"
Write-Host '  The key stayed in commander.key beside the commander. It was never printed.'
