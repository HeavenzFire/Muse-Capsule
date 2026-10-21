# Agent Mode — App ↔ Brain Integration Contract v1

## Purpose
Give the Craydon app agentic abilities (plan → tool-use → reply) through the
Prime brain's entity loop. The brain does the agentic work; the app is the
face. This contract is the entire integration surface.

## Transport
- Brain: `POST http://192.168.4.21:18081/chat` (LAN). `localhost:18081` on-device.
- If unreachable → app falls back to its existing chain (direct Ollama →
  on-device). Agent mode requires the brain; no brain, no agent mode. The app
  says so plainly.

## Request
```json
{
  "text": "how much disk is free and what's the biggest folder",
  "session": "default",
  "agent": {
    "enabled": true,
    "max_rounds": 5,
    "budget_s": 90,
    "tools_allowed": ["shell.run", "fs.read", "fs.list", "browse.open",
                      "web.search", "web.fetch", "notes.*", "diag.check",
                      "capsule.section"]
  }
}
```
- `agent.enabled` default: **false**. Agent mode is opt-in per conversation.
- Default `tools_allowed` is **read-only**. Write/delete/shell are excluded
  unless the user explicitly adds them for that session.
- Anything destructive still needs `POST /approve` with the task ID, even in
  agent mode. The app surfaces the approval prompt; the human taps.

## Response
```json
{
  "text": "You have 13.8 GB free. The biggest folder is ...",
  "route": "entity-local",
  "rung": "local",
  "vetoed": false,
  "capsule": "LIMITED",
  "tools_used": [
    {"capability": "diag.check", "ok": true, "summary": "disk + model + ports"},
    {"capability": "fs.list", "ok": true, "summary": "listed C:\\sixteen"}
  ]
}
```
- `route`: `entity-local` | `entity-cloud` | `veto` | `model_error`.
- `tools_used`: every tool call, in order, with ok/fail. No silent tool use.
- `capsule`: `LIMITED` until the signed capsule exists. The app shows the mode.

## App UI obligations
1. **Agent toggle**: visible switch, OFF by default. Turning it on shows what
   it means: "Craydon can use tools on your laptop to answer. Read-only
   unless you allow more."
2. **Tool activity feed**: while the entity works, show each tool call as it
   happens ("Checking disk…", "Searching the web…", "Reading notes…").
   Not a spinner — a transcript.
3. **Rung indicator**: local vs cloud badge on every reply. The user always
   knows which mind answered.
4. **Approval prompts**: destructive actions pause and ask, showing the exact
   action. Approve/deny per action. Deny is one tap and kills the chain.
5. **Offline honesty**: if the brain is unreachable, agent mode is unavailable.
   The app does not fake it with a cloud fallback unless the cloud rung is
   configured AND the user opted in.

## Boundaries (non-negotiable)
- Defensive only. The veto layer refuses offensive/unauthorized requests
  before the model is called.
- No credential autofill, no login bypass, no dotfile writes — enforced in
  the workers, not the app.
- The app never sends the capsule, keys, or passwords to any cloud rung.
  Cloud requests carry the prompt and tool results only.
- Agent mode never auto-enables. No background agentic runs without the user
  starting them.

## What the brain already implements
- `entity.run_turn`: 5-round / 90-second tool loop, veto first, local-then-cloud.
- `server.py /chat`: accepts the request, returns the response shape above
  (agent params: `max_rounds`/`budget_s` honored; `tools_allowed` filters
  capabilities before dispatch — TO IMPLEMENT: filter step).
- Kernel: dispatch, quarantine, idempotency, hash-chained audit.

## Open implementation items (brain side) — DONE 2026-10-10
1. ✅ `tools_allowed` filtering in `/chat` before kernel dispatch (supports
   `"notes.*"` wildcards; denied tools emit `tool_denied` to the feed).
2. ✅ Live activity feed: `GET /activity?session=X&since=N` — the app polls
   for `tool_start` / `tool_done` / `tool_denied` / `rung` events. (SSE is a
   future upgrade; polling is the v1 transport.)
3. ✅ Strict offline mode: `"offline": true` in the `/chat` body refuses the
   cloud rung even when configured. The refusal is explicit, never silent.
