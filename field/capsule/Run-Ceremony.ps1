# Run-Ceremony.ps1 — the production key ceremony, on Zachary's hardware.
#
# Run this ONCE, with your witnesses present, on the machine the field
# will live on. It:
#   1. births the signing keypair in .\ceremony-keys (never overwrites
#      a born key),
#   2. shows the fingerprint and waits for your witnesses,
#   3. signs .\CRAYDON-CAPSULE.json (or -CapsulePath) with that key,
#   4. verifies the signature and prints the birth certificate.
#
# The private key never leaves this machine. Send back ONLY the
# fingerprint. Full explanation: CEREMONY.md.
param(
    [string]$CapsulePath = "$PSScriptRoot\CRAYDON-CAPSULE.json",
    [string]$Signer = ""
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { $py = (Get-Command python3 -ErrorAction SilentlyContinue) }
if (-not $py) {
    Write-Host "Python 3 not found on PATH. Install it, reopen PowerShell, run again."
    exit 1
}
if (-not (Test-Path $CapsulePath)) {
    Write-Host "Capsule not found: $CapsulePath"
    Write-Host "Build it first from the canonical seeds:  python build_capsule.py --out `"$CapsulePath`""
    exit 1
}
if (-not $Signer) {
    $Signer = "Zachary Dakota Hulse — production key ceremony, $env:COMPUTERNAME, witnesses present"
}

$keyDir = Join-Path $PSScriptRoot "ceremony-keys"
$priv = Join-Path $keyDir "ceremony-private-key.hex"

if (Test-Path $priv) {
    Write-Host "A key already exists in ceremony-keys — reusing it (a born key is never overwritten)."
} else {
    Write-Host "=== STEP 1: the key is born ==="
    & $py.Source ceremony.py keygen --out-dir $keyDir --label "PRODUCTION — born on $env:COMPUTERNAME"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$pub = Get-Content (Join-Path $keyDir "ceremony-public.json") | ConvertFrom-Json
Write-Host ""
Write-Host "FINGERPRINT: $($pub.fingerprint_sha256)"
Write-Host ""
Write-Host "=== STEP 2: witnesses ==="
Write-Host "Back up ceremony-keys\ceremony-private-key.hex to your offline media now."
Read-Host "When your witnesses are present and the backup is done, press Enter"

Write-Host ""
Write-Host "=== STEP 3: signing ==="
& $py.Source ceremony.py sign --capsule $CapsulePath --key $priv --signer $Signer
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "=== STEP 4: verify + birth certificate ==="
& $py.Source ceremony.py verify --capsule $CapsulePath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$hash = (Get-FileHash $CapsulePath -Algorithm SHA256).Hash
Write-Host ""
Write-Host "BIRTH CERTIFICATE"
Write-Host "  capsule:     $CapsulePath"
Write-Host "  capsule sha256: $hash"
Write-Host "  fingerprint: $($pub.fingerprint_sha256)"
Write-Host "  signer:      $Signer"
Write-Host ""
Write-Host "Send back ONLY the fingerprint. The private key never travels."
