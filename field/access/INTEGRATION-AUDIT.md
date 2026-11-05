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
