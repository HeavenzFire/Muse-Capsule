"""One hash-chained log across the orchestrated flow.

Each subsystem keeps its own chain (PRIME audit.log, mesh per-sender chains,
Sixteen Metatron ledger). The orchestrator ledger EXTENDS them, never
replaces: every entry records the subsystem chain head it follows, so the
orchestrated flow is verifiable end-to-end and each subsystem's own
verification still passes independently.

Entry: {seq, t (logical tick), type, prev, task_id, subsystem, gates,
        subsystem_head, detail}
Chain: entry hash = sha256(canonical line). Same construction as
prime-brain-build/kernel.py EventLog — verify() is the same algorithm.
"""
import os
import threading

from .canonical import canonical, sha256_hex


class OrchestratorLedger:
    def __init__(self, path):
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
                e = __import__("json").loads(line)
                self.seq = e["seq"]
                self.tick = e["t"]
                self.head = sha256_hex(line.encode("utf-8"))

    def append(self, etype, task_id="", subsystem="", gates=None,
               subsystem_head="", detail=""):
        with self._lock:
            self.seq += 1
            self.tick += 1
            e = {
                "seq": self.seq,
                "t": self.tick,
                "type": etype,
                "prev": self.head,
                "task_id": task_id,
                "subsystem": subsystem,
                "gates": gates or [],
                "subsystem_head": subsystem_head,
                "detail": detail,
            }
            line = canonical(e)
            h = sha256_hex(line.encode("utf-8"))
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            self.head = h
            return {"seq": self.seq, "hash": h}

    def verify(self):
        import json
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
