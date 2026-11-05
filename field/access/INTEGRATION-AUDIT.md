# HF-Access Existing-Stack Integration Audit

Audit basis: GitHub `main` source files inspected for this task. This is a static source review, not a live deployment test.

## Reuse rather than replace

### Sovereign Gateway

Inspected:
- `field/src/gateway/README.md`
- `field/src/gateway/GATEWAY.md`
- `field/src/gateway/gateway/gateway.py`
- `field/src/gateway/gateway/keystore.py`
- `field/src/gateway/gateway/allowlist.py`

Existing capabilities:
- One gateway fronts brain, orchestrator, node health, mesh health, box, terminal, forge, and egress paths.
- Client API keys have coarse scopes: `phone`, `laptop`, and `witness`.
- Key records are stored as salted SHA-256 hashes; raw keys are emitted only at mint time.
- Revocation is recorded; key administration is restricted to laptop scope.
- Requests are hash-chain audited.
- Loopback is the default bind; public bind is opt-in and explicitly documented as plaintext.

HF-Access decision:
- Reuse the gateway as the application entry point and retain its audit/keystore integration.
- Do not mistake the three client scopes for per-device identity or per-capability authorization.
- Extend only after tests establish the actual route-level scope checks and key lifecycle behavior.
- Do not enable `SOVEREIGN_GATEWAY_PUBLIC=1`. It is plaintext and is not an acceptable remote-access transport.
- Review the existing salted-SHA256 API-key verifier before expanding its use; do not weaken it or treat it as a replacement for device public-key identity.

### Node / mesh

Inspected:
- `field/src/node/mesh-daemon.py`
- `field/src/node/node.py`
- `field/src/node/config.yaml`

Existing mesh-daemon source:
- Creates a persistent 32-byte Ed25519 secret under its data directory with restrictive file permissions and refuses silent regeneration.
- Derives a node identity and stores its public key.
- Starts in self-owned genesis; joining a wider mesh is explicitly described as an out-of-band owner action.
- Exposes a loopback health endpoint and writes a hash-chained local mesh log.
- Supports seed peers, capability labels, periodic attestations, and a reconnect/healer loop.

HF-Access decision:
- Reuse the node's existing identity and attestation model if the underlying transport passes review.
- Preserve owner-controlled admission; do not turn seed-peer reachability into automatic trust.
- Bind each admitted peer identity to an owner-approved enrollment record and explicit capability grant.
- A node health response is not proof of all attached devices' health.

Open source-verification gap:
- `mesh-daemon.py` imports `mesh.transport`, `mesh.node.unified_node`, and `mesh.field.observer`. Those imported package files were not present in the inspected `field/src/node` directory listing. Locate their actual source/deployment package and inspect transport authentication, encryption, replay protection, and peer admission before relying on the mesh as a secure remote transport.

### Orchestrator and policy

Inspected:
- `field/src/orchestrator/swarm_orchestrator/registry.py`
- `field/src/orchestrator/swarm_orchestrator/gates.py`
- `field/orchestrator_server.py`

Existing capability routing and approval gates should remain the execution authority. HF-Access must add device principal and resource-scope checks before task execution; a valid gateway key alone must not authorize arbitrary capabilities.

Static-review issue to resolve before production use:
- The inspected `ZadkielGate` implementation describes default-allow behavior when no deny rule matches. HF-Access device grants must be independently deny-by-default and must not inherit that permissive default.

## Required implementation decisions

1. Find and inspect the actual mesh transport package and its dependency/version provenance.
2. Map gateway route-to-scope checks and existing regression tests.
3. Decide whether the gateway keystore can be extended safely or whether device public-key identities should be verified by the existing mesh trust layer and mapped to gateway principals.
4. Add a durable owner-approved peer registry using the existing ledger/event conventions.
5. Add deny-by-default per-device capability and resource grants at the execution boundary.
6. Add revocation propagation and tests for offline/reconnecting peers.
7. Add a test-only authenticated Windows-to-VM round trip using the existing private network; do not expose the gateway publicly.
8. Only then pilot a read-only IoT telemetry adapter.

## Verification boundary

No runtime was launched and no endpoint was probed during this static review. The repository sources do not establish that the VM, Windows services, mesh transport, or any IoT endpoint is currently online.


## Accelerated implementation review — 2026-11-04

This review expands the static audit against the repository's current `main` tree. It is not a runtime test.

### Confirmed integration facts

- The existing federation contract is at `field/federation/INTEGRATION-CONTRACT.md`; its status model distinguishes discovery, contract verification, and live connected verification. HF-Access should use this contract rather than invent another component lifecycle.
- The existing field manifest and `field/FIELD-STATE.md` are dated historical evidence. They describe a VM proving-ground state from October 2026 and explicitly record Windows services as unmeasured/down at that time. They are not proof of current availability.
- The current `field/src/node` directory contains `mesh-daemon.py`, `node.py`, and `config.yaml`, but not the imported `mesh.transport`, `mesh.node.unified_node`, or `mesh.field.observer` package sources. The mesh daemon therefore cannot be treated as a self-contained, reproducible transport from this repository snapshot. Locate the exact dependency source, version, license, and runtime installation before writing an adapter.
- The mesh daemon's health endpoint binds to loopback, and its seed-peer healing behavior is not a substitute for authenticated transport. Its current source uses an Ed25519 identity object supplied by the missing package; transport guarantees remain unverified.
- The gateway validates an API key before all non-`/ping` routes. The three key scopes are `phone`, `laptop`, and `witness`; inspected route handling passes every authenticated scope to brain, orchestrator, node, forge, and egress proxies. The `laptop` distinction is enforced for key administration, not as a complete per-route/per-capability authorization matrix.
- The orchestrator HTTP face binds to `127.0.0.1`, but its `/task` handler does not authenticate a caller itself. It relies on being reached through a trusted local boundary. Do not expose it directly or interpret loopback binding as device authentication.
- The orchestrator's `ZadkielGate` explicitly defaults to allow when no deny rule matches; the PRIME approval gate only requires recorded approval for capabilities classified as destructive. HF-Access needs a separate device-grant check at a trusted boundary, with principal identity injected by authenticated server-side code—not accepted from caller-supplied task JSON.
- Existing orchestrator tests are in `field/src/orchestrator/tests/test_orchestrator.py`; gateway tests were referenced by historical field notes but were not present under `field/src/gateway` in the inspected directory listing. Locate their actual test source before extending route authorization.
- The repository's current CI workflow `.github/workflows/agent-governance.yml` tests the general agent runtime and policy contract, not the HF-Access Python packages. The reviewed HF-Access head had a successful CodeRabbit status marked “Review skipped”; that is not a test run. No HF-Access-specific CI result was established in this review.

### Consolidated execution plan

Batch A — dependency and boundary closure:
1. Locate the exact mesh transport package and install/build provenance; verify authentication, encryption, replay defense, peer admission, and reconnect behavior.
2. Locate the gateway test suite and run the existing orchestrator and gateway suites in a supported Python 3.11 environment.
3. Freeze the trusted ingress boundary: gateway-authenticated device principal must be derived server-side; never trust a `device_id`, role, scope, or capability list supplied in task JSON.
4. Select one transport for the first Windows-to-VM test based on verified installed components. Prefer the existing private network plus mature TLS/mTLS; do not rely on an undocumented prototype transport.

Batch B — implement once the trust boundary is known:
1. Add durable owner-approved device enrollment and revocation using existing persistence/audit conventions.
2. Add deny-by-default device/resource/capability authorization at the orchestrator execution boundary.
3. Add authenticated heartbeat, freshness, bounded reconnect, and revoked-peer denial.
4. Add task-envelope validation, expiry, idempotency, and evidence correlation.
5. Add regression tests for valid, unknown, expired, revoked, replayed, stale, and unauthorized requests.

Batch C — integrated proving-ground verification:
1. Run the existing gateway/orchestrator regression suites plus new HF-Access tests in CI.
2. Exercise one harmless read-only Windows-to-VM round trip over the approved private network.
3. Verify ledger/audit settlement, revocation, restart, and offline recovery.
4. Only after all checks pass, promote the adapter to `connected-verified` in the existing federation registry and begin an explicitly enrolled, read-only IoT pilot.

### Current stop conditions

- Do not add an access route to the gateway until per-route authorization tests exist; current key scopes do not provide that boundary.
- Do not wire the mesh daemon into HF-Access until its missing imported package is located and transport security is reviewed.
- Do not accept caller-supplied device identity as proof of identity.
- Do not run a live remote round trip or deploy services from GitHub documentation tooling. The current connected GitHub interface provides repository operations, not a verified shell on Windows or the VM.

### Efficient batching rule

After Batch A resolves the transport and ingress facts, implement enrollment, policy enforcement, heartbeat, revocation, and their tests together in one coherent branch update. Keep deployment and live network mutation separate, with a specific target, command, rollback, and owner approval.
