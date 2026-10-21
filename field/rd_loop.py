#!/usr/bin/env python3
"""Unified Field — standing R&D loop (priority 4).

Research -> plan -> implement -> test -> review -> integrate, in the
only form a deterministic loop may honestly run: it works the backlog
in field/backlog.json, runs every machine-checkable verification it
can, records evidence in a hash-chained cycle log, and NEVER
terminates the pipeline. Items that need a mind stay open for the
next Muse pass or for GPT via the capsule repo — the loop queues,
it does not pretend to think.

Cycle: every RD_INTERVAL_S (default 600). A failed check is data,
recorded with its evidence; the loop continues.
Log: field/rd-log.jsonl — each line carries prev + hash where
hash = sha256(prev + canonical(entry-without-hash)).
"""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

FIELD = os.path.dirname(os.path.abspath(__file__))
BACKLOG = os.path.join(FIELD, "backlog.json")
LOG = os.path.join(FIELD, "rd-log.jsonl")
BRAIN = "http://127.0.0.1:18081"
INTERVAL = int(os.environ.get("RD_INTERVAL_S", "600"))


def _brain_key():
    try:
        with open("/home/hatch/workspace/prime-brain-build/brain.key") as f:
            return f.read().strip()
    except OSError:
        return ""


def brain_task(capability, args=None):
    req = urllib.request.Request(
        BRAIN + "/task",
        data=json.dumps({"capability": capability,
                         "args": args or {}}).encode(),
        headers={"Content-Type": "application/json",
                 "X-API-Key": _brain_key()})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def run_check(check):
    """Return (passed, evidence). Check kinds are deliberately few."""
    kind = check.get("kind")
    if kind == "brain_task":
        res = brain_task(check["capability"], check.get("args"))
        expect = check.get("expect", {})
        ok = all(res.get(k) == v for k, v in expect.items())
        return ok, {k: res.get(k) for k in list(expect) + ["ok"]}
    if kind == "argv":
        p = subprocess.run(check["argv"], capture_output=True, text=True,
                           timeout=check.get("timeout", 120),
                           cwd=check.get("cwd") or None)
        tail = (p.stdout + p.stderr).strip().splitlines()
        return p.returncode == 0, {"rc": p.returncode,
                                   "tail": tail[-1] if tail else ""}
    if kind == "file_exists":
        return os.path.isfile(check["path"]), {"path": check["path"]}
    return False, {"error": "unknown check kind: %r" % kind}


def log_cycle(entry):
    prev = "GENESIS"
    if os.path.exists(LOG):
        with open(LOG, "rb") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        if lines:
            prev = json.loads(lines[-1]).get("hash", "GENESIS")
    entry = dict(entry, prev=prev)
    canon = json.dumps(entry, sort_keys=True).encode()
    entry["hash"] = hashlib.sha256(prev.encode() + canon).hexdigest()
    with open(LOG, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry["hash"]


def load_backlog():
    try:
        with open(BACKLOG) as f:
            return json.load(f)
    except Exception:
        return {"items": []}


def save_backlog(data):
    tmp = BACKLOG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, BACKLOG)


def cycle(n):
    data = load_backlog()
    results = []
    changed = False
    for item in data.get("items", []):
        if item.get("status") == "done":
            continue
        check = item.get("check")
        if not check:
            results.append({"id": item["id"], "state": "awaiting_mind"})
            continue
        try:
            passed, ev = run_check(check)
        except Exception as e:  # noqa: BLE001 - a failed check is data
            passed, ev = False, {"error": "%s: %s" % (type(e).__name__, e)}
        results.append({"id": item["id"], "passed": passed, "evidence": ev})
        if passed:
            item["status"] = "done"
            item["done_evidence"] = ev
            item["done_cycle"] = n
            changed = True
    if changed:
        save_backlog(data)
    h = log_cycle({"cycle": n, "ts": int(time.time()), "results": results})
    print("rd cycle %d -> %s (%d checks)" % (n, h[:12], len(results)),
          flush=True)
    return results


def main():
    n = 0
    while True:
        n += 1
        try:
            cycle(n)
        except Exception as e:  # noqa: BLE001 - the loop does not die
            print("rd cycle %d error: %s" % (n, e), flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
