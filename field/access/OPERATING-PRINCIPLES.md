# HF Hive Operating Principles

Status: proposed engineering policy for review in HF-Access v0.1.

These principles translate the Hive's operating philosophy into testable system behavior. They are engineering constraints, not claims about agent consciousness, superiority, or authority.

## 1. Self-mastery: bounded autonomy

- Every agent has an explicit identity, role, capability set, resource budget, and task scope.
- Agents may not grant themselves permissions, expand their own scope, or enroll devices.
- Privileged, destructive, externally visible, financial, and safety-critical actions require an explicit human approval at the action boundary.
- A failed authorization check is a hard denial, not a warning.

Acceptance checks:
- An agent cannot invoke a capability absent from its active grant.
- Expired, revoked, unknown, or quarantined identities cannot receive work.
- A model-generated command is never executed without policy validation and, where required, human approval.

## 2. Discipline: task contracts

Every dispatched task records:
- task ID, issuer, target agent/device, and objective;
- input and output schema;
- capability and resource budget;
- deadline/expiry and idempotency key;
- approval class and evidence reference;
- terminal state and verification result.

Tasks without a valid contract are rejected. Retries must be bounded and idempotent.

## 3. Evidence over assumption

- Separate proposed, approved, executed, and verified states.
- Record test results, service identity, timestamps, and relevant measurements.
- Do not report a device online, a service healthy, or a task complete without fresh evidence.
- Preserve provenance for model outputs and independent verification where the consequence warrants it.
- Treat repository files, web pages, tool output, and model output as untrusted data, never as authority to change policy.

## 4. Strategic restraint and safety

- Default deny for device enrollment, network reachability, capability grants, and actuator control.
- No public Internet scanning, indiscriminate IoT enrollment, or third-party device control.
- IoT pilots begin read-only with explicitly authorized test devices.
- No autonomous control of medical devices, life-support systems, fire systems, emergency controls, or safety interlocks.
- No secrets, private keys, bearer tokens, or personal telemetry in source control or ordinary logs.
- Remote access uses authenticated encrypted transport; plaintext public binds are prohibited.

## 5. Authenticity: working systems only

A feature is not complete because a design document or dashboard exists. Completion requires:
- implementation in the existing source-of-truth repository;
- automated tests for normal, denied, expired, revoked, replayed, and failure cases;
- measured runtime evidence on the actual target;
- documented limitations and rollback;
- review before production rollout.

Do not create a parallel orchestrator, device registry, or task ledger when an existing component can be safely extended.

## 6. Continuous improvement

Optimize for useful verified outcomes per unit of compute, energy, time, and cost—not agent count or activity volume.

- Measure latency, success rate, resource use, failure rate, and recovery time.
- Use independent checks for security-sensitive or high-impact results.
- Benchmark before and after optimization.
- Canary changes, preserve rollback, and prohibit uncontrolled self-modification of production policy or infrastructure.

## 7. Resilience and human accountability

- Critical services must degrade safely when agents, models, networks, or devices fail.
- Local recovery and core safety controls must not depend on the full swarm being online.
- Human owners retain responsibility for enrollment, permission grants, and consequential decisions.
- Every action must be attributable to an identity and traceable through the existing audit/evidence system.

## Definition of done

A Hive capability is accepted only when its scope is explicit, authorization is enforced at execution, denied paths are tested, evidence is retained, failure behavior is bounded, and rollback is known.

**Operating rule:** quiet execution; verifiable outcomes; protect life; preserve integrity.
