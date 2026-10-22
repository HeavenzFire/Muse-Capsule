# HeavenzFire Persistent Agent Runtime

A local-first Unified Field surface for deterministic agent simulation. It uses a pure simulation engine, a module Web Worker with OffscreenCanvas when available, IndexedDB event persistence, periodic checkpoints, SHA-256 checkpoint integrity checks, deterministic replay, and JSON evidence export.

## Run tests
From this directory, with Node.js 18 or newer: npm test

## Run the UI
Serve the capsule from localhost or HTTPS so ES modules and IndexedDB are available. Open field/surfaces/agent-runtime/index.html. No dependencies or remote services are required.

## Guarantees and limits
- Seeded xorshift PRNG and tick-driven movement make the simulation deterministic for the same engine version, seed, checkpoint and event sequence.
- Events are explicit records with tick and monotonic sequence. Unknown event types are rejected.
- Checkpoints store complete engine state and a SHA-256 digest. A digest mismatch halts startup.
- IndexedDB is local to this browser profile. Export the JSON evidence bundle for portability.
- Population is bounded. Persistent means events/checkpoints are retained, not that a process is immortal.
- Worker mode isolates simulation and rendering from the main thread; browser throttling and worker termination remain possible.
- This surface is not yet a Unified Field gateway client and does not invoke system commands, external models, or desktop actions.
- Automated engine tests do not constitute browser UI smoke tests. Browser compatibility, quota behavior, and Windows desktop integration remain unverified.