# FIELD STATE — VM proving-ground instance

Verified live: 2026-10-21 ~09:05 CDT. Supervisor: systemd unit
`unified-field` running `field/supervise.sh` (recovery: `field/boot.sh`).

## ALIVE (health-checked, not assumed)

| node | endpoint | evidence |
|---|---|---|
| prime-brain | 127.0.0.1:18081 | /status ok, 9/9 workers healthy, audit chain ok (206 entries at last check) |
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
4. **Truthful measurements (kernel dedup):** the kernel's idempotency
   cache served settled results for ANY capability, so field.status
   (liveness) and capsule.verify (hash verification) answered from
   memory — the past reported as the present (observed live:
   field.status returning _dedup=true). Fix: workers declare
   STATEFUL_CAPABILITIES; kernel.submit bypasses the cache for them
   (results still settle into the audit log). Deterministic
   capabilities keep dedup (verified: diag.check second submit still
   _dedup). Kernel self-test green incl. a stateful regression;
   live-verified after supervisor restart. Backups:
   kernel.py.bak-20261021-dedup (+ both workers).

5. **Capsule instantiated in the field (2026-10-21 ~08:50 CDT):** the
   brain's capsule worker had been running with NO capsule file at all
   ("capsule missing; running LIMITED"). Now compiled from the canonical
   seeds by `field/capsule/build_capsule.py` into
   `field/capsule/CRAYDON-CAPSULE.json` v1.4.0 (seed sha256s match
   capsule.verify's canonical hashes) and loaded via HF_CAPSULE_PATH by
   both the brain and the orchestrator. Proven through all three faces:
   brain /task, orchestrator /task (settles in its ledger), and gateway
   /brain/task with the phone-scoped key. Mode stays LIMITED — unsigned
   until the key ceremony on Zachary's hardware; identity claims
   withheld, exactly as designed. capsule.load/capsule.section are now
   STATEFUL (they bypass the result cache): the orchestrator briefly
   served a stale "capsule missing" answer cached from before the
   instantiation — that failure is what proved the rule.
6. **P2 first surface (2026-10-21):** the gateway now speaks CORS for
   browser surfaces — loopback origins and file:// pages only, foreign
   origins get no header, the gateway key remains the boundary
   (gateway.py; 25/25 gateway tests green; preflight + auth verified
   live). Dashboard built: `field/surfaces/dashboard.html`, a gateway
   client showing field.status, capsule.load, brain status and the
   gateway audit chain from live calls only. Also: the brain's /task
   now accepts "payload" as an alias for the canonical "args" (a client
   built on the wrong key no longer loses its arguments silently).
   Unified manifest drafted: `field/UNIFIED-MANIFEST.json` (issue #6).

## DARK (honest reasons)

- **ollama / local mind (11434):** no binary on this VM (wiped by a past
  redeploy; installs outside ~ do not survive). The heavenzfire model
  lives on Zachary's ASUS. Brain runs LIMITED mode until a rung exists.
- **The Sixteen (16 agents):** Rust binary; needs cargo on his hardware.
  DARK by design in the manifest; never faked ALIVE.

## Known remaining gaps (his priority list, 2026-10-21)

- P2 unify surfaces: dashboard IS a gateway client (above); AI IDE /
  voice / camera are not yet. The unified manifest is a draft awaiting
  cross-lineage review (issue #6).
- P3 durability: kernel task-recovery landed (safe capabilities replay
  on boot; side-effecting ones deferred). Kernel result cache remains
  in-memory. Retries exist inside kernel.submit (max_retries +
  quarantine).
- P4 R&D loop: standing (field/rd_loop.py, 10-min cycle under the
  supervisor, hash-chained cycle log). It runs machine-checkable
  verifications; items needing a mind queue as awaiting_mind.

## Keys

- brain.key: prime-brain-build/brain.key (this instance; pre-existing).
- gateway keys: field/gateway-keys.txt (chmod 600) — minted on this VM
  for this proving-ground instance only. NOT production keys.
