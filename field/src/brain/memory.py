"""Persistent session memory: hash-chained, credential-scrubbed, consolidated.

Raw entries are preserved. consolidate() folds them into durable facts /
preferences / decisions / commitments. recall() is keyword search over both.
"""
import json
import os
import re
import threading

from kernel import EventLog, canonical, sha256_hex

BRAIN_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_LOG = os.path.join(BRAIN_DIR, "memory.jsonl")
FACTS_FILE = os.path.join(BRAIN_DIR, "memory_facts.json")

# credential-shaped values are scrubbed BEFORE anything is written
SCRUB_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*\S+"),
     r"\1=[SCRUBBED]"),
    (re.compile(r"\bsk-[A-Za-z0-9]{10,}\b"), "[SCRUBBED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[SCRUBBED]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"), "bearer [SCRUBBED]"),
]


def scrub(text):
    if not isinstance(text, str):
        text = str(text)
    for pat, repl in SCRUB_PATTERNS:
        text = pat.sub(repl, text)
    return text


class Memory:
    def __init__(self, path=MEMORY_LOG):
        self.path = path
        self._lock = threading.Lock()
        self.seq = 0
        self.head = "GENESIS"
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    e = json.loads(line)
                    self.seq = e["seq"]
                    self.head = sha256_hex(line.encode("utf-8"))

    def add(self, kind, text, session="default"):
        text = scrub(text)
        with self._lock:
            self.seq += 1
            e = {"seq": self.seq, "kind": kind, "session": session,
                 "text": text[:4000], "prev": self.head}
            line = canonical(e)
            self.head = sha256_hex(line.encode("utf-8"))
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            return {"seq": self.seq, "hash": self.head}

    def recall(self, keyword, limit=10):
        kw = keyword.lower()
        hits = []
        if not os.path.exists(self.path):
            return hits
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                e = json.loads(line)
                if kw in e.get("text", "").lower():
                    hits.append(e)
        return hits[-limit:]

    def consolidate(self):
        """Fold raw entries into durable buckets. Heuristic + transparent."""
        buckets = {"facts": [], "preferences": [], "decisions": [],
                   "commitments": []}
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                entries = [json.loads(l) for l in f if l.strip()]
        else:
            entries = []
        for e in entries:
            t = e.get("text", "")
            low = t.lower()
            if low.startswith("fact:"):
                buckets["facts"].append(t[5:].strip())
            elif low.startswith("prefer:"):
                buckets["preferences"].append(t[7:].strip())
            elif low.startswith("decided:"):
                buckets["decisions"].append(t[8:].strip())
            elif low.startswith("commit:"):
                buckets["commitments"].append(t[7:].strip())
        # dedupe, keep order
        for k in buckets:
            seen, out = set(), []
            for v in buckets[k]:
                if v not in seen:
                    seen.add(v)
                    out.append(v)
            buckets[k] = out
        buckets["_entries"] = len(entries)
        with open(FACTS_FILE, "w", encoding="utf-8") as f:
            json.dump(buckets, f, indent=2)
        return {k: len(v) for k, v in buckets.items() if not k.startswith("_")}

    def facts(self):
        try:
            with open(FACTS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"facts": [], "preferences": [], "decisions": [],
                    "commitments": []}

    def verify(self):
        prev = "GENESIS"
        n = 0
        if not os.path.exists(self.path):
            return {"ok": True, "entries": 0}
        with open(self.path, encoding="utf-8") as f:
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
