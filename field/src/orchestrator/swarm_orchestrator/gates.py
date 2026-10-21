"""Safety gates: Zadkiel's veto AND the PRIME approval gate.

Union rule: a task executes only if BOTH gates permit. A task needs to pass
the union of applicable gates, never the weaker one.

Zadkiel (ported from sovereign-core/src/agents/zadkiel.rs — same semantics):
  - explicit rule list over (from, intent, to); "*" matches any; intent None
    matches any intent
  - deny rules veto; default-allow when no rule matches
  - v1 ships with HeavenzFire's standing denies (below); production binds
    signed policy bundles (owner's hand only)

PRIME approval gate (mirrors prime-brain-build/kernel.py):
  - destructive capabilities (registry.DESTRUCTIVE_CAPABILITIES) require a
    recorded approval for the task's canonical ID
  - approvals live in the kernel's approvals file; the orchestrator reads it,
    never writes it (writes are the kernel's POST /approve path)
"""
import json
import os

from . import registry
from .canonical import make_task_id

APPROVALS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "prime-brain-build", "approvals.json")


class ZadkielRule:
    """One policy rule. Port of sovereign-core PolicyRule."""

    def __init__(self, from_pat="*", intent=None, to_pat="*", deny=True, reason=""):
        self.from_pat = from_pat
        self.intent = intent  # None = any intent
        self.to_pat = to_pat
        self.deny = deny
        self.reason = reason

    def matches(self, from_agent, intent, to_agent):
        from_ok = self.from_pat == "*" or self.from_pat == from_agent
        to_ok = self.to_pat == "*" or self.to_pat == to_agent
        intent_ok = self.intent is None or self.intent == intent
        return from_ok and to_ok and intent_ok


# HeavenzFire's standing denies (v1). Same shape as the Rust default set:
# explicit denies, default-allow. Production binds signed bundles.
STANDING_DENIES = [
    # No agent may task Gabriel's broadcast except the orchestrator itself —
    # broadcast is a privilege, not a capability.
    ZadkielRule(from_pat="*", intent=None, to_pat="Gabriel",
                reason="zadkiel: broadcast is orchestrator-privileged"),
    # Destructive intents never ride the mesh wire without local approval.
    ZadkielRule(from_pat="*", intent="destroy", to_pat="*",
                reason="zadkiel: destroy intent denied without local approval"),
]


class ZadkielGate:
    """Port of Zadkiel.adjudicate. (bool, reason)."""

    def __init__(self, extra_rules=None):
        self.rules = list(STANDING_DENIES) + list(extra_rules or [])

    def add_rule(self, rule):
        """Owner's hand only in production (signed bundle)."""
        self.rules.append(rule)

    def adjudicate(self, from_agent, intent, to_agent):
        for r in self.rules:
            if r.deny and r.matches(from_agent, intent, to_agent):
                return False, r.reason
        return True, "zadkiel: permitted by default-allow"


def load_approvals(path=None):
    try:
        with open(path or APPROVALS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


class ApprovalGate:
    """PRIME approval gate: destructive capabilities need recorded approval."""

    def __init__(self, approvals_path=None):
        self.path = approvals_path or APPROVALS_FILE

    def check(self, task):
        cap = task.get("capability", "")
        if cap not in registry.DESTRUCTIVE_CAPABILITIES:
            return True, "approval: not destructive, no approval needed"
        tid = task.get("approval_id") or make_task_id(task)
        if tid in load_approvals(self.path):
            return True, "approval: recorded for %s" % tid
        return False, "approval: destructive capability '%s' needs recorded approval" % cap


class GateUnion:
    """Both gates must permit. Reports every denial."""

    def __init__(self, zadkiel=None, approval=None):
        self.zadkiel = zadkiel or ZadkielGate()
        self.approval = approval or ApprovalGate()

    def check(self, task, from_agent="orchestrator", intent="execute", to_agent=""):
        reasons = []
        z_ok, z_reason = self.zadkiel.adjudicate(from_agent, intent, to_agent or task.get("capability", ""))
        a_ok, a_reason = self.approval.check(task)
        reasons.append(("zadkiel", z_ok, z_reason))
        reasons.append(("approval", a_ok, a_reason))
        permitted = z_ok and a_ok
        return permitted, reasons
