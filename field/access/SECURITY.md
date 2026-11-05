# HF-Access Security and Threat Model

Status: initial design baseline. Requires review before deployment.

## Assets

- Device private keys and issued credentials.
- Device identity and enrollment state.
- Capability grants and approval records.
- Task payloads, results, and audit ledger.
- Gateway, node, mesh, and orchestrator availability.
- IoT telemetry and any operational metadata.

## Threats and required controls

| Threat | Required control | Verification |
|---|---|---|
| Rogue device joins a LAN | Explicit enrollment; cryptographic identity; no LAN trust | Unenrolled peer rejected |
| Enrollment replay | Single-use nonce/challenge with short expiry and server-side consumption | Replayed challenge rejected |
| Stolen credential | Device-scoped credential, revocation, rotation, minimal scope | Revoked credential rejected |
| Privilege escalation | Deny-by-default capability authorization at execution boundary | Out-of-scope task rejected |
| Agent impersonation | Authenticate device and workload identity separately where needed | Wrong identity binding rejected |
| Network interception | Mature TLS/mTLS implementation with certificate validation | Invalid/expired peer certificate rejected |
| Duplicate task delivery | Existing task idempotency and durable ledger semantics | Retry does not double-execute |
| Ledger tampering | Existing hash-chain verification and protected write path | Modified event chain fails verification |
| Coordinator outage | Bounded local behavior, queue persistence, reconnect backoff | Restart/outage recovery test |
| IoT unsafe actuation | Read-only first; separate explicit capability and human approval for any later actuator | Actuation denied by default |
| Secret leakage | Hardware/local key generation, no repository secrets, redacted logs | Repository and log scans |

## Identity and enrollment requirements

- Generate device private keys on the device or its trusted local host.
- Never upload private keys to GitHub, chat, logs, or the coordination VM.
- Bind enrollment to a device identity, owner approval, expiry, and one-time challenge.
- Issue credentials with explicit audience, purpose, validity, and revocation identifier.
- Rotate credentials without disabling audit continuity.
- Treat device names, IP addresses, MAC addresses, and network membership as metadata, not authentication.

## Authorization model

Each grant must identify:
- principal/device identity;
- permitted capability identifiers;
- permitted resource/device scope;
- allowed operation class (read, report, bounded action);
- validity interval;
- approval requirement;
- issuer and evidence reference.

No wildcard capability or unrestricted command channel is permitted by default. The authorization check must run at the action execution boundary, not only in the UI or gateway.

## Data minimization

- Collect only operational telemetry required for the declared task.
- Do not collect household traffic, user content, camera/microphone streams, or personal data by default.
- Keep development and test data synthetic wherever possible.
- Define retention and deletion rules before collecting production telemetry.
- Never log secrets, private keys, bearer tokens, or full sensitive payloads.

## Critical infrastructure boundary

HF-Access is not a safety-certified control system. Medical life-support devices, clinical device settings, industrial safety interlocks, fire systems, and emergency controls remain outside experimental autonomous control. Initial integrations are read-only monitoring and authorized alert routing. Any later actuation requires domain-specific hazard analysis, independent validation, operator approval, and applicable regulatory review.

## Incident response

1. Revoke the affected identity or credential.
2. Stop routing new tasks to the affected device.
3. Preserve redacted audit evidence and timestamps.
4. Determine scope and whether other credentials are affected.
5. Rotate impacted credentials through the approved local ceremony.
6. Restore only after independent verification.
