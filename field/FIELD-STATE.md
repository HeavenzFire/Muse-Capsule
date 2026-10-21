# FIELD STATE — VM proving-ground instance

Verified live: 2026-10-21 ~06:10 CDT. Supervisor: systemd unit
`unified-field` running `field/supervise.sh` (recovery: `field/boot.sh`).

## ALIVE (health-checked, not assumed)

| node | endpoint | evidence |
|---|---|---|
| prime-brain | 127.0.0.1:18081 | /status ok, 7/7 workers healthy, audit chain ok (58 entries at last check) |
| node | 127.0.0.1:18090 | /node-health ok; supervises mesh-daemon child |
| mesh | 127.0.0.1:18091 | /mesh-health ok, coherence_R 1.0, own node_id + pubkey |
| orchestrator | 127.0.0.1:18082 | /status ok; /task executes through gates -> prime -> ledger (field/orchestrator_server.py) |
| gateway | 127.0.0.1:18080 | /ping ok; /brain/status proxied with phone key -> full chain proven |

## Repairs made 2026-10-21

1. **Central execution path (the break GPT's assessment pointed at):**
   measured live — POST /chat died at the model router ("all rungs
   failed: gemini=auth") so deterministic workers NEVER executed.
   Fix: `POST /task` added to prime-brain-build/server.py — direct
   kernel dispatch by capability, no model rung required; worker-side
   gates (approval, allowlists) unchanged. Backup: server.py.bak-20261021.
   Proof: diag.check + fs.list execute, return, and settle into the
   hash-chained audit (entries 17 -> 46+ during testing); the same
   canonical task_id (e233c7deb4445963) is produced by both the brain
   path and the orchestrator path.
2. **Orchestrator HTTP face:** field/orchestrator_server.py (stdlib,
   loopback) — the manifest's 18082/status + /task now exist.
3. **Durability:** services first died with the exec sessions that
   launched them (nohup was not enough). Now under systemd +
   supervisor restart loops. Kill test: brain SIGTERM -> back in ~2s,
   chain verified intact.

## DARK (honest reasons)

- **ollama / local mind (11434):** no binary on this VM (wiped by a past
  redeploy; installs outside ~ do not survive). The heavenzfire model
  lives on Zachary's ASUS. Brain runs LIMITED mode until a rung exists.
- **The Sixteen (16 agents):** Rust binary; needs cargo on his hardware.
  DARK by design in the manifest; never faked ALIVE.

## Known remaining gaps (his priority list, 2026-10-21)

- P2 unify surfaces: dashboard / AI IDE / voice / camera are not yet
  gateway clients. The gateway path is proven; the surfaces are not.
- P3 durability: kernel result cache is in-memory; a task in flight at
  kill time is ledgered but not resumed after restart. Retries exist
  inside kernel.submit (max_retries + quarantine).
- P4 R&D loop: not yet standing as a continuous cycle.

## Keys

- brain.key: prime-brain-build/brain.key (this instance; pre-existing).
- gateway keys: field/gateway-keys.txt (chmod 600) — minted on this VM
  for this proving-ground instance only. NOT production keys.
