"""Unified swarm orchestrator.

Makes three existing systems ONE system (unification, not greenfield):

- Sixteen core (~/workspace/sovereign-core/): ZYLPHA-16 routing, 15 workers,
  UCP v4, Ara -> Michael -> Zadkiel -> Tesla -> dispatch -> Gabriel flow.
  Rust — no cargo here, so gate/routing logic is ported faithfully in
  adapters.py (SixteenAdapter); actual Rust agent execution stays on
  HeavenzFire's hardware where the binary builds.
- Mesh (~/workspace/mesh-tracks/unified/): task diffusion, deterministic
  chairman verdicts, signed+encrypted envelopes, hash chains, ADMIT-only join.
- PRIME brain (~/workspace/prime-brain-build/): deterministic kernel,
  canonical task IDs, hash-chained audit log, approval gates, workers.

Layout:
    canonical.py    canonical JSON + task IDs (same function as both systems)
    registry.py     capability audit: what lives where, overlaps resolved
    gates.py        Zadkiel veto (ported semantics) + PRIME approval, UNION
    ledger.py       one hash-chained log across the orchestrated flow
    scheduler.py    deterministic, replayable dispatch ordering
    ranks.py        the 144 rank table as a structured authority map
    adapters.py     PrimeAdapter / MeshAdapter / SixteenAdapter
    orchestrator.py SwarmOrchestrator: the one entry point
"""
