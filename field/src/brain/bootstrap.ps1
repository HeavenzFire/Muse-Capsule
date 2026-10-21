# HeavenzFire Prime Brain -- one-click bootstrap.
# Double-click this file. It extracts the brain, runs the self-test,
# and starts the server if the test is green.
# The capsule (CRAYDON-CAPSULE.json) is placed by YOUR hand -- never automated.
$ErrorActionPreference = "Stop"

$Zip  = "$HOME\Downloads\prime-brain.zip"
$Dest = "C:\sixteen\brain"

Write-Host "`n=== PRIME BRAIN BOOTSTRAP ===" -ForegroundColor Cyan

if (!(Test-Path -LiteralPath $Zip -PathType Leaf)) {
    Write-Host "prime-brain.zip not found in Downloads." -ForegroundColor Red
    Write-Host "Download it first, then double-click this again."
    pause; exit 1
}

Write-Host "[1/3] Extracting to $Dest ..."
Expand-Archive -Path $Zip -DestinationPath $Dest -Force
Set-Location -LiteralPath $Dest

Write-Host "[2/3] Running kernel self-test (py -3.12) ..."
& py -3.12 kernel.py --self-test
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nSELF-TEST FAILED. Server not started. Fix the errors above." -ForegroundColor Red
    pause; exit 1
}

Write-Host "`n[3/3] Self-test GREEN. Starting brain server :18081 ..." -ForegroundColor Green
Write-Host "Place CRAYDON-CAPSULE.json in $Dest by hand, then"
Write-Host "verify from this machine:  Invoke-RestMethod http://127.0.0.1:18081/status"
Write-Host "verify from the phone:     http://192.168.4.21:18081/status"
Write-Host "`nClose this window to stop the brain.`n"

& py -3.12 server.py
