"""Subsystem adapters: the orchestrator's hands into the three systems.

- PrimeAdapter: imports prime-brain-build/kernel.py directly (same process),
  registers the real workers, submits tasks. Deterministic, local.
- MeshAdapter: drives real loopback mesh diffusion (propose -> bid ->
  award -> result -> chairman verdict) using unified transport +
  coordination. The orchestrator acts as owner (genesis ADMIT).
- SixteenAdapter: ports Sixteen routing/gate logic faithfully in Python
  (Ara intent parsing, Zadkiel veto, agent registry). No cargo on this
  machine, so Rust agent EXECUTION stays on HeavenzFire's hardware where
  the binary builds; the adapter documents the handoff and applies the
  identical gate flow (Ara -> Michael(trust) -> Zadkiel -> Tesla -> Gabriel
  broadcast note) around it.

Stdlib + existing code only. Nothing leaves the machine.
"""
import os
import sys
import threading
import time


def _resolve_dir(env_name, *candidates):
    """First existing directory wins: explicit env var, then platform
    defaults. Returns None when nothing exists (callers fail loudly)."""
    p = os.environ.get(env_name)
    if p and os.path.isdir(p):
        return p
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return None


_HERE = os.path.dirname(os.path.abspath(__file__))
_INSTALL = os.path.dirname(_HERE)  # pack root: swarm_orchestrator/ -> ..
_WS = os.path.expanduser("~/workspace")

# PRIME brain: env > his Windows brain > this dev tree.
PRIME_DIR = _resolve_dir("SWARM_PRIME_DIR",
                         r"C:\sixteen\brain",
                         os.path.join(_WS, "prime-brain-build"))
# Mesh: env > pack-bundled copy > this dev tree.
# NOTE: this is the PARENT directory of the `unified` namespace package.
MESH_PARENT = _resolve_dir("SWARM_MESH_DIR",
                           os.path.join(_INSTALL, "mesh"),
                           os.path.join(_WS, "mesh-tracks"))
# Azazel forge worker drop-in: env > pack-bundled copy > dev tree copy.
_AZAZEL = os.environ.get("SWARM_AZAZEL_PATH")
if not (_AZAZEL and os.path.isfile(_AZAZEL)):
    _AZAZEL = os.path.join(_INSTALL, "forge", "azazel_worker.py")
if not os.path.isfile(_AZAZEL):
    _fb = os.path.join(_WS, "your_files", "azazel_worker.py")
    _AZAZEL = _fb if os.path.isfile(_fb) else None
AZAZEL_PATH = _AZAZEL

if PRIME_DIR:
    sys.path.insert(0, PRIME_DIR)
if MESH_PARENT:
    sys.path.insert(0, MESH_PARENT)


# ------------------------------------------------------------------ PRIME
class PrimeAdapter:
    """PRIME deterministic kernel, in-process."""

    def __init__(self, audit_log_path, approvals_path=None):
        import kernel
        self._kernel_mod = kernel
        if approvals_path:
            # kernel binds APPROVALS_FILE at def-time; rebind the defaults
            # so the orchestrator's approval file is honored everywhere
            # (kernel store, worker is_approved checks, save path).
            for fn in ("is_approved", "load_approvals", "save_approvals"):
                f = getattr(kernel, fn)
                f.__defaults__ = (approvals_path,)
        self.kernel = kernel.Kernel(log_path=audit_log_path)
        self._register_workers()
        self.kernel.recover()

    def _register_workers(self):
        import importlib
        k = self.kernel
        for mod_name, worker in (
                ("shell_worker", "shell"), ("fs_worker", "fs"),
                ("browse_worker", "browse"), ("web_worker", "web"),
                ("notes_worker", "notes"),
                ("diagnostics_worker", "diagnostics"),
                ("field_worker", "field"), ("verify_worker", "verify"),
                ("capsule_worker", "capsule")):
            try:
                m = importlib.import_module("workers." + mod_name)
                k.register(worker, m)
            except ImportError:
                pass
        # Azazel forge worker: the drop-in.
        # Resolved at import: SWARM_AZAZEL_PATH env > pack-bundled copy >
        # dev-tree copy. Loaded by path so the orchestrator never depends on
        # it being installed into the brain tree.
        if AZAZEL_PATH:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "azazel_worker", AZAZEL_PATH)
            m = importlib.util.module_from_spec(spec)
            sys.modules["azazel_worker"] = m
            spec.loader.exec_module(m)
            k.register("azazel", m)
        # Forge-repo worker (git forges): ships inside this package.
        try:
            from . import forge_repo as _fr
            k.register("forge_repo", _fr)
        except ImportError:
            pass

    def run(self, task, timeout=60):
        """Submit to the kernel. Returns the kernel's result dict."""
        return self.kernel.submit(
            {"capability": task["capability"], "args": task.get("args", {})},
            timeout=timeout)

    def audit_head(self):
        return self.kernel.log.head

    def approve(self, task_id):
        return self.kernel.approve(task_id)


# ------------------------------------------------------------------- MESH
class MeshAdapter:
    """Real loopback mesh diffusion. Orchestrator is the owner."""

    def __init__(self, node_count=3):
        from unified.transport.mesh import Identity
        from unified.node.unified_node import UnifiedNode, CODE_HASH
        from unified.coordination import agent as coord_agent
        self._Identity = Identity
        self._UnifiedNode = UnifiedNode
        self._CODE_HASH = CODE_HASH
        self._coord_agent = coord_agent
        self.node_count = node_count
        self.nodes = []
        self.agents = []
        self._owner_ident = None

    def _build(self):
        import os as _os
        U = self._UnifiedNode
        owner_ident = self._Identity(_os.urandom(32))
        self._owner_ident = owner_ident
        OWNER_ID = owner_ident.node_id
        OWNER_PK = owner_ident.pk.hex()
        self.nodes = [
            U("orch-node-%d" % i, ["compute"], OWNER_ID, OWNER_PK,
              bid_cost=5 + i, bid_eta_ms=800 + 200 * i)
            for i in range(self.node_count)]
        for x in self.nodes:
            for y in self.nodes:
                x.admit_local(y.node_id, y.pubkey_hex, self._CODE_HASH,
                              admitted_by=OWNER_ID)
        for n in self.nodes:
            n.start()
        # Sequential dials (parallel dials flake under crypto load).
        for i, a in enumerate(self.nodes):
            for b in self.nodes[i + 1:]:
                try:
                    a.connect(*b.addr, timeout=30)
                except Exception:
                    pass
                time.sleep(1)
        self.agents = [self._coord_agent.CoordinatorAgent(n)
                       for n in self.nodes]
        for ag in self.agents:
            ag.start()

    def _teardown(self):
        for ag in self.agents:
            try:
                ag.stop()
            except Exception:
                pass
        for n in self.nodes:
            try:
                n.stop()
            except Exception:
                pass
        self.agents = []
        self.nodes = []

    def diffuse(self, spec, timeout=120):
        """Propose -> bid -> award -> result -> chairman verdict.

        Returns the winning result dict, or raises TimeoutError.
        """
        from unified.coordination import diffusion
        self._build()
        try:
            proposer = self.nodes[0]
            proposer_agent = self.agents[0]
            prop_env = diffusion.propose(proposer, spec, round_no=1,
                                         bid_window_s=15)
            task_id = prop_env["payload"]["task_id"]
            deadline = time.time() + timeout
            while time.time() < deadline:
                with proposer_agent._lock:
                    outcome = proposer_agent.outcomes.get(task_id)
                if outcome:
                    return {"task_id": task_id,
                            "winner": outcome.get("winner"),
                            "verdict": outcome.get("verdict")}
                time.sleep(0.5)
            raise TimeoutError("no chairman verdict within %ss" % timeout)
        finally:
            self._teardown()


# ---------------------------------------------------------------- SIXTEEN
# Ported routing logic (sovereign-core, Rust; no cargo here).
# Semantics match src/agents/ara.rs parse() and the orchestrator flow.

def ara_parse(text):
    """Port of Ara::parse. Returns (intent, target_agent)."""
    t = text.lower()

    def has(words):
        return any(w in t for w in words)

    if has(["remember", "recall", "find", "search", "what do you know"]):
        return ("recall", "Uriel")
    if has(["compress", "shrink", "encode"]):
        return ("execute", "Sophia")
    if has(["verify", "check", "validate", "is this allowed"]):
        return ("verify", "Zadkiel")
    if has(["heal", "repair", "restart", "fix"]):
        return ("heal", "Raphael")
    if has(["run", "execute", "do it", "build"]):
        return ("execute", "Bael")
    if has(["ingest", "learn", "read this"]):
        return ("execute", "Thoth")
    return ("route", "Gabriel")


class SixteenAdapter:
    """Sixteen routing + gate flow, ported.

    Applies the identical gate sequence as orchestrator.rs dispatch_signed
    (Michael trust -> Zadkiel veto -> Tesla placement note -> Gabriel
    broadcast note). Rust agent EXECUTION requires the sovereign-core
    binary on HeavenzFire's hardware; this adapter routes, gates, and
    records the handoff — it never pretends to have run the Rust code.
    """

    TRUSTED_KEYS = {"heavenzfire-dev"}

    def route(self, text, key_id="heavenzfire-dev"):
        """Returns dict with intent, target, gate results, and handoff note."""
        intent, target = ara_parse(text)
        # Michael: trust gate (port of Michael::verify_message trust check)
        if key_id not in self.TRUSTED_KEYS:
            return {"ok": False, "stage": "michael",
                    "reason": "key '%s' untrusted" % key_id}
        # Zadkiel: veto (ported; full rule engine lives in gates.py)
        from .gates import ZadkielGate
        permitted, reason = ZadkielGate().adjudicate(
            "Ara", intent, target)
        if not permitted:
            return {"ok": False, "stage": "zadkiel", "reason": reason}
        # Tesla: placement note (placement proper needs the grid backend)
        # Gabriel: broadcast note recorded by the orchestrator ledger.
        return {"ok": True, "intent": intent, "target": target,
                "note": ("sixteen: routed %s -> %s; Rust execution on "
                         "HeavenzFire hardware") % (intent, target)}
