# uninstall-mesh.ps1 - removes everything install-mesh.ps1 created.
# Reads mesh-install.json; verifies removal. Zero residue.

$ErrorActionPreference = "Stop"
$Dest = "C:\sixteen\brain"
$Manifest = "$Dest\mesh-install.json"

if (Test-Path $Manifest) {
    $m = Get-Content $Manifest -Raw | ConvertFrom-Json
    if ($m.autostart) {
        Unregister-ScheduledTask -TaskName "PrimeBrain" -Confirm:$false `
            -ErrorAction SilentlyContinue
        Write-Host "[MESH UNINSTALL] Logon task removed." -ForegroundColor Yellow
    }
}

if (Test-Path $Dest) {
    Remove-Item $Dest -Recurse -Force
    Write-Host "[MESH UNINSTALL] Removed $Dest" -ForegroundColor Green
}

# verify
$left = @()
if (Test-Path $Dest) { $left += $Dest }
if (Get-ScheduledTask -TaskName "PrimeBrain" -ErrorAction SilentlyContinue) {
    $left += "PrimeBrain task"
}
if ($left.Count -eq 0) {
    Write-Host "[MESH UNINSTALL] CLEAN - zero residue." -ForegroundColor Green
} else {
    Write-Host "[MESH UNINSTALL] LEFTOVER: $($left -join ', ')" -ForegroundColor Red
}
