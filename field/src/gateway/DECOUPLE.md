# DECOUPLE.md — the decoupling manifest

**Doctrine:** sever dependence on their APIs; put our own API in front of
everything. One sovereign surface, our keys, our audit.

Every external API/network dependency found across the stack
(surveyed 2026-10-15 by grepping `https?://`, `api_key`, `urllib`,
socket connects across `prime-brain-build/`, `swarm-orchestrator/`,
`mesh-tracks/unified/`, `asus-node/`, plus the Android app's known
expectations). Three verdicts:

- **SOVEREIGN** — already ours (loopback, his server, our code). Keep.
- **REPLACED** — a sovereign equivalent exists; the external call is cut.
- **GATEWAYED** — legitimate web need; goes through the gateway's
  egress control: allow-listed domain + declared purpose + requesting
  capability, every call logged. Default-deny otherwise.
- **REMOVED** — unnecessary; cut.

---

## 1. Model / intelligence rungs

| # | Dependency | Where | Verdict | Terms |
|---|-----------|-------|---------|-------|
| 1 | Ollama `http://localhost:11434` (chat, tags) | `entity.py`, `provider_router.py`, `workers/diagnostics_worker.py` | **SOVEREIGN** | Loopback. Our models, our machine. Unchanged. |
| 2 | Gemini `generativelanguage.googleapis.com` | `provider_router.py` (chat rung), Seer vision in the v32 Android app | **GATEWAYED** | Frontier quality cannot be matched by the local 7B yet — stated plainly, not pretended. Allow-listed for capabilities `seer.vision`, `model.chat` only. Every call logged. Replacement path: a local vision model on his hardware; then this row becomes REMOVED. |
| 3 | OpenAI-compatible `CLOUD_API_URL` (default `api.openai.com`) | `entity.py`, `provider_router.py` | **GATEWAYED** | Spare rung, skipped entirely when key/model unset (his key, his choice). If he configures a non-OpenAI endpoint (his own server), that host replaces this row as SOVEREIGN. |
| 4 | `HF_PROVIDER_ORDER` default `gemini,openai,ollama` | `provider_router.py` | **REPLACED** | Default order is re-declared sovereign-first: `ollama` primary, cloud rungs only on explicit per-request opt-in. Local is the default; their APIs are the exception. (Config change, no code cut needed.) |

## 2. Web access (research)

| # | Dependency | Where | Verdict | Terms |
|---|-----------|-------|---------|-------|
| 5 | SearXNG `http://localhost:8888` | `workers/web_worker.py` | **SOVEREIGN** | His own metasearch on loopback. First search backend. Unchanged. |
| 6 | DuckDuckGo `lite.duckduckgo.com` | `workers/web_worker.py` | **GATEWAYED** | Keyless fallback when SearXNG is down. `web.search` only. Logged. |
| 7 | Wikipedia `en.wikipedia.org/w/api.php` | `workers/web_worker.py` | **GATEWAYED** | Keyless, reliable. `web.search`/`web.fetch` only. Logged. |
| 8 | `web.fetch` arbitrary URLs | `workers/web_worker.py` | **GATEWAYED** | Inherent to research — can't be replaced, so it's controlled: must flow through `POST /egress/fetch` (allow-list + SSRF guard + log). Direct `urllib` in workers is the migration: workers import the `egress` shim (`SOVEREIGN_GATEWAY` set) instead of calling out directly. |
| 9 | `browse.open` Playwright, arbitrary pages | `workers/browse_worker.py` | **GATEWAYED** | Declared capability, logged per open. Shared-profile risk from the six-gap review is unchanged and still his to accept; the gateway at least makes every open auditable. |

## 3. Forge (code)

| # | Dependency | Where | Verdict | Terms |
|---|-----------|-------|---------|-------|
| 10 | GitHub REST `api.github.com` (issues) | `swarm-orchestrator/swarm_orchestrator/forge_repo.py` | **GATEWAYED** | Mirror direction ONLY. `forge.issue.*` capabilities. Logged. |
| 11 | `github.com` git push/pull | `forge_repo.py` | **GATEWAYED** | Mirror direction ONLY. `forge.repo.sync`. Logged. |
| 12 | Gitea REST + git (his URL) | `forge_repo.py` | **SOVEREIGN** | His server. Source of truth. The gateway builds its allow-list entry from his configured `GITEA_URL` at runtime — no hardcoded host. |
| 13 | `gh` CLI auth | `forge_repo.py` | **SOVEREIGN** | Local credential helper on his machine. Unchanged. |

## 4. Install-time only (not runtime)

| # | Dependency | Where | Verdict | Terms |
|---|-----------|-------|---------|-------|
| 14 | `winget install Python.Python.3.12` | `asus-node/Install-SovereignNode.ps1`, gateway installer | **INSTALL-TIME** | Not a runtime dependency. Documented; the stack never calls winget after install. |
| 15 | `https://www.python.org/downloads/` (manual fallback link) | installer text | **INSTALL-TIME** | A printed URL for his hands, not a call the system makes. |

## 5. Mesh & node

| # | Dependency | Where | Verdict | Terms |
|---|-----------|-------|---------|-------|
| 16 | Mesh transport (TCP dial) | `mesh-tracks/unified/transport/` | **SOVEREIGN** | Loopback/LAN only, our own from-spec crypto (X25519, XSalsa20-Poly1305, Blake2b KDF), forward secrecy, in-place rekey. No external API anywhere in the path. |
| 17 | Node health/terminal/box ports | `asus-node/bin/` | **SOVEREIGN** | Loopback-only by config (`bind: 127.0.0.1`; node.py refuses anything else). Now fronted by the gateway — nothing else needs to touch these ports directly. |

## 6. Android app (v32, from build context — source not on disk)

| # | Dependency | Where | Verdict | Terms |
|---|-----------|-------|---------|-------|
| 18 | App → brain `http://<lan>:18081` (`/status`, `/chat`, `/activity`) | Sovereign ONE v32 | **REPLACED** | The app points at the gateway (`:18080`) with the phone-scoped gateway key instead of the brain directly. One key, one surface, full audit. Brain keeps its own key as defense-in-depth; the gateway holds it. |
| 19 | Seer vision → Gemini (AI Studio key in app settings) | Sovereign ONE v32 Seer card | **GATEWAYED** | On-device call today. Honest limit: local 7B has no vision; frontier quality stays until a local vision model lands. Migration path: Seer calls `POST /egress/relay` to `generativelanguage.googleapis.com` through the gateway so every vision call is allow-listed and logged — instead of leaving the phone silently. |

---

## What remains GATEWAYED and why (the honest list)

1. **Frontier model quality** (rows 2, 3, 19). The local 7B cannot match
   it yet. We don't pretend otherwise; we log every call and keep the
   local rung primary.
2. **Keyless web search/fallbacks** (rows 6, 7). No account, no key, no
   extraction contract — but still their servers. Allow-listed, logged,
   SearXNG-first.
3. **Arbitrary research fetch/browse** (rows 8, 9). The job *is* the web;
   control means audit + SSRF guard, not blocking.
4. **GitHub as mirror** (rows 10, 11). Distribution needs it; authority
   doesn't live there. Gitea is the source of truth.

## Enforcement

- The gateway is the only process that needs to reach the subsystem
  ports; subsystems stay loopback-only behind it.
- Default-deny egress: `gateway/allowlist.py` is the single list. Any
  host not on it is refused AND logged (`verdict: DENIED`).
- Workers migrate from direct `urllib` to the `egress` shim:
  `SOVEREIGN_GATEWAY=http://127.0.0.1:18080`
  `SOVEREIGN_GATEWAY_KEY=<laptop key>` — then `from egress import fetch`
  routes through the gateway. Without the env vars, the shim enforces
  the same allow-list locally. No worker is rewritten in this pass;
  the shim is the migration path and the manifest is the policy.
- The audit log (`data/audit.jsonl`, hash-chained) records every
  request the gateway serves — including denials. Verify any time:
  `python gateway/gateway.py --verify-audit`.

## Gaps (stated, not hidden)

- Worker migration (row 8) is a path, not a cutover: `web_worker.py`
  still calls `urllib` directly until it's pointed at the shim.
- The gateway's public bind is opt-in and plaintext; TLS termination
  in front of it is his network's job (documented in README).
- `credstore.py`'s Win32 signatures and actual scheduled-task
  registration are unverifiable from the build VM — first Windows run
  is watched, as always.
- Seer-on-device (row 19) still calls Gemini directly until the app
  update routes it through the gateway.
