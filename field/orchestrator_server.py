#!/usr/bin/env python3
"""Unified Field — orchestrator HTTP face (port 18082, loopback).

Thin face over swarm_orchestrator.SwarmOrchestrator, written 2026-10-21
to give the field manifest's orchestrator node a live service:
  GET  /status -> {ok, ledger: verify()}
  POST /task   -> {capability, args} -> gates -> route -> execute -> ledger
The orchestrator's own gates (Zadkiel veto AND PRIME approval) and its
hash-chained ledger do the real work; this file only carries HTTP.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Paths are env-overridable so the same file runs on the VM proving
# ground and on Zachary's Windows desktop (C:\sixteen\...).
BRAIN_DIR = os.environ.get("HF_BRAIN_DIR", "/home/hatch/workspace/prime-brain-build")
SWARM_DIR = os.environ.get("HF_SWARM_DIR", "/home/hatch/workspace/swarm-orchestrator")
WORKDIR = os.environ.get("HF_ORCH_WORKDIR", "/home/hatch/workspace/field/orchestrator-data")

sys.path.insert(0, SWARM_DIR)
sys.path.insert(0, BRAIN_DIR)

from swarm_orchestrator.orchestrator import SwarmOrchestrator, OrchestratorError  # noqa: E402

ORCH = SwarmOrchestrator(WORKDIR)


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            v = ORCH.verify()
            self._json(200, {"ok": True, "service": "orchestrator",
                             "ledger": v})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path != "/task":
            self._json(404, {"ok": False, "error": "not found"})
            return
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            data = {}
        if not data.get("capability"):
            self._json(400, {"ok": False, "error": "capability required"})
            return
        try:
            res = ORCH.submit(data)
            self._json(200, {"ok": True, **res})
        except OrchestratorError as e:
            self._json(403, {"ok": False, "error": str(e)})

    def log_message(self, fmt, *args):
        sys.stderr.write("ORCH %s\n" % (fmt % args))


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", 18082), Handler)
    print("orchestrator face on 127.0.0.1:18082, workdir %s" % WORKDIR)
    srv.serve_forever()
