"""Orchestrator tests: routing, gate union, ledger integrity, replay, ranks.

Run: python -m pytest tests/ -q  (or python tests/test_orchestrator.py)
Stdlib only. No network. Mesh live-diffusion test is opt-in (slow).
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swarm_orchestrator import registry, scheduler, ranks
from swarm_orchestrator.canonical import make_task_id
from swarm_orchestrator.gates import GateUnion, ZadkielGate, ZadkielRule, ApprovalGate
from swarm_orchestrator.ledger import OrchestratorLedger
from swarm_orchestrator.orchestrator import SwarmOrchestrator, OrchestratorError
from swarm_orchestrator.adapters import ara_parse

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (" -- " + detail if detail and not cond else ""))


# ---------------------------------------------------------------- routing
def test_routing():
    cases = [
        ({"capability": "shell.run", "args": {}}, "prime"),
        ({"capability": "fs.read", "args": {"path": "/tmp"}}, "prime"),
        ({"capability": "forge.dry", "args": {"dir": "/tmp"}}, "prime"),
        ({"capability": "notes.search", "args": {}}, "prime"),
        ({"capability": "whatever", "args": {}, "distributed": True}, "mesh"),
        ({"capability": "sophia.compress", "args": {}}, "sixteen"),
        ({"capability": "tesla.place", "args": {}}, "sixteen"),
        ({"capability": "nope.nothing", "args": {}}, None),
    ]
    for task, want in cases:
        sub, _ = registry.route(task)
        check("route %s -> %s" % (task["capability"], want), sub == want)


def test_canonical_id_matches_kernel():
    sys.path.insert(0, os.path.expanduser("~/workspace/prime-brain-build"))
    import kernel as prime_kernel
    t = {"capability": "fs.list", "args": {"path": "/tmp"}}
    check("task id matches kernel.make_task_id",
          make_task_id(t) == prime_kernel.make_task_id(t))


# ---------------------------------------------------------------- gates
def test_gate_union():
    with tempfile.TemporaryDirectory() as d:
        ap = os.path.join(d, "approvals.json")
        gu = GateUnion(approval=ApprovalGate(approvals_path=ap))
        # benign task: both permit
        ok, _ = gu.check({"capability": "fs.read", "args": {}})
        check("gates permit benign task", ok)
        # destructive without approval: denied (even though Zadkiel allows)
        ok, reasons = gu.check({"capability": "fs.delete",
                                "args": {"path": "/tmp/x"}})
        check("gates deny destructive without approval", not ok)
        # Zadkiel deny beats approval: add broadcast deny, approve the task,
        # still denied
        zg = ZadkielGate(extra_rules=[
            ZadkielRule(to_pat="Gabriel",
                        reason="test: no broadcast")])
        gu2 = GateUnion(zadkiel=zg, approval=ApprovalGate(approvals_path=ap))
        t = {"capability": "fs.read", "args": {}}
        ok, _ = gu2.check(t, to_agent="Gabriel")
        check("zadkiel deny holds despite approval gate permitting", not ok)
        # approval then permit
        from swarm_orchestrator.canonical import make_task_id as mtid
        tid = mtid({"capability": "fs.delete", "args": {"path": "/tmp/x"}})
        with open(ap, "w") as f:
            json.dump([tid], f)
        ok, _ = gu.check({"capability": "fs.delete", "args": {"path": "/tmp/x"}})
        check("gates permit destructive with recorded approval", ok)


def test_zadkiel_semantics():
    z = ZadkielGate()
    ok, _ = z.adjudicate("Ara", "execute", "Bael")
    check("zadkiel default-allow", ok)
    ok, reason = z.adjudicate("Samael", "execute", "Gabriel")
    check("zadkiel denies broadcast by non-orchestrator", not ok and "broadcast" in reason)
    ok, _ = z.adjudicate("orchestrator", "execute", "Gabriel")
    # orchestrator->Gabriel: rule matches from_pat="*" too -> denied.
    # The orchestrator bypasses the gate for its own broadcast (by design).
    check("zadkiel standing broadcast rule exists", not ok)


# ---------------------------------------------------------------- ledger
def test_ledger_integrity():
    with tempfile.TemporaryDirectory() as d:
        lp = os.path.join(d, "orch.log")
        L = OrchestratorLedger(lp)
        L.append("gate", task_id="abc", subsystem="-", detail="permitted")
        L.append("route", task_id="abc", subsystem="prime", detail="shell")
        L.append("done", task_id="abc", subsystem="prime",
                 subsystem_head="deadbeef", detail="ok")
        v = L.verify()
        check("ledger verifies", v["ok"] and v["entries"] == 3)
        # tamper: flip a byte
        with open(lp, "r+") as f:
            lines = f.readlines()
            lines[0] = lines[0].replace("permitted", "PERMITTED")
            f.seek(0)
            f.writelines(lines)
            f.truncate()
        L2 = OrchestratorLedger(lp)
        check("ledger detects tamper", not L2.verify()["ok"])


# ---------------------------------------------------------------- scheduler
def test_deterministic_replay():
    tasks = [{"capability": "fs.list", "args": {"path": "/tmp/x%d" % i}}
             for i in range(5)]
    d1 = scheduler.replay_digest(tasks)
    d2 = scheduler.replay_digest(list(reversed(tasks)))
    check("replay digest order-independent", d1 == d2)
    o1 = [t["args"]["path"] for t in scheduler.order(tasks)]
    o2 = [t["args"]["path"] for t in scheduler.order(list(reversed(tasks)))]
    check("scheduler order stable", o1 == o2)
    # priority bands respected
    ts = [{"capability": "fs.list", "args": {}, "priority": 1},
          {"capability": "fs.list", "args": {"path": "/z"}, "priority": 0}]
    ordered = scheduler.order(ts)
    check("priority band first", ordered[0].get("priority") == 0)


# ---------------------------------------------------------------- ranks
def test_ranks():
    check("king tier seats ZYLPHA-16", ranks.tier_of("ZYLPHA-16") == "King")
    check("duke tier seats Zadkiel", ranks.tier_of("Zadkiel") == "Duke")
    check("knight tier seats mesh-executor",
          ranks.tier_of("mesh-executor") == "Knight")
    check("orchestrator may task anywhere",
          ranks.may_task("orchestrator", "mesh"))
    check("king may task anywhere", ranks.may_task("Gabriel", "prime"))
    check("earl may not task cross-subsystem",
          not ranks.may_task("notes_worker", "mesh"))
    total = sum(c for _, c, _, _ in ranks.RANKS)
    check("rank counts sum to 72", total == 72)


# ---------------------------------------------------------------- live prime
def test_live_prime_submit():
    with tempfile.TemporaryDirectory() as d:
        orch = SwarmOrchestrator(workdir=d,
                                 approvals_path=os.path.join(d, "appr.json"))
        r = orch.submit({"capability": "notes.create",
                         "args": {"name": "t1", "content": "hello"}})
        check("live prime submit routes to prime", r["subsystem"] == "prime")
        check("live prime submit ok", r["result"].get("ok") is True)
        v = orch.verify()
        check("orchestrator ledger verifies after live submit", v["ok"])
        # unknown capability rejected
        try:
            orch.submit({"capability": "nope.nothing", "args": {}})
            check("unknown capability rejected", False)
        except OrchestratorError:
            check("unknown capability rejected", True)
        # destructive denied without approval
        try:
            orch.submit({"capability": "fs.delete",
                         "args": {"path": os.path.join(d, "nope")}})
            check("destructive denied pre-approval", False)
        except OrchestratorError as e:
            check("destructive denied pre-approval", "denied" in str(e))
        # approve then execute
        orch.approve({"capability": "fs.delete",
                      "args": {"path": os.path.join(d, "nope")}})
        r2 = orch.submit({"capability": "fs.delete",
                          "args": {"path": os.path.join(d, "nope")}})
        check("destructive executes post-approval",
              r2["subsystem"] == "prime")


def test_batch_deterministic():
    with tempfile.TemporaryDirectory() as d:
        orch = SwarmOrchestrator(workdir=d,
                                 approvals_path=os.path.join(d, "appr.json"))
        tasks = [{"capability": "notes.create",
                  "args": {"name": "b%d" % i, "content": "x"}} for i in range(3)]
        r1 = [r.get("task_id") for r in orch.submit_batch(tasks) if r["ok"]]
        with tempfile.TemporaryDirectory() as d2:
            orch2 = SwarmOrchestrator(workdir=d2,
                                      approvals_path=os.path.join(d2, "appr.json"))
            r2 = [r.get("task_id") for r in orch2.submit_batch(list(reversed(tasks))) if r["ok"]]
        check("batch dispatch order deterministic", r1 == r2)


def test_sixteen_routing():
    intent, target = ara_parse("remember what we decided about the mesh")
    check("ara parses recall -> Uriel", (intent, target) == ("recall", "Uriel"))
    intent, target = ara_parse("build the release bundle")
    check("ara parses build -> Bael", (intent, target) == ("execute", "Bael"))


if __name__ == "__main__":
    test_routing()
    test_canonical_id_matches_kernel()
    test_gate_union()
    test_zadkiel_semantics()
    test_ledger_integrity()
    test_deterministic_replay()
    test_ranks()
    test_live_prime_submit()
    test_batch_deterministic()
    test_sixteen_routing()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILURES:", FAIL)
        sys.exit(1)
