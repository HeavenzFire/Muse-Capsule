# install-mesh.ps1 - CLEAN per-machine mesh installer.
#
# Run EXPLICITLY by Zachary on each machine. It never runs itself.
# What it does:
#   1. Copies C:\sixteen\brain\ from a source path HE provides.
#   2. Optionally registers a logon scheduled task, ONLY with -AutoStart.
#   3. Writes an install manifest (mesh-install.json): what, where, when.
#   4. Prints every action. Nothing silent.
#
# What it NEVER does: copy itself, scan for targets, hide anything,
# install persistence without the flag, or run without logging.
#
# Usage:
#   .\install-mesh.ps1 -Source "E:\brain-backup" [-AutoStart]

param(
    [Parameter(Mandatory = $true)][string]$Source,
    [switch]$AutoStart
)

$ErrorActionPreference = "Stop"
$Dest = "C:\sixteen\brain"
$Manifest = "$Dest\mesh-install.json"

Write-Host "[MESH INSTALL] Source: $Source" -ForegroundColor Cyan
Write-Host "[MESH INSTALL] Dest:   $Dest" -ForegroundColor Cyan

if (-not (Test-Path $Source)) { throw "Source not found: $Source" }
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

Copy-Item "$Source\*" -Destination $Dest -Recurse -Force
Write-Host "[MESH INSTALL] Files copied." -ForegroundColor Green

$manifest = @{
    installed_at = (Get-Date).ToString("o")
    source       = $Source
    dest         = $Dest
    autostart    = [bool]$AutoStart
    files        = @((Get-ChildItem $Dest -Recurse -File |
        Select-Object FullName, Length))
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content $Manifest -Encoding UTF8
Write-Host "[MESH INSTALL] Manifest written: $Manifest" -ForegroundColor Green

if ($AutoStart) {
    $taskName = "PrimeBrain"
    $action = New-ScheduledTaskAction -Execute "cmd.exe" `
        -Argument "/c C:\sixteen\brain\start_brain.bat"
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME `
        -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName $taskName -Action $action `
        -Trigger $trigger -Principal $principal -Force | Out-Null
    Write-Host "[MESH INSTALL] Logon task registered: $taskName " -ForegroundColor Yellow
    Write-Host "  (created by YOUR explicit -AutoStart flag, logged in manifest)"
} else {
    Write-Host "[MESH INSTALL] No autostart (flag not passed). Start by hand:" -ForegroundColor Yellow
    Write-Host "  C:\sixteen\brain\start_brain.bat"
}

Write-Host "[MESH INSTALL] DONE. Uninstall anytime: .\uninstall-mesh.ps1" -ForegroundColor Green
