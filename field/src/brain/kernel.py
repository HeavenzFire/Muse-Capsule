#!/usr/bin/env python3
"""
PRIME deterministic dispatch kernel.

- Deterministic task IDs: sha256(canonical_json(capability+args))[:16]
- Logical clock for the audit log (no wall-clock inside the chain, so
  same-seed runs produce byte-identical logs)
- Seeded Mulberry32 PRNG (seeded from task ID)
- Skip-and-defer with backoff; nothing is silently dropped
- Worker quarantine after 3 consecutive failures; probe-based recovery
- Idempotency: same task submitted twice runs once
- Cooperative cancellation via threading.Event signal
- SHA-256 hash-chained JSONL audit log

Run the self-test:  python kernel.py --self-test
"""

import concurrent.futures
import hashlib
import json
import os
import sys
import tempfile
import threading
import time

BRAIN_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIT_LOG = os.path.join(BRAIN_DIR, "audit.log")
APPROVALS_FILE = os.path.join(BRAIN_DIR, "approvals.json")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def make_task_id(task: dict) -> str:
    core = {"capability": task.get("capability"), "args": task.get("args", {})}
    return sha256_hex(canonical(core).encode("utf-8"))[:16]


def mulberry32(seed: int):
    """Seeded PRNG. Same seed -> same sequence, every platform."""
    a = seed & 0xFFFFFFFF

    def rand():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        step = ((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF
        t = (((t + step) & 0xFFFFFFFF) ^ t) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return rand


class EventLog:
    """Hash-chained JSONL event log. Chain: entry hash = sha256(canonical line)."""

    def __init__(self, path=AUDIT_LOG):
        self.path = path
        self._lock = threading.Lock()
        self.seq = 0
        self.tick = 0
        self.head = "GENESIS"
        if os.path.exists(path):
            self._replay()

    def _replay(self):
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                e = json.loads(line)
                self.seq = e["seq"]
                self.tick = e["t"]
                self.head = sha256_hex(line.encode("utf-8"))

    def append(self, etype, **fields):
        with self._lock:
            self.seq += 1
            self.tick += 1
            e = {"seq": self.seq, "t": self.tick, "type": etype, "prev": self.head}
            e.update(fields)
            line = canonical(e)
            h = sha256_hex(line.encode("utf-8"))
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            self.head = h
            return {"seq": self.seq, "hash": h}

    def entries(self):
        """All parsed log entries, in order. Used by recovery."""
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if line:
                    out.append(json.loads(line))
        return out

    def verify(self):
        if not os.path.exists(self.path):
            return {"ok": True, "entries": 0, "head": "GENESIS"}
        prev = "GENESIS"
        n = 0
        with open(self.path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line:
                    continue
                n += 1
                e = json.loads(line)
                if e.get("seq") != n or e.get("prev") != prev:
                    return {"ok": False, "at": n}
                prev = sha256_hex(line.encode("utf-8"))
        return {"ok": True, "entries": n, "head": prev}


def load_approvals(path=APPROVALS_FILE):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_approvals(approvals, path=APPROVALS_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(approvals), f, indent=2)


def is_approved(task_id, path=APPROVALS_FILE):
    return task_id in load_approvals(path)


class Kernel:
    QUARANTINE_AFTER = 3
    RECOVER_AFTER = 3
    MAX_DEFERS = 3

    def __init__(self, log_path=AUDIT_LOG):
        self.log = EventLog(log_path)
        self.workers = {}
        self.cap2worker = {}
        self._lock = threading.Lock()
        self._results = {}
        self._consec_fail = {}
        self._quarantined = set()
        self._probe_ok = {}
        self._approvals = load_approvals()

    # ---- registration ----
    def register(self, name, module):
        self.workers[name] = module
        for cap in getattr(module, "CAPABILITIES", []):
            self.cap2worker[cap] = name
        self.log.append("worker_registered", worker=name,
                        capabilities=list(getattr(module, "CAPABILITIES", [])))

    # ---- approvals (consent gate) ----
    def approve(self, task_id):
        with self._lock:
            self._approvals.add(task_id)
            save_approvals(self._approvals)
        self.log.append("approved", task_id=task_id)
        return True

    def is_approved(self, task_id):
        return task_id in self._approvals

    # ---- dispatch ----
    def submit(self, task, timeout=60, max_retries=2):
        tid = make_task_id(task)
        cap = task.get("capability")
        with self._lock:
            if tid in self._results:
                self.log.append("dedup_hit", task_id=tid, capability=cap)
                return dict(self._results[tid], _dedup=True)
        self.log.append("submitted", task_id=tid, capability=cap,
                        args=task.get("args", {}))

        worker_name = self.cap2worker.get(cap)
        if not worker_name:
            res = {"ok": False, "terminal": True,
                   "error": "no worker for capability: %r" % cap}
            self._settle(tid, res, "no_worker")
            return res

        # seeded PRNG available to dispatch decisions
        rng = mulberry32(int(tid[:8], 16))

        attempt = 0
        while True:
            attempt += 1
            with self._lock:
                quarantined = worker_name in self._quarantined
            if quarantined:
                self.log.append("deferred", task_id=tid, worker=worker_name,
                                attempt=attempt, reason="quarantined")
                if attempt > self.MAX_DEFERS:
                    res = {"ok": False, "terminal": True,
                           "error": "worker quarantined: %s" % worker_name}
                    self._settle(tid, res, "quarantine_exhausted")
                    return res
                time.sleep(0.1 * attempt + rng() * 0.1)
                continue
            res = self._run_once(worker_name, task, tid, timeout)
            if res.get("ok"):
                self._note_success(worker_name)
                self._settle(tid, res, "completed")
                return res
            self._note_failure(worker_name, tid, res)
            if attempt > max_retries:
                res = dict(res, terminal=True)
                self._settle(tid, res, "failed_terminal")
                return res
            time.sleep(0.05 * attempt)

    def _run_once(self, worker_name, task, tid, timeout):
        module = self.workers[worker_name]
        signal = threading.Event()
        self.log.append("dispatched", task_id=tid, worker=worker_name)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(module.run, task, signal)
            try:
                out = fut.result(timeout=timeout)
                if not isinstance(out, dict):
                    out = {"ok": False, "error": "worker returned non-dict"}
                return out
            except concurrent.futures.TimeoutError:
                signal.set()
                return {"ok": False, "error": "timeout after %ss" % timeout}
            except Exception as e:  # noqa: BLE001 - worker faults are data
                signal.set()
                return {"ok": False, "error": "worker raised: %s: %s"
                        % (type(e).__name__, e)}

    def _settle(self, tid, res, how):
        with self._lock:
            self._results[tid] = res
        self.log.append("settled", task_id=tid, how=how, ok=bool(res.get("ok")))

    def _note_success(self, worker_name):
        with self._lock:
            self._consec_fail[worker_name] = 0
            if worker_name in self._quarantined:
                self._probe_ok[worker_name] = self._probe_ok.get(worker_name, 0) + 1
                if self._probe_ok[worker_name] >= self.RECOVER_AFTER:
                    self._quarantined.discard(worker_name)
                    self._probe_ok[worker_name] = 0
                    self.log.append("recovered", worker=worker_name)

    def _note_failure(self, worker_name, tid, res):
        with self._lock:
            n = self._consec_fail.get(worker_name, 0) + 1
            self._consec_fail[worker_name] = n
            self.log.append("failed", task_id=tid, worker=worker_name,
                            error=str(res.get("error"))[:200], consec=n)
            if n >= self.QUARANTINE_AFTER and worker_name not in self._quarantined:
                self._quarantined.add(worker_name)
                self._probe_ok[worker_name] = 0
                self.log.append("quarantined", worker=worker_name)

    def worker_status(self):
        with self._lock:
            return {name: ("quarantined" if name in self._quarantined else "healthy")
                    for name in self.workers}

    # ---- recovery: resume what a crash interrupted ----
    # Read-only / idempotent capabilities replay automatically on boot.
    # Side-effecting capabilities are NEVER blind-replayed: a task that
    # was dispatched but never settled may have partially happened.
    # Those are deferred into the log for reconciliation by a mind.
    RECOVERY_SAFE = {
        "diag.check", "field.status", "capsule.verify", "capsule.load",
        "capsule.section", "fs.read", "fs.list", "notes.read",
        "notes.list", "notes.search", "web.search", "web.fetch",
    }

    def recover(self):
        submitted = {}
        settled = set()
        for e in self.log.entries():
            if e.get("type") == "submitted" and e.get("task_id"):
                submitted[e["task_id"]] = (e.get("capability"),
                                           e.get("args", {}))
            elif e.get("type") == "settled" and e.get("task_id"):
                settled.add(e["task_id"])
        replayed, deferred, skipped = [], [], []
        for tid, (cap, args) in submitted.items():
            if tid in settled:
                continue
            task = {"capability": cap, "args": args or {}}
            if make_task_id(task) != tid:
                self.log.append("recovery_skipped", task_id=tid,
                                capability=cap,
                                reason="cannot reconstruct task faithfully")
                skipped.append(tid)
            elif cap in self.RECOVERY_SAFE:
                self.log.append("recovery_replay", task_id=tid,
                                capability=cap)
                self.submit(task)
                replayed.append(tid)
            else:
                self.log.append(
                    "recovery_deferred", task_id=tid, capability=cap,
                    reason="side-effecting capability: reconcile by hand, "
                           "never blind-replay")
                deferred.append(tid)
        return {"replayed": replayed, "deferred": deferred,
                "skipped": skipped}


# ---------------------------------------------------------------- self-test
def _self_test():
    tmp = tempfile.mkdtemp(prefix="prime-kernel-test-")
    log1 = os.path.join(tmp, "a1.log")
    log2 = os.path.join(tmp, "a2.log")

    class OkWorker:
        CAPABILITIES = ["test.echo"]

        @staticmethod
        def run(task, signal):
            return {"ok": True, "echo": task["args"].get("v")}

    class FlakyWorker:
        CAPABILITIES = ["test.flaky"]
        calls = 0

        @staticmethod
        def run(task, signal):
            FlakyWorker.calls += 1
            if FlakyWorker.calls <= 2:
                raise RuntimeError("injected fault")
            return {"ok": True, "recovered": True}

    class DeadWorker:
        CAPABILITIES = ["test.dead"]

        @staticmethod
        def run(task, signal):
            raise RuntimeError("always fails")

    def run_suite(log_path):
        FlakyWorker.calls = 0
        k = Kernel(log_path=log_path)
        k.register("ok", OkWorker)
        k.register("flaky", FlakyWorker)
        k.register("dead", DeadWorker)
        results = []
        for i in range(50):
            if i % 5 == 4:
                t = {"capability": "test.dead", "args": {"i": i}}
            elif i % 5 == 3:
                t = {"capability": "test.flaky", "args": {"i": i}}
            else:
                t = {"capability": "test.echo", "args": {"v": i}}
            results.append(k.submit(t, timeout=5, max_retries=3))
        # idempotency: resubmit first task
        dup = k.submit({"capability": "test.echo", "args": {"v": 0}}, timeout=5)
        assert dup.get("_dedup") is True, "idempotency dedup failed"
        # determinism: same task id twice
        assert make_task_id({"capability": "a", "args": {"x": 1}}) == \
            make_task_id({"args": {"x": 1}, "capability": "a"})
        # PRNG determinism
        r1, r2 = mulberry32(1337), mulberry32(1337)
        assert [r1() for _ in range(5)] == [r2() for _ in range(5)]
        # every task settled (completed or terminal failure) - none lost
        assert len(results) == 50
        assert all("ok" in r for r in results)
        # dead worker quarantined
        assert k.worker_status()["dead"] == "quarantined"
        # chain verifies
        v = k.log.verify()
        assert v["ok"], "audit chain broken: %r" % v
        return k

    k1 = run_suite(log1)
    k2 = run_suite(log2)
    b1 = open(log1, "rb").read()
    b2 = open(log2, "rb").read()
    assert b1 == b2, "same-seed logs differ - nondeterminism!"
    print("kernel self-test: 50 tasks settled, quarantine OK, "
          "idempotency OK, chain verified (%d entries), byte-identical across seeds OK"
          % k1.log.verify()["entries"])
    print("SELF-TEST GREEN")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        _self_test()
    else:
        print("usage: python kernel.py --self-test")
