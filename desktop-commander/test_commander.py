#!/usr/bin/env python3
"""
Tests for Desktop Commander V1.

Boots commander.py on an ephemeral port with a throwaway data dir
(temp key, temp ledger), checks auth, exec, honest backend errors, and
the hash-chained ledger — then shuts the server down.
Run: python3 test_commander.py   (exit 0 = all green)
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
COMMANDER = os.path.join(HERE, "commander.py")

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s%s" % ("PASS" if cond else "FAIL", name,
                       (" — " + detail) if detail else ""))


def http(method, url, key=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if key is not None:
        req.add_header("X-Commander-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}


def read_until(proc, markers, limit=50):
    found = {}
    for _ in range(limit):
        line = proc.stdout.readline()
        if not line:
            break
        for m in markers:
            if line.startswith(m):
                found[m] = line[len(m):].strip()
        if len(found) == len(markers):
            break
    return found


def main():
    tmp = tempfile.mkdtemp(prefix="dc-test-")
    proc = subprocess.Popen(
        [sys.executable, COMMANDER, "--data-dir", tmp,
         "--host", "127.0.0.1", "--port", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        got = read_until(proc, ["COMMANDER KEY (shown once — save it now): ",
                                "LISTENING http://"])
        key = got.get("COMMANDER KEY (shown once — save it now): ", "")
        listening = got.get("LISTENING http://", "")
        check("server boots and prints key once", len(key) == 64,
              "key len %d" % len(key))
        check("server reports its bound port", ":" in listening, listening)
        base = "http://" + listening

        # key file hygiene
        key_path = os.path.join(tmp, "commander.key")
        mode = oct(os.stat(key_path).st_mode & 0o777)
        check("commander.key is mode 0600", mode == "0o600", mode)

        # auth
        st, _ = http("GET", base + "/status")
        check("GET /status without key -> 401", st == 401, "got %d" % st)
        st, _ = http("GET", base + "/status", key="0" * 64)
        check("GET /status with wrong key -> 401", st == 401, "got %d" % st)

        st, body = http("GET", base + "/status", key=key)
        check("GET /status with key -> 200", st == 200, "got %d" % st)
        check("status carries hostname/version/backends",
              bool(body.get("hostname")) and body.get("version")
              and "backends" in body)

        # exec
        st, body = http("POST", base + "/exec", key=key,
                        body={"command": "echo dc-roundtrip"})
        check("POST /exec echo round-trip",
              st == 200 and body.get("exit_code") == 0
              and "dc-roundtrip" in body.get("stdout", ""),
              "status %d" % st)
        st, _ = http("POST", base + "/exec",
                     body={"command": "echo nope"})
        check("POST /exec without key -> 401", st == 401, "got %d" % st)
        st, body = http("POST", base + "/exec", key=key,
                        body={"command": "exit 3"})
        check("POST /exec propagates exit code",
              st == 200 and body.get("exit_code") == 3)
        st, body = http("POST", base + "/exec", key=key,
                        body={"command": "sleep 5", "timeout_s": 1})
        check("POST /exec honors timeout",
              st == 200 and body.get("timed_out") is True)

        # backends: honest success-or-error, never a fake
        for route, payload, label in [
                ("/shot", {}, "shot"),
                ("/type", {"text": "hi"}, "type"),
                ("/click", {"x": 1, "y": 2}, "click"),
                ("/browser/render", {"url": "http://127.0.0.1:1/"},
                 "browser/render")]:
            st, body = http("POST", base + route, key=key, body=payload)
            honest = (st == 200 and body.get("ok")) or \
                     (st in (501, 502) and body.get("ok") is False
                      and body.get("error"))
            check("POST %s answers honestly (200 real or 501/502 named "
                  "error)" % label, honest, "status %d" % st)

        # ledger: independent chain recomputation in the test itself
        ledger_path = os.path.join(tmp, "ledger.jsonl")
        lines = [l for l in open(ledger_path, "rb").read().split(b"\n") if l]
        check("ledger recorded the actions", len(lines) >= 5,
              "%d entries" % len(lines))
        prev = hashlib.sha256(b"").hexdigest()
        chain_ok = True
        for i, line in enumerate(lines, 1):
            entry = json.loads(line.decode())
            if entry["seq"] != i or entry["prev_hash"] != prev:
                chain_ok = False
                break
            prev = hashlib.sha256(line).hexdigest()
        check("ledger chain verifies (independent recomputation)", chain_ok)
        check("ledger never contains the key",
              key.encode() not in open(ledger_path, "rb").read())

        # ledger: the server's own --verify agrees
        vfy = subprocess.run([sys.executable, COMMANDER, "--data-dir", tmp,
                              "--verify"], capture_output=True, text=True)
        check("commander.py --verify exits 0", vfy.returncode == 0,
              vfy.stdout.strip())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        check("server shut down", proc.poll() is not None)

    failed = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
