# Swarm Orchestrator — the unification layer

One entry point that makes three existing systems ONE system.
Unification, not greenfield: nothing here re-implements what exists.

## The three systems

| System | Location | Language | What it contributes |
|---|---|---|---|
| Sixteen core | `~/workspace/sovereign-core/` | Rust | ZYLPHA-16 routing, 15 workers, UCP v4, Ara→Michael→Zadkiel→Tesla→dispatch→Gabriel flow |
| Mesh | `~/workspace/mesh-tracks/unified/` | Python | Task diffusion (propose/bid/award/result), deterministic chairman verdicts, signed+encrypted envelopes, hash chains, ADMIT-only join |
| PRIME brain | `~/workspace/prime-brain-build/` | Python | Deterministic kernel, canonical task IDs, hash-chained audit log, approval gates, workers |

## What was unified vs built new

**Unified (wired together, not rewritten):**
- Task IDs: one `make_task_id` (canonical JSON → sha256[:16]) — byte-identical
  to the PRIME kernel's and compatible with the mesh's `task_id_of`.
- PRIME kernel: imported in-process, real workers registered, real submits.
- Mesh diffusion: real loopback propose→bid→award→verdict via the
  orchestrator as owner (genesis ADMIT).
- Sixteen flow: Ara intent parsing + Michael trust + Zadkiel veto ported
  with identical semantics (deny-list, default-allow). No cargo on this
  machine, so Rust agent *execution* stays on HeavenzFire's hardware —
  the adapter routes, gates, and records the handoff.

**Built new (the layer that didn't exist):**
- `registry.py` — capability audit across all three systems, overlaps
  resolved and documented (Bael/shell, Azazel/forge, Uriel/notes,
  Raphael/diag, Thoth/web all default to PRIME locally).
- `gates.py` — the UNION rule: Zadkiel veto AND PRIME approval must both
  permit. Never the weaker gate.
- `ledger.py` — one hash-chained log across the flow; each entry records
  the subsystem chain head it follows (extends, never replaces).
- `scheduler.py` — deterministic batch ordering (priority, then task_id);
  replay digests prove same-input→same-order.
- `ranks.py` — the 144 rank table as a structured authority map
  (King→Knight, 7 tiers), documented as organizational convention.
- `orchestrator.py` — `SwarmOrchestrator.submit()`: the one entry point.

## The flow

```
task in (any shape)
  → canonical task_id
  → GATE UNION (Zadkiel veto + PRIME approval; both must permit)
  → ledger: gate entry
  → ROUTE (registry: prime / mesh / sixteen / reject)
  → ledger: route entry
  → EXECUTE via subsystem adapter
  → ledger: done entry (chaining the subsystem's own chain head)
  → result
```

## Authority (ranks.py)

From `research_notes/goetia-shemhamphorash-144/COMPILED-144.md`
(9 Kings, 21 Dukes, 5 Princes, 16 Marquises, 12 Presidents, 8 Earls,
1 Knight). Used as a 7-tier org chart — structured data, not mysticism.
ZYLPHA-16 sits King-tier and routes only, as the map specifies.

## Tests

`python3 tests/test_orchestrator.py` — 37 checks:
routing (8), gate union (4), Zadkiel semantics (3), ledger integrity +
tamper detection (2), deterministic replay (3), ranks (6),
live PRIME submit incl. approval flow (5), batch determinism (1),
Ara parsing (2).

Existing suites untouched and green:
- `prime-brain-build/kernel.py --self-test`: GREEN (50 tasks, chain verified)
- `mesh-tracks/unified/tests/test_unified.py`: 25/25 OK
- sovereign-core Rust tests: cannot run here (no cargo) — unchanged code

## Honest gaps

1. Sixteen Rust execution needs the binary on his hardware (no cargo here).
   The ported gate logic is semantics-identical, but it is a port, not the
   Rust code running.
2. Mesh diffusion inside the orchestrator spins real loopback nodes per
   distributed task — correct but heavy; a persistent node pool is future work.
3. The orchestrator's approvals file defaults to the PRIME approvals file
   when no path is given (same trust root, documented).
4. Forward secrecy / rekey on the mesh transport is done; the orchestrator
   does not yet drive rekey policy — mesh default (off) applies.
5. No new dependencies: stdlib + existing code only. Mesh crypto is the
   tree's own from-spec pure-Python (pricrypto.py).
