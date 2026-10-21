# Sovereign Gateway

DECOUPLE from their web. RECONNECT on our terms — with our own API.

One unified REST API fronting every subsystem. One auth (keys WE mint on
his machine). One hash-chained audit log. The gateway is the only surface
the phone — or anything — talks to; brain, orchestrator, node stay
loopback-only behind it.

## Layout

```
sovereign-gateway/
  gateway/
    gateway.py    the server (127.0.0.1:18080, stdlib only)
    keystore.py   mint / verify / revoke, scoped keys (phone|laptop|witness)
    audit.py      hash-chained request log, verify any time
    allowlist.py  egress allow-list: default-deny
    egress.py     sanctioned web path + worker shim
  tests/test_gateway.py   25 tests, all green
  DECOUPLE.md     the manifest: every external dependency + verdict
  GATEWAY.md      architecture
  Install-Gateway.ps1 / Uninstall-Gateway.ps1 / services/run-gateway.ps1
```

## Routes

| Route | Behind it |
|---|---|
| `GET /ping` | liveness, no key (still audited) |
| `GET /status` | gateway health + audit head |
| `/brain/*` | `127.0.0.1:18081` — gateway injects the brain's `X-API-Key` from `brain.key`, so the phone needs only ONE key |
| `/orchestrator/*` | `127.0.0.1:18082` |
| `/node/health`, `/node/mesh` | `:18090`, `:18091` |
| `/node/box/*`, `/node/terminal/*` | `:18083`, `:18088` |
| `/forge/*` | translated to orchestrator `forge.repo.*` / `forge.issue.*` tasks |
| `/egress/fetch`, `/egress/search`, `/egress/relay` | the ONLY sanctioned path to the web (allow-list + SSRF guard + log) |
| `/keys/mint`, `/keys/revoke`, `/keys/list` | laptop scope only |

Auth header: `X-Gateway-Key`. Default bind loopback-only; public bind is
opt-in via `SOVEREIGN_GATEWAY_PUBLIC=1` (plaintext — put TLS in front).

## His-side install (Windows)

1. Extract this folder (as `payload/gateway/`) next to the stack pack.
2. Right-click `Install-Gateway.ps1` → Run with PowerShell.
3. Copy the three printed keys (phone / laptop / witness) — shown ONCE.
4. The phone app uses the PHONE key as `X-Gateway-Key` and talks to the
   gateway — not to the brain directly. The gateway is loopback-only by
   default; the phone reaches it either through the LAN bridge he
   already runs, or by opting into the public bind
   (`SOVEREIGN_GATEWAY_PUBLIC=1` — plaintext, TLS is his network's job).

## Stage 5 drop-in for Install-Sovereign.ps1

Do NOT modify the master script yet. When ready, append this stage
after the forge stage (it calls the gateway installer the same way the
other stages call theirs):

```powershell
# ---- Stage 5: sovereign gateway ----
Write-Step "Stage 5/5: sovereign gateway"
$gw = Join-Path $StageDir "gateway\Install-Gateway.ps1"
if (Test-Path $gw) {
  & $gw -SkipPrompts:$SkipPrompts
  if ($LASTEXITCODE -ne 0) { throw "gateway stage failed" }
  Invoke-RestMethod "http://127.0.0.1:18080/ping" -TimeoutSec 5 | Out-Null
  Write-Host "  gateway: GREEN (127.0.0.1:18080)"
} else {
  Write-Host "  gateway payload missing; skipping" -ForegroundColor Yellow
}
```

`$StageDir\gateway\` = this folder copied into the stack pack as
`payload/gateway/`.

## Audit

Every request is chained into `data/audit.jsonl`. Verify:

```
python gateway/gateway.py --verify-audit
```

## Egress policy

`gateway/allowlist.py` is the single list. Default-deny; denials are
logged with `verdict: DENIED`. The full per-dependency verdicts are in
`DECOUPLE.md`. Workers migrate from direct `urllib` to the `egress`
shim (`SOVEREIGN_GATEWAY` + `SOVEREIGN_GATEWAY_KEY` env).
