# PRIME Brain — operator manual

Local agent system for Zachary's Windows laptop. Deterministic kernel,
tool workers, capsule-driven entity (Ollama `qwen2.5:7b`), LAN API on 18081.

## Layout

```
C:\sixteen\brain\
├── kernel.py, memory.py, entity.py, server.py
├── workers\  (shell, fs, browse, web, notes, diagnostics, capsule)
├── start_brain.bat
├── install-mesh.ps1 / uninstall-mesh.ps1
├── CRAYDON-CAPSULE.json   <- you place this by hand
├── audit.log              <- hash-chained event log (runtime)
└── memory.jsonl           <- hash-chained session memory (runtime)
```

## Internet access + cloud spare rung

- `web.search` / `web.fetch`: keyless web access. Search tries DuckDuckGo
  first, falls back to Wikipedia's API. No key, no account.
- Cloud model rung (optional): the entity runs the local Ollama model first.
  If it's unreachable AND you've set these env vars, it falls back to a
  cloud model (OpenAI-compatible API). Empty = rung skipped, local only.

```powershell
$env:CLOUD_API_KEY="your-key"
$env:CLOUD_MODEL="gpt-5"   # or any OpenAI-compatible model id
$env:CLOUD_API_URL="https://api.openai.com/v1"   # default
```

Local stays primary. The cloud is a spare tire, not the engine.

## First run

```powershell
cd C:\sixteen\brain
python kernel.py --self-test     # must print SELF-TEST GREEN
# place CRAYDON-CAPSULE.json here (v1.2.0, from Muse)
.\start_brain.bat
```

Verify:

```powershell
curl http://localhost:18081/status
```

## API

- `GET /status` — health, capsule mode, workers, audit head hash
- `POST /chat` — `{"text": "...", "session": "..."}` → entity reply
- `POST /consolidate` — fold session memory into facts
- `POST /approve` — `{"task_id": "..."}` — approve a destructive action

## Firewall

Allow Python on **private networks only**. The phone reaches
`http://192.168.4.21:18081` on the home Wi-Fi.

## Boundaries (architectural)

- Defensive only. No offensive action, no unauthorized access, no retaliation.
- The system never installs persistence for itself and never copies itself.
  Boot-start is YOUR explicit scheduled task, never code-driven.
- Destructive actions (file delete, writes outside roots) need `POST /approve`.
- No credential autofill, no login bypass, no dotfile writes.
- Unsigned/missing capsule → LIMITED mode, stated on every reply.
- Every task hits the hash-chained audit log. `diag.check` verifies the chain.

## Mesh (other machines)

```powershell
.\install-mesh.ps1 -Source "E:\brain-backup"        # explicit copy
.\install-mesh.ps1 -Source "E:\brain-backup" -AutoStart   # + logon task, your flag
.\uninstall-mesh.ps1                                # full removal, verified
```
