"""Hash-chained audit log for the gateway. Every request, no silent calls.

Line format (canonical JSON, one per line, no trailing newline in hash):
  {"seq","ts","client","scope","method","path","status",
   "req_sha","res_sha","capability","verdict","prev","hash"}

Chain rule (matches the settlement ledger convention):
  prev  = sha256 of the previous line's exact text (no trailing newline)
  hash  = sha256 of this line's text with the "hash" field blanked.

Bodies are never stored -- only their sha256. Secrets can't leak from
the log, and the log still proves exactly what went over the wire.
"""
import hashlib
import json
import os
import threading
import time

DATA_DIR_ENV = "SOVEREIGN_GATEWAY_DATA"


def data_dir():
    d = os.environ.get(DATA_DIR_ENV,
                       os.path.join(os.path.dirname(
                           os.path.abspath(__file__)), "..", "data"))
    os.makedirs(d, exist_ok=True)
    return d


def _path():
    return os.path.join(data_dir(), "audit.jsonl")


def _sha(b):
    if isinstance(b, str):
        b = b.encode("utf-8")
    return hashlib.sha256(b or b"").hexdigest()


class AuditLog:
    def __init__(self, path=None):
        self.path = path or _path()
        self._lock = threading.Lock()
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)

    def _last_line(self):
        if not os.path.isfile(self.path):
            return None, 0
        last, seq = None, 0
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.strip():
                    last, seq = line, seq + 1
        return last, seq

    def append(self, method, path, status, client="anon", scope="-",
               req_body=b"", res_body=b"", capability="", verdict=""):
        with self._lock:
            last, seq = self._last_line()
            prev = _sha(last) if last else "GENESIS"
            entry = {
                "seq": seq + 1,
                "ts": int(time.time()),
                "client": client,
                "scope": scope,
                "method": method,
                "path": path,
                "status": status,
                "req_sha": _sha(req_body),
                "res_sha": _sha(res_body),
                "capability": capability,
                "verdict": verdict,
                "prev": prev,
                "hash": "",
            }
            line = json.dumps(entry, sort_keys=True, separators=(",", ":"))
            entry["hash"] = _sha(line)
            line = json.dumps(entry, sort_keys=True, separators=(",", ":"))
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            return entry

    def verify(self):
        """Returns {"ok": bool, "entries": n, "head": hash|None, "break_at": seq|None}."""
        if not os.path.isfile(self.path):
            return {"ok": True, "entries": 0, "head": None, "break_at": None}
        prev_expected, seq, head = "GENESIS", 0, None
        with open(self.path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line.strip():
                    continue
                seq += 1
                try:
                    e = json.loads(line)
                except ValueError:
                    return {"ok": False, "entries": seq, "head": head,
                            "break_at": seq}
                if e.get("prev") != prev_expected:
                    return {"ok": False, "entries": seq, "head": head,
                            "break_at": seq}
                check = dict(e)
                check["hash"] = ""
                if _sha(json.dumps(check, sort_keys=True,
                                   separators=(",", ":"))) != e.get("hash"):
                    return {"ok": False, "entries": seq, "head": head,
                            "break_at": seq}
                head = e["hash"]
                prev_expected = _sha(line)
        return {"ok": True, "entries": seq, "head": head, "break_at": None}
