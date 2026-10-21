"""SwarmOrchestrator: the one entry point.

A task enters once, via any subsystem's shape:
  {"capability": ..., "args": {...}}              (PRIME shape)
  {"capability": ..., "args": {...}, "distributed": True}  (mesh shape)
  {"text": "..."}                                  (Sixteen/human shape)

Flow:
  1. canonical task_id (same function as PRIME + mesh)
  2. gate union: Zadkiel veto AND PRIME approval — both must permit
  3. deterministic route (registry.route)
  4. execute via the subsystem adapter
  5. ledger entry chaining the subsystem's own chain head
  6. result

Nothing executes before the gates. Unknown capabilities are rejected,
never guessed.
"""
import os
import threading

from . import registry, scheduler
from .canonical import make_task_id
from .gates import GateUnion, ApprovalGate
from .ledger import OrchestratorLedger
from .adapters import PrimeAdapter, MeshAdapter, SixteenAdapter


class OrchestratorError(Exception):
    pass


class SwarmOrchestrator:
    def __init__(self, workdir, approvals_path=None, mesh_nodes=3):
        os.makedirs(workdir, exist_ok=True)
        self.workdir = workdir
        self.ledger = OrchestratorLedger(
            os.path.join(workdir, "orchestrator.log"))
        self.gates = GateUnion(
            approval=ApprovalGate(approvals_path=approvals_path))
        self._lock = threading.Lock()
        self._prime = None
        self._prime_audit = os.path.join(workdir, "prime-audit.log")
        self._approvals_path = approvals_path
        self._mesh_nodes = mesh_nodes
        self.sixteen = SixteenAdapter()

    def _prime_adapter(self):
        if self._prime is None:
            self._prime = PrimeAdapter(self._prime_audit,
                                       approvals_path=self._approvals_path)
        return self._prime

    # ------------------------------------------------------------ submit
    def submit(self, task):
        """Submit one task dict. Returns a result dict. Raises on denial."""
        task = dict(task)
        tid = task.get("task_id") or make_task_id(task)
        task["task_id"] = tid

        # Sixteen/human shape: parse text -> capability via Ara's table.
        if "text" in task and "capability" not in task:
            from .adapters import ara_parse
            intent, target = ara_parse(task["text"])
            task["intent"] = intent
            task["_sixteen_target"] = target

        with self._lock:
            # 2. gates (union)
            permitted, gate_reasons = self.gates.check(
                task, from_agent="orchestrator",
                intent=task.get("intent", "execute"),
                to_agent=task.get("_sixteen_target",
                                  task.get("capability", "")))
            self.ledger.append(
                "gate", task_id=tid, subsystem="-",
                gates=[{"gate": g, "ok": ok, "reason": r}
                       for g, ok, r in gate_reasons],
                detail="permitted" if permitted else "DENIED")
            if not permitted:
                denied = [r for g, ok, r in gate_reasons if not ok]
                raise OrchestratorError("denied: " + "; ".join(denied))

            # 3. route
            subsystem, handler = registry.route(task)
            self.ledger.append("route", task_id=tid, subsystem=subsystem or "-",
                               detail=str(handler))
            if subsystem is None:
                raise OrchestratorError(handler)

            # 4. execute
            if subsystem == registry.SUBSYSTEM_PRIME:
                adapter = self._prime_adapter()
                result = adapter.run(task)
                head = adapter.audit_head()
            elif subsystem == registry.SUBSYSTEM_MESH:
                mesh = MeshAdapter(node_count=self._mesh_nodes)
                result = mesh.diffuse(
                    {"description": task.get("capability", ""),
                     "args": task.get("args", {})})
                head = result.get("task_id", "")
            else:  # sixteen
                routed = self.sixteen.route(
                    task.get("text", task.get("capability", "")))
                if not routed["ok"]:
                    raise OrchestratorError(
                        "sixteen %s: %s" % (routed["stage"], routed["reason"]))
                result = routed
                head = "-"

            # 5. ledger the completion, chaining the subsystem head
            entry = self.ledger.append(
                "done", task_id=tid, subsystem=subsystem,
                subsystem_head=head,
                detail=str(result)[:500])
            return {"task_id": tid, "subsystem": subsystem,
                    "handler": handler, "result": result,
                    "ledger_seq": entry["seq"], "ledger_hash": entry["hash"]}

    def submit_batch(self, tasks):
        """Deterministic batch: ordered by scheduler, then submitted."""
        results = []
        for t in scheduler.order(tasks):
            try:
                results.append({"ok": True, **self.submit(t)})
            except OrchestratorError as e:
                results.append({"ok": False, "error": str(e),
                                "task_id": t.get("task_id") or make_task_id(t)})
        return results

    def approve(self, task):
        """Record a PRIME approval for a destructive task (owner's hand)."""
        tid = task.get("task_id") or make_task_id(task)
        return self._prime_adapter().approve(tid)

    def verify(self):
        return self.ledger.verify()

    def replay_digest(self, tasks):
        return scheduler.replay_digest(tasks)
