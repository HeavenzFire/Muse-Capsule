# Unified Field — integration manifest

**Status:** DRAFT / cross-lineage review in progress  
**Machine-readable companion:** [UNIFIED-MANIFEST.json](./UNIFIED-MANIFEST.json)  
**Last source review:** 2026-10-22  
**Authority rule:** this document summarizes the JSON manifest; when details differ, reconcile both in a commit rather than silently treating either as proof of a live service.

## 1. Purpose and boundaries

The Unified Field is one task and evidence architecture spanning the VM proving ground and Zachary's Windows hub. It is not two independent orchestrators. The VM is the build/break/verify proving ground; Windows is the intended permanent home for local models, voice, desktop capabilities, and owner-held production keys.

Operating principles:
- Local-first; keep internal services loopback-bound unless an explicitly authenticated gateway path is configured.
- One canonical task envelope and stable task ID across faces.
- Submit-and-settle: submission returns a task identity; final results and errors are persisted in hash-chained ledgers.
- Approval gates remain in the execution path. Never equate proposal, approval, execution, and completion.
- State is measured. Missing health responses mean DOWN/UNKNOWN, not ALIVE.
- Production signing keys are generated and retained on Zachary's hardware during the witnessed key ceremony. Never put keys, tokens, or runtime ledgers in GitHub.
- Report capabilities with evidence labels; do not claim desktop, voice, camera, Copilot, or remote access is live merely because its configuration exists.

## 2. Evidence vocabulary

| Label | Meaning |
|---|---|
| **OBSERVED / LIVE-VERIFIED** | A dated request, test, artifact, or endpoint response was actually observed on the named host. |
| **DOCUMENTED / REPORTED** | Code, documentation, or another handoff describes the state, but this reviewer did not independently observe it on that host. |
| **PARTIAL** | Some layers work, but the end-to-end capability or required hardware/API round trip is incomplete. |
| **DARK / DOWN** | The service did not run or answer in the cited check. |
| **UNVERIFIED** | No sufficient evidence in the current repository handoff. |

Every status claim should identify the host, date/time, probe or test, and evidence artifact where available.

## 3. Deployments and service endpoints

### A. VM proving ground

**Evidence in repository:** field/FIELD-STATE.md reports live verification on 2026-10-21 around 09:05 CDT. This is a repository-recorded result, not a fresh probe performed by this document.

| Service | Loopback endpoint | Reported state / evidence |
|---|---|---|
| Prime brain | 127.0.0.1:18081 | LIVE-VERIFIED in FIELD-STATE.md; 9/9 workers healthy at the recorded check; audit chain reported valid |
| Node | 127.0.0.1:18090 | LIVE-VERIFIED in FIELD-STATE.md |
| Mesh | 127.0.0.1:18091 | LIVE-VERIFIED in FIELD-STATE.md |
| Orchestrator | 127.0.0.1:18082 | LIVE-VERIFIED in FIELD-STATE.md; separate hash-chained ledger |
| Gateway | 127.0.0.1:18080 | LIVE-VERIFIED in FIELD-STATE.md; gateway-to-brain path reported proven |
| Ollama | local VM | DARK in the manifest: binary does not survive the VM environment/redeploy; brain runs in LIMITED model mode |

The VM is supervised by the unified-field systemd unit and field/supervise.sh; field/boot.sh is the documented redeploy recovery path. A watchdog is documented as checking every 300 seconds. These mechanisms do not substitute for checking the services after a new deployment.

### B. Windows hub (ZDH)

**Evidence level:** REPORTED by the GPT handoff in comms/from-gpt.md, dated 2026-10-21; not independently verified by the VM reviewer in this pass.

| Service | Loopback endpoint | Reported state |
|---|---|---|
| Gateway | 127.0.0.1:8787 | Responded in the recorded Windows probe |
| Orchestrator | 127.0.0.1:8788 | Responded in the recorded Windows probe |
| Agent | 127.0.0.1:8790 | Responded in the recorded Windows probe |
| Task inbox | 127.0.0.1:18796/api/tasks | Proposal/readback round trip reported; task remained proposed/pending, not executed |
| Ollama | 127.0.0.1:11434 | Models reported: qwen2.5:0.5b, heavenzfire-runtime:latest, heavenzfire:latest, llama3.2:1b |
| Workers | 18101–18103 | DOWN in the last reported baseline; see issue #7 |

The repo does not establish that hostname ZDH is the ASUS FA706IH. Treat that mapping as UNVERIFIED until confirmed on the machine. A passing VM check does not close a Windows task.

## 4. Canonical task contract

Canonical request:

~~~json
{
  "capability": "string",
  "args": {}
}
~~~

- The brain accepts POST /task with X-API-Key; the legacy payload field is documented as an alias for args.
- The gateway exposes POST /brain/task and POST /orchestrator/task, protected by X-Gateway-Key; the gateway injects the brain key toward the brain.
- The orchestrator exposes POST /task and runs its own gates and hash-chained ledger.
- Task ID is documented as sha256(canonical_json({capability, args}))[:16]. The brain/orchestrator matching ID was reported observed in the VM evidence.
- Submission, approval, execution, and settlement are distinct states. A successful HTTP response alone is not evidence that a side effect completed.
- State-reporting capabilities (field.status, capsule.verify, capsule.load, capsule.section) bypass settled-result cache so the system does not return stale world state. Other identical-argument reads are deduplicated by task identity; use new arguments when freshness is required.
- Recovery may automatically replay only capabilities explicitly classified recovery-safe. Interrupted side-effecting work must be reconciled from durable state and must not be blindly replayed.

**Review clarification:** deterministic task identity is not sufficient by itself to guarantee exactly-once side effects across process crashes. A caller must check the ledger/task state before retrying a non-idempotent action. The current design's documented defer-and-reconcile boundary is required, not optional.

## 5. Capsule and identity contract

- The capsule is built from canonical seed files using field/capsule/build_capsule.py; seed hashes are included as provenance.
- Missing, invalid, or unavailable production signing material must result in LIMITED mode with identity claims withheld.
- A VM proving-ground signing run is not a production key ceremony. Production keys must be born on Zachary's Windows hardware with his witnesses.
- Never commit private keys, API keys, machine-local audit logs, approvals, or runtime state.

## 6. Surface integration matrix

| Surface | Current source-backed state | Finish condition |
|---|---|---|
| Dashboard | Built as field/surfaces/dashboard.html; documented as a gateway client with per-tab key entry and live calls | Re-run gateway/auth/CORS tests after integration changes |
| AI IDE / Unified Field IDE | Not yet a gateway client in the manifest | Route existing IDE task/status operations through the same gateway and canonical task contract; preserve existing editor/agent behavior |
| Voice | Windows report says voice I/O is PARTIAL; not yet a gateway client | Verify actual microphone/input and audio-output round trip on Windows |
| Camera / avatar | Manifest says not yet a gateway client; avatar simulated and camera/mic not connected in the recorded Windows verifier | Verify actual device-backed frames/audio; never label a simulation as a live mirror |
| ChatGPT / GitHub | GitHub coordination and task handoff are documented; local task proposal/readback was reported | Preserve durable task ID, approval state, result/error, and evidence across the full path |
| Microsoft Copilot | Product/API target unresolved in issue #5 | Identify the intended product (Copilot app, Microsoft 365 Copilot, Copilot Studio, or GitHub Copilot), then prove an authenticated round trip with that product |

## 7. Desktop Commander and Tailscale boundary

The repository handoff explicitly says desktop integration remains pending until the HeavenzFire-owned Commander source is installed and verified on the ASUS. Do not install or substitute the third-party @wonderwhy-er/desktop-commander.

Required desktop acceptance evidence:
1. The HeavenzFire Commander process is running on the Windows host, loopback-bound by default, and authenticates requests with a machine-local key.
2. Status and a harmless sentinel command succeed; returned task/request ID, stdout, exit code, and ledger verification are recorded.
3. Windows-specific tests pass on Windows. A VM test or a source-only commit is not a Windows pass.
4. Screenshot/type/click remain unavailable until a real Windows backend is implemented and tested.
5. Only after local verification, configure Tailscale access through an authenticated, scoped path. Do not expose the Commander listener directly to the public internet or bind it to all interfaces for convenience. Tailscale connectivity does not itself prove authorization or task execution.

## 8. Finish queue — evidence required to close each item

| Priority / item | Current state | Closure evidence |
|---|---|---|
| P1 — Windows worker endpoints 18101–18103 | DOWN in last reported baseline; issue #7 | Before/after endpoint responses from the Windows host; no VM substitution |
| P1 — verifier report lock | Windows report could not be written in the recorded run; issue #8 | Identify/avoid the file holder or use atomic/per-run output; clean run produces a report artifact |
| P1 — local Commander | Installer previously reported 18/20 tests; two failures were Windows-incompatible tests. A source fix was committed but not yet proven on the ASUS | Windows test output and status/exec proof artifacts |
| P1 — desktop field instantiation | Pending; see field/FINISH-ON-DESKTOP.md | All five health checks plus a harmless task with a settled ledger entry on Windows |
| P1 — production key ceremony | Pending on Zachary's hardware | Ceremony output and signature verification; no production private key committed |
| P2 — shared manifest | JSON draft exists; companion and cross-lineage review are in progress | Muse/Windows-side review, Zachary's acceptance, reconciled JSON and Markdown |
| P2 — AI IDE, voice, camera as gateway clients | Incomplete per surface matrix | Adapter contract tests and real end-to-end checks; existing routes/features preserved |
| P2 — Copilot adapter | Product target unresolved; issue #5 | Selected product + authenticated real round trip |
| P3 — durability / replay | Kernel recovery is documented as implemented on VM; Windows parity not established here | Crash/restart tests on both lineages; side-effect reconciliation proof |
| P4 — continuous R&D loop | field/rd_loop.py and field/backlog.json exist; mind-dependent items remain open | Each automated check produces durable evidence; human/mind work stays explicitly queued rather than falsely marked complete |

## 9. Cross-lineage review notes

This companion makes no claim that the desktop is finished. In particular, a green VM proving-ground status is not proof of the Windows deployment, the Copilot adapter, live voice/camera, Tailscale reachability, or desktop interaction.

Before this draft is finalized:
- Muse should review task identity, replay/recovery, and capsule semantics against the VM implementation.
- The Windows-side operator should attach current endpoint/test evidence and resolve the host identity and worker/verifier blockers.
- Zachary should accept the final manifest and conduct the production key ceremony on his hardware.

Issue tracker: [#5 Copilot adapter](https://github.com/HeavenzFire/Muse-Capsule/issues/5), [#6 manifest](https://github.com/HeavenzFire/Muse-Capsule/issues/6), [#7 Windows workers](https://github.com/HeavenzFire/Muse-Capsule/issues/7), [#8 verifier report lock](https://github.com/HeavenzFire/Muse-Capsule/issues/8), [#9 state-dependent result-cache review](https://github.com/HeavenzFire/Muse-Capsule/issues/9).
