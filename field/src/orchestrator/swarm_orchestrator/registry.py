"""Capability registry: what lives where, overlaps resolved.

Audited 2026-10-15 from the three systems' own sources:
- prime-brain-build/workers/*.py (CAPABILITIES lists) + your_files/azazel_worker.py
- sovereign-core/src/agents/*.rs (owns() strings + handle payloads)
- mesh-tracks/unified (coordination/diffusion.py, chairman.py, trust/)

Routing policy (deterministic, first match wins):
  1. capability in PRIME_CAPABILITIES      -> PRIME kernel (local, deterministic)
  2. capability in FORGE_CAPABILITIES      -> PRIME azazel_worker (local forge)
  3. task["distributed"] is True          -> mesh diffusion + chairman verdict
  4. capability in SIXTEEN_CAPABILITIES    -> Sixteen routing (gate logic ported;
     Rust execution on HeavenzFire's hardware)
  5. otherwise                             -> REJECT (unknown capability)

Overlaps found and resolved (documented, not hidden):
  - shell.run (PRIME) vs Bael "state execution" (Sixteen): local shell work
    routes to PRIME; Bael is the Sixteen-side equivalent when the Rust core
    is the executor. Default: PRIME.
  - forge.dry/forge.build (PRIME azazel_worker) vs Azazel "forge" (Sixteen):
    local builds route to the PRIME worker; Sixteen Azazel when the Rust
    backend executes. Default: PRIME.
  - notes.search/capsule.* (PRIME) vs Uriel "recall" (Sixteen): local memory
    routes to PRIME; cross-agent knowledge ops route Sixteen.
  - diag.check (PRIME) vs Raphael "healing" (Sixteen): local diagnostics go
    PRIME; system-wide healing goes Sixteen/Raphael.
  - web.search/web.fetch (PRIME) vs Thoth "ingest" (Sixteen): fetch goes
    PRIME; knowledge-graph ingest goes Sixteen/Thoth.
"""
from .canonical import make_task_id

# ---------------------------------------------------------------- PRIME
# prime-brain-build/workers/*.py CAPABILITIES + your_files/azazel_worker.py
PRIME_CAPABILITIES = {
    "shell.run": "shell_worker",
    "fs.read": "fs_worker",
    "fs.write": "fs_worker",
    "fs.list": "fs_worker",
    "fs.mkdir": "fs_worker",
    "fs.delete": "fs_worker",
    "browse.open": "browse_worker",
    "web.search": "web_worker",
    "web.fetch": "web_worker",
    "notes.create": "notes_worker",
    "notes.read": "notes_worker",
    "notes.list": "notes_worker",
    "notes.search": "notes_worker",
    "diag.check": "diagnostics_worker",
    "field.status": "field_worker",
    "capsule.verify": "verify_worker",
    "capsule.load": "capsule_worker",
    "capsule.section": "capsule_worker",
    "capsule.append": "capsule_worker",
    "forge.dry": "azazel_worker",
    "forge.build": "azazel_worker",
    # Git-forges (forge_repo worker, ships in this package). Doctrine:
    # Gitea is the source of truth (origin), GitHub is the mirror.
    # Destructive modes (force push) are enforced inside the worker via the
    # same PRIME approvals file the gate union reads — one trust root.
    "forge.repo.sync": "forge_repo",
    "forge.repo.status": "forge_repo",
    "forge.repo.check": "forge_repo",
    "forge.issue.create": "forge_repo",
    "forge.issue.list": "forge_repo",
}

# Capabilities that need a recorded PRIME approval before execution.
# Mirrors kernel approval gates (fs.delete, forge.build) — the union rule
# in gates.py enforces these even when a task arrives via another system.
DESTRUCTIVE_CAPABILITIES = {"fs.delete", "forge.build"}

# ---------------------------------------------------------------- SIXTEEN
# sovereign-core/src/agents/*.rs — owns() strings. Handled via the ported
# routing table (adapters.SixteenAdapter); Rust execution on his hardware.
SIXTEEN_CAPABILITIES = {
    # agent -> owns()
    "zypha16.route": "ZYLPHA-16",
    "ara.parse": "Ara",
    "bael.execute": "Bael",
    "tesla.place": "Tesla",
    "zadkiel.adjudicate": "Zadkiel",
    "metatron.record": "Metatron",
    "sophia.compress": "Sophia",
    "uriel.recall": "Uriel",
    "raphael.heal": "Raphael",
    "michael.verify": "Michael",
    "gabriel.broadcast": "Gabriel",
    "azazel.forge": "Azazel",
    "samael.adversarial": "Samael",
    "lilith.ingest": "Lilith",
    "sandalphon.ground": "Sandalphon",
    "thoth.extract": "Thoth",
}

# ---------------------------------------------------------------- MESH
# mesh-tracks/unified — distributed execution surface.
MESH_KINDS = {
    "TASK_PROPOSE", "TASK_BID", "TASK_RESULT", "CHAIRMAN_VERDICT",
    "ADMIT", "REVOKE", "ATTEST",
}

SUBSYSTEM_PRIME = "prime"
SUBSYSTEM_MESH = "mesh"
SUBSYSTEM_SIXTEEN = "sixteen"


def route(task: dict):
    """Return (subsystem, handler_key) or (None, 'unknown capability').

    Deterministic: same task -> same route, every time.
    """
    cap = task.get("capability", "")
    if cap in PRIME_CAPABILITIES:
        return SUBSYSTEM_PRIME, PRIME_CAPABILITIES[cap]
    if task.get("distributed") is True:
        return SUBSYSTEM_MESH, "diffusion"
    if cap in SIXTEEN_CAPABILITIES:
        return SUBSYSTEM_SIXTEEN, SIXTEEN_CAPABILITIES[cap]
    return None, "unknown capability: %s" % cap


def audit_report():
    """Human-readable capability audit: every capability, its home, overlaps."""
    lines = ["PRIME brain (local, deterministic):"]
    for cap in sorted(PRIME_CAPABILITIES):
        flag = " [DESTRUCTIVE: needs approval]" if cap in DESTRUCTIVE_CAPABILITIES else ""
        lines.append("  %-18s -> %s%s" % (cap, PRIME_CAPABILITIES[cap], flag))
    lines.append("Sixteen (routing/gates ported; Rust execution on his hardware):")
    for cap in sorted(SIXTEEN_CAPABILITIES):
        lines.append("  %-18s -> %s" % (cap, SIXTEEN_CAPABILITIES[cap]))
    lines.append("Mesh (distributed): TASK_PROPOSE/BID/RESULT + CHAIRMAN_VERDICT, ADMIT/REVOKE/ATTEST")
    lines.append("Overlaps resolved: shell Bael->PRIME, forge Azazel->PRIME worker, "
                 "recall Uriel->PRIME notes, diag Raphael->PRIME, ingest Thoth->PRIME web")
    return "\n".join(lines)
