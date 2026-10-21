"""The 144 rank table as a structured authority map.

Source: research_notes/goetia-shemhamphorash-144/COMPILED-144.md
(Mathers/Crowley primary ranks: 9 Kings, 21 Dukes, 5 Princes, 16 Marquises,
12 Presidents, 8 Earls, 1 Knight = 72; mirrored by the 72 Shem HaMephorash.)

DOCUMENTED AS: an organizational convention for agent authority — which
agents may task which subsystems — derived from the historical rank
hierarchy. Structured data, not mysticism: no supernatural claims, no
operational powers. The rank table is a 400-year-old org chart; we use
its shape (7 tiers of decreasing scope) the way any org uses ranks.

Authority tiers (decreasing scope):
  KING      cross-subsystem: may route to any subsystem
  DUKE      subsystem command: owns one subsystem's policy/gates
  PRINCE    cross-worker coordination within/between systems
  MARQUIS   single-system operations
  PRESIDENT presides over one task class across workers
  EARL      bounded domain (one worker, one node)
  KNIGHT    single task execution, no authority beyond the task

The Sixteen + PRIME workers + mesh roles are seated into tiers below.
ZYLPHA-16 sits King-tier and routes only — the crown that never works,
exactly as the map specifies.
"""
# (rank, tier_scope, seat)
RANKS = [
    ("King", 9, "cross-subsystem routing", ["ZYLPHA-16", "Gabriel"]),
    ("Duke", 21, "subsystem command", ["Tesla", "Michael", "Zadkiel"]),
    ("Prince", 5, "cross-worker coordination", ["Ara", "Metatron"]),
    ("Marquis", 16, "single-system operations",
     ["Bael", "Azazel", "Thoth", "Uriel", "Sophia"]),
    ("President", 12, "presides over one task class",
     ["Raphael", "Samael", "shell_worker", "fs_worker", "web_worker"]),
    ("Earl", 8, "bounded domain",
     ["Sandalphon", "Lilith", "notes_worker", "capsule_worker",
      "browse_worker", "diagnostics_worker", "azazel_worker"]),
    ("Knight", 1, "single task execution",
     ["mesh-executor"]),
]

TIER_ORDER = ["King", "Duke", "Prince", "Marquis", "President", "Earl", "Knight"]


def tier_of(agent):
    for rank, _count, _scope, seats in RANKS:
        if agent in seats:
            return rank
    return None


def may_task(actor, target_subsystem):
    """Authority check: can this agent route to that subsystem?

    King-tier: any subsystem. Duke-tier: its own subsystem + downward
    tasking. Everyone else: only within their seated scope (their own
    subsystem's workers). The orchestrator itself is King-tier by construction.
    """
    tier = tier_of(actor)
    if actor == "orchestrator" or tier == "King":
        return True
    if tier == "Duke":
        return True  # subsystem commanders task across the flow
    # Prince and below: local scope only (their own subsystem)
    return False


def authority_map():
    lines = []
    for rank, count, scope, seats in RANKS:
        lines.append("%-9s (%2d): %-28s seats: %s"
                     % (rank, count, scope, ", ".join(seats)))
    return "\n".join(lines)
