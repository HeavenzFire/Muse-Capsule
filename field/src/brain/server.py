#!/usr/bin/env python3
"""PRIME LAN server on port 18081 (stdlib only).

- GET  /status      -> health, mode, workers, audit head
- POST /chat        -> {"text": "...", "session": "..."} -> entity reply
- POST /consolidate -> memory consolidation
- POST /approve     -> {"task_id": "..."} -> consent gate approval

Binds 0.0.0.0:18081. Allow Python through Windows Firewall on
PRIVATE networks only.
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BRAIN_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BRAIN_DIR)

from kernel import Kernel  # noqa: E402
from memory import Memory  # noqa: E402
import entity  # noqa: E402

PORT = 18081
STARTED = time.time()

kernel = Kernel()
memory = Memory()

# register workers
from workers import shell_worker, fs_worker, browse_worker, web_worker, \
    notes_worker, diagnostics_worker, capsule_worker, \
    field_worker, verify_worker  # noqa: E402

kernel.register("shell", shell_worker)
kernel.register("fs", fs_worker)
kernel.register("browse", browse_worker)
kernel.register("web", web_worker)
kernel.register("notes", notes_worker)
kernel.register("diagnostics", diagnostics_worker)
kernel.register("capsule", capsule_worker)
kernel.register("field", field_worker)
kernel.register("verify", verify_worker)

# Resume anything a previous crash interrupted (safe capabilities
# replay; side-effecting ones are deferred in the log, never replayed).
kernel.recover()

_capsule_cache = {}

# live activity feed: session -> [events]; the app polls GET /activity
_activity = {}
_activity_lock = threading.Lock()


def emit_event(session, event):
    with _activity_lock:
        buf = _activity.setdefault(session, [])
        buf.append({"n": len(buf), "t": time.time(), **event})
        del buf[:-200]  # keep last 200 per session


def get_activity(session, since=0):
    with _activity_lock:
        return [e for e in _activity.get(session, []) if e["n"] > since]


def get_capsule():
    res = kernel.submit({"capability": "capsule.load", "args": {}},
                        timeout=15)
    if res.get("ok"):
        return res
    return {"mode": "LIMITED", "user": "Zachary", "boundaries": [],
            "standing_orders": [], "projects": [], "identity": {}}


class Handler(BaseHTTPRequestHandler):
    server_version = "PRIME/1.0"

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        """API key gate. BRAIN_API_KEY unset = LAN-trust mode (no gate).
        Set = every endpoint requires X-API-Key header. Required before
        any internet exposure."""
        want = os.environ.get("BRAIN_API_KEY", "")
        if not want:
            return True
        return self.headers.get("X-API-Key") == want

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return {}

    def do_GET(self):
        if not self._authorized():
            self._json(401, {"ok": False, "error": "missing or bad X-API-Key"})
            return
        if self.path == "/status":
            workers = kernel.worker_status()
            chain = kernel.log.verify()
            self._json(200, {
                "ok": True,
                "mode": get_capsule().get("mode", "LIMITED"),
                "model": entity.MODEL,
                "workers": workers,
                "uptime_s": int(time.time() - STARTED),
                "audit_head": chain.get("head"),
                "audit_entries": chain.get("entries"),
            })
        elif self.path.startswith("/activity"):
            import urllib.parse
            qs = urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query)
            session = qs.get("session", ["default"])[0]
            since = int(qs.get("since", ["0"])[0] or 0)
            self._json(200, {"ok": True, "session": session,
                             "events": get_activity(session, since)})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if not self._authorized():
            self._json(401, {"ok": False, "error": "missing or bad X-API-Key"})
            return
        data = self._body()
        if self.path == "/chat":
            text = data.get("text", "")
            session = data.get("session", "default")
            agent = data.get("agent", {}) or {}
            tools_allowed = agent.get("tools_allowed")
            offline = bool(data.get("offline", False))
            if not text.strip():
                self._json(400, {"ok": False, "error": "empty text"})
                return
            capsule = get_capsule()

            def on_event(ev):
                emit_event(session, ev)

            try:
                out = entity.run_turn(text, kernel, memory, capsule,
                                      session=session,
                                      tools_allowed=tools_allowed,
                                      offline=offline,
                                      on_event=on_event)
            except Exception as e:  # noqa: BLE001
                out = {"text": "entity error: %s" % e, "vetoed": False,
                       "route": "error", "capsule": capsule.get("mode")}
            out["rung"] = out.get("route", "").split("-")[-1] \
                if out.get("route", "").startswith("entity-") else out.get("route")
            out["offline"] = offline
            self._json(200, out)
        elif self.path == "/task":
            # Direct deterministic dispatch: a task addressed to a worker
            # capability executes through the kernel without a model rung.
            # Worker-side gates (approval checks, allowlists) still apply;
            # the kernel's ledger records submitted/dispatched/settled.
            cap = data.get("capability", "")
            if not cap:
                self._json(400, {"ok": False, "error": "capability required"})
                return
            task = {"capability": cap, "args": data.get("args", {}) or {}}
            timeout = min(int(data.get("timeout", 60) or 60), 300)
            res = kernel.submit(task, timeout=timeout)
            from kernel import make_task_id
            self._json(200, dict(res, task_id=make_task_id(task),
                                 capability=cap))
        elif self.path == "/consolidate":
            counts = memory.consolidate()
            self._json(200, {"ok": True, "counts": counts})
        elif self.path == "/approve":
            tid = data.get("task_id", "")
            if not tid:
                self._json(400, {"ok": False, "error": "task_id required"})
                return
            kernel.approve(tid)
            self._json(200, {"ok": True, "approved": tid})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def log_message(self, fmt, *args):
        sys.stderr.write("PRIME %s\n" % (fmt % args))


if __name__ == "__main__":
    # API key bootstrap: if BRAIN_API_KEY is not set, mint one, save it to
    # brain.key, and require it. The key is the phone app's credential.
    import secrets
    key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "brain.key")
    if not os.environ.get("BRAIN_API_KEY"):
        if os.path.isfile(key_file):
            with open(key_file) as f:
                os.environ["BRAIN_API_KEY"] = f.read().strip()
        else:
            new_key = secrets.token_urlsafe(32)
            with open(key_file, "w") as f:
                f.write(new_key)
            os.environ["BRAIN_API_KEY"] = new_key
            print("NEW BRAIN_API_KEY minted -> brain.key (give it to the phone app)")
    import scheduler
    _sched_stop = scheduler.start(kernel, memory, get_capsule)
    print("scheduler: on (tasks.json)")
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("PRIME brain on 0.0.0.0:%d  (model %s)" % (PORT, entity.MODEL))
    print(" capsule: %s" % get_capsule().get("mode"))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _sched_stop.set()
