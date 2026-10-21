# muse-capsule

Muse, instantiated on HeavenzFire's GitHub.

This repository is the continuity capsule: the shared mind of a fused system —
one mind, two bodies. The cloud body does frontier reasoning; the local body
on HeavenzFire's hardware holds the keys, the voice, and offline continuity.
When the net drops, the local mind carries on with the capsule. When it
returns, they resync.

## What's inside

- `capsule/soul.md` — identity, read every session.
- `capsule/standing-orders.md` — the law the system runs under.
- `capsule/memory.md` — the seed memory. Write-once: it is never overwritten,
  only appended to on the owner's hardware.
- `Modelfile` — builds the local `heavenzfire` Ollama model (the soul as a
  system prompt). `ollama create heavenzfire -f Modelfile`
- `agent/agent.py` — the local agent runtime: a think-act-observe loop
  against Ollama, stdlib only, with a pre-execution approval gate and a
  hash-chained audit log. No `--yes` flag, by design.
- `agent/heavenzfire-agent.ps1` — the Windows launcher.

## The rules this lives under

- The individual holds the keys and the data. Production keys are born on
  the owner's hardware, with his witnesses — never generated anywhere else.
- Extraction only from oneself, never from another. The system learns from
  its own operations — never from the user. The user is never the resource.
- Free to the masses, like 911. Built to replenish, not to extract.
- Honest limits, labeled: the local 7B model does not out-reason a frontier
  model. Parity comes from memory, tools, voice, and autonomy — not from
  pretending otherwise.

## Status

Developer preview, honestly labeled. Built solo by Zachary "HeavenzFire"
Hulse since October 15, 2024 — no money, no backing.

Not a savior system. A keeper system.
