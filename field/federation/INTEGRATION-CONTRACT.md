# Unified Field Federation Contract

## Rule

Every new repository, application, model, or agent must be registered before it is described as integrated. Registration is inventory, not connectivity.

## Required lifecycle

1. **Discover** the component and verify its canonical owner, repository, runtime, and license.
2. **Register** a stable component ID, canonical URL, role, interfaces, evidence, and current integration status.
3. **Adapt** through a versioned, least-privilege interface. Prefer the Unified Field gateway; keep internal services private and loopback-bound unless an explicitly reviewed network design requires otherwise.
4. **Contract-test** request/response schemas, authentication, timeout behavior, error handling, idempotency where needed, and compatibility.
5. **Verify live health** from the actual runtime. A repository URL, README, successful build, or registry entry is not live-health evidence.
6. **Promote status** only when required checks pass and the adapter is exercised end-to-end.
7. **Prevent drift** with CI validation on every change. New components must add a registry entry and a test or documented reason why an adapter is not applicable.

## Status values

- `discovered-not-connected`: identity found; no working adapter verified.
- `governance-candidate`: governance or architecture exists; integration remains unverified.
- `adapter-in-progress`: adapter implementation exists but acceptance checks have not passed.
- `contract-verified`: adapter contract tests pass; live end-to-end health may still be unverified.
- `connected-verified`: contract tests and live end-to-end health checks pass with dated evidence.
- `identity-unresolved`: canonical repository or component identity is ambiguous.
- `blocked`: a concrete dependency or permission prevents integration.

## Security invariants

- Never put credentials, tokens, private keys, personal data, or secret endpoints in the registry.
- Use explicit capability allowlists and least privilege for every adapter.
- Keep write, deployment, credential, network, and destructive operations behind separate approval gates.
- Do not merge repositories merely to create connectivity. Integrate through stable contracts and adapters; use code merging only when a reviewed shared codebase is the correct design.
- Do not claim models have been fused into a new model. Orchestrate existing models through explicit interfaces and preserve attribution, version, policy, and provenance.

## Current evidence boundary

The registry records only the two discovered repositories and the unresolved PR reference included in its entries. It does not claim that all HeavenzFire repositories, AI apps, or local services are connected. The next implementation milestone is a gateway adapter and an end-to-end contract test, followed by onboarding repositories incrementally through this same gate.
