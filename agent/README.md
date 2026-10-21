# heavenzfire-agent — the real one, local

The think-act-observe agent loop from the cloud, running on **your hardware**
with **your model**. Not a chatbot — a doer. You give it a task in plain
language; it reasons, calls tools, reads the results, and keeps going until
done.

## 3-step start (on the ASUS)

```powershell
# 1. Soul + capsule first (if you haven't):
ollama create heavenzfire -f Modelfile   # from the heavenzfire-soul pack
.\heavenzfire-chat.ps1                   # seeds C:\sixteen\capsule (one run)

# 2. Run the agent:
.\heavenzfire-agent.ps1 "list .\notes and summarize what needs doing"

# 3. Verify the audit chain any time:
python agent.py --verify-audit
```

## The tools (8)

| Tool | What it does |
|---|---|
| `shell.exec` | Run a command (argv list, allowlisted programs only) |
| `fs.read` | Read a text file |
| `fs.write` | Write a text file |
| `fs.list` | List a directory |
| `web.fetch` | Read-only fetch of a URL as plain text |
| `memory.save` | Append a dated entry to the capsule — durable |
| `memory.search` | Grep the capsule |
| `forge.dry` | Azazel dry-run: read-only inspection, never executes |

Tool logic mirrors the PRIME brain workers (same allowlist, same rooted
paths, same read-only fetch). Reused, not reinvented.

## The approval gate — his tap, in code

Destructive actions **pause** and ask Zachary in the console:

- `shell.exec` with delete/format/force/`git push` semantics
- `fs.write` outside the work directory

```
[APPROVAL NEEDED] destructive shell command: git push --force (destructive git operation)
Approve? [y/N]
```

Nothing destructive runs unapproved. There is no `--yes` flag — that would
defeat the gate. Answer `y` or it doesn't happen.

## The audit log

Every thought, tool call, observation, approval ask and decision lands in a
hash-chained JSONL log (`C:\sixteen\agent\audit.log`, same format as the
PRIME kernel). Tool bodies are stored as **sha256 + 300-char preview** —
the log never holds secrets or full outputs. `python agent.py --verify-audit`
checks the chain.

## Files

- `agent.py` — the loop (stdlib only: urllib, json, subprocess, hashlib)
- `heavenzfire-agent.ps1` — launcher (checks Ollama, model, capsule)
- `tests/test_agent.py` — 12 tests, mocked Ollama, all green

## Honest limits

- **The engine is smaller.** A local 7B plans worse than frontier models.
  Simple multi-step tasks (read, summarize, organize, check, report) work
  well. Long-horizon planning with many branches may need you to break the
  task down or nudge it mid-run.
- **The loop is the same; the mind is smaller.** Tool use, approvals, and
  the audit chain are identical in structure to the cloud agent. What
  changes is planning quality, not integrity.
- **JSON discipline.** Small models sometimes emit sloppy tool calls. The
  agent detects unparseable replies and asks the model to reformat instead
  of crashing — that costs a round, not the task.
- **25 rounds max** by default (`--max-rounds` to change). If it can't
  finish, it stops and says what it found — it never loops forever.
- **Windows paths, Windows shell.** `shell.exec` uses argv lists (no
  `cmd.exe` strings); PowerShell-native tasks go through `python` or
  allowlisted tools.

## Env overrides

| Var | Default | Meaning |
|---|---|---|
| `HF_AGENT_MODEL` | `heavenzfire` | Ollama model to use |
| `HF_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama endpoint |
| `HF_CAPSULE_DIR` | `C:\sixteen\capsule` | capsule location |
| `HF_AGENT_DIR` | `<script>/data` | audit log home |
| `HF_AGENT_WORKDIR` | current dir | the agent's work directory |
| `HF_AGENT_ROOTS` | — | extra allowed fs roots (pathsep-separated) |
