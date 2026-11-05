# HF-Access Protocol Contract

Status: interface contract; wire format and implementation are not yet frozen.

## Required lifecycle

`UNENROLLED -> CHALLENGE_ISSUED -> OWNER_APPROVED -> CREDENTIAL_ISSUED -> ACTIVE -> REVOKED | EXPIRED | QUARANTINED`

All transitions are durable audit events. No transition to ACTIVE occurs solely because a device is reachable.

## Enrollment

1. An authorized operator requests enrollment for a known device and declared role.
2. The coordinator issues a cryptographically random, single-use challenge with a short expiry.
3. The device proves possession of its locally generated private key and binds the challenge to its device identity.
4. The operator reviews device identity, intended owner, requested scopes, and environment.
5. The approval event is recorded; a device-specific credential is issued through the selected mature identity/transport mechanism.
6. The device performs an authenticated health check.
7. The registry marks ACTIVE only after identity, policy, and health checks pass.

Enrollment must fail closed on missing approval, invalid proof, expiry, replay, identity mismatch, or ledger failure.

## Authenticated session

A session must provide:
- mutual peer authentication where supported by the selected transport;
- integrity and confidentiality in transit;
- explicit protocol version and audience;
- device identity and credential status;
- request identifier and replay protection;
- bounded message size and request timeout;
- server-side capability authorization;
- auditable outcome.

## Heartbeat

Heartbeat reports are signed/authenticated by the session identity and include:
- device identifier;
- monotonic sequence or replay-resistant freshness value;
- observed timestamp;
- software/runtime version;
- health summary;
- supported capability identifiers.

A heartbeat is evidence of a recent report, not proof that every subsystem or attached device is healthy. Staleness thresholds are configurable per device class. Unknown or stale devices are not eligible for new tasks.

## Task dispatch

A task envelope must include:
- unique task ID;
- issuer and target device identity;
- capability identifier;
- bounded arguments/schema;
- creation and expiry times;
- idempotency key;
- required approval class;
- evidence correlation ID.

The receiver validates identity, expiry, capability grant, approval, schema, and idempotency before execution. Unknown capabilities are rejected. Results settle into the existing task ledger; delivery acknowledgement is not task success.

## Revocation

Revocation must:
- invalidate the device credential or identity grant;
- prevent new sessions and task dispatch;
- terminate or quarantine active sessions according to policy;
- append an auditable event;
- propagate to all coordinators before the system reports revocation complete.

Offline devices remain revoked when they reconnect. Revocation state must not be rolled back by stale synchronization.

## Transport decision

Do not implement cryptographic primitives or a custom secure handshake. First inspect existing private network, gateway, and certificate infrastructure; then select a mature, maintained TLS/mTLS or equivalent authenticated transport compatible with the deployed nodes. Record the choice, version, trust anchors, rotation path, and operational failure modes before coding.
