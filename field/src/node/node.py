#!/usr/bin/env python3
"""node.py — mesh supervisor (adapted from Track 2 for the ASUS node).

Supervises the mesh-daemon as a child process: restarts it on crash
(bounded, with backoff), parks it if it keeps dying, and exposes
/node-health. The box and the terminal run as their own scheduled tasks;
this supervisor owns only the mesh daemon.

Stdlib only. Binds 127.0.0.1 only. Makes no external connections.

Usage:
    python3 node.py --config config.yaml
    python3 node.py --verify-log <data>/node.log
"""

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

BIN = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "node_name": "asus-node",
    "bind": "127.0.0.1",
    "mesh_health_port": 18091,
    "node_port": 18090,
    "data_dir": "../data",
    "mesh_name": "asus-mesh",
    "mesh_seeds": "",
    "mesh_capabilities": "compute",
    "attest_interval_s": 600.0,
    "max_restarts": 5,
    "restart_backoff_base": 1.0,
    "shutdown_timeout": 5,
}

INT_KEYS = ("mesh_health_port", "node_port", "max_restarts",
            "shutdown_timeout")
FLOAT_KEYS = ("restart_backoff_base", "attest_interval_s")


def load_config(path):
    """Minimal flat-YAML reader (key: value, # comments). Stdlib only."""
    cfg = dict(DEFAULTS)
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                v = v[1:-1]
            cfg[k] = v
    for k in INT_KEYS:
        cfg[k] = int(cfg[k])
    for k in FLOAT_KEYS:
        cfg[k] = float(cfg[k])
    return cfg


class NodeLog:
    """Append-only hash-chained JSONL log."""

    def __init__(self, path):
        self.path = path
        self.prev = "GENESIS"
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.prev = json.loads(line)["hash"]
        self._f = open(path, "a", encoding="utf-8")

    def append(self, kind, msg):
        entry = {"ts": time.time(), "kind": kind, "msg": msg,
                 "prev": self.prev}
        body = json.dumps(entry, sort_keys=True)
        h = hashlib.sha256((self.prev + "\n" + body).encode()).hexdigest()
        entry["hash"] = h
        self._f.write(json.dumps(entry) + "\n")
        self._f.flush()
        self.prev = h
        return h

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass

    @staticmethod
    def verify(path):
        prev = "GENESIS"
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                e = json.loads(line)
                body = json.dumps(
                    {k: e[k] for k in ("ts", "kind", "msg", "prev")},
                    sort_keys=True)
                h = hashlib.sha256((prev + "\n" + body).encode()).hexdigest()
                if e.get("prev") != prev or e.get("hash") != h:
                    return False, i
                prev = e["hash"]
        return True, prev


def port_open(bind, port, timeout=0.5):
    try:
        with socket.create_connection((bind, port), timeout=timeout):
            return True
    except OSError:
        return False


class Child:
    def __init__(self, name, script, env, log_path, port):
        self.name = name
        self.script = script
        self.env = env
        self.log_path = log_path
        self.port = port
        self.proc = None
        self.restarts = 0
        self.parked = False
        self.pid = None

    def start(self):
        logf = open(self.log_path, "a", encoding="utf-8")
        kwargs = dict(env=self.env, cwd=BIN,
                      stdout=logf, stderr=subprocess.STDOUT,
                      stdin=subprocess.DEVNULL)
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        self.proc = subprocess.Popen([sys.executable, self.script], **kwargs)
        self.pid = self.proc.pid

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def ready(self, bind):
        return self.alive() and port_open(bind, self.port)

    def stop(self, timeout):
        if self.proc is None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        except Exception:
            pass


class Node:
    def __init__(self, cfg):
        self.cfg = cfg
        self.bind = cfg["bind"]
        if self.bind != "127.0.0.1":
            raise ValueError("refusing non-loopback bind: %r" % self.bind)
        self.data_dir = cfg["data_dir"]
        if not os.path.isabs(self.data_dir):
            self.data_dir = os.path.normpath(os.path.join(BIN, self.data_dir))
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "logs"), exist_ok=True)
        self.pidfile = os.path.join(self.data_dir, "node.pid")
        self.log = NodeLog(os.path.join(self.data_dir, "node.log"))
        self.stop_flag = False
        self.start_ts = time.time()
        self.children = {}
        self._server = None

    def check_single(self):
        if os.path.exists(self.pidfile):
            try:
                with open(self.pidfile) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                print("node already running (pid %d) — refusing double "
                      "start" % pid, file=sys.stderr)
                return False
            except (OSError, ValueError):
                pass  # stale pidfile
        with open(self.pidfile, "w") as f:
            f.write(str(os.getpid()))
        return True

    def build_children(self):
        env_base = dict(os.environ)
        mesh_env = dict(env_base)
        mesh_env.update({
            "MESH_NAME": self.cfg["mesh_name"],
            "MESH_HEALTH_PORT": str(self.cfg["mesh_health_port"]),
            "DATA_DIR": os.path.join(self.data_dir, "mesh"),
            "MESH_SEEDS": self.cfg["mesh_seeds"],
            "MESH_CAPABILITIES": self.cfg["mesh_capabilities"],
            "ATTEST_INTERVAL_S": str(self.cfg["attest_interval_s"]),
        })
        logs = os.path.join(self.data_dir, "logs")
        self.children = {
            "mesh-daemon": Child(
                "mesh-daemon", os.path.join(BIN, "mesh-daemon.py"), mesh_env,
                os.path.join(logs, "mesh-daemon.log"),
                self.cfg["mesh_health_port"]),
        }

    def health_payload(self):
        kids = {}
        all_ok = True
        for name, c in self.children.items():
            ok = c.ready(self.bind)
            all_ok = all_ok and ok
            kids[name] = {"running": c.alive(), "ready": ok, "pid": c.pid,
                          "restarts": c.restarts, "parked": c.parked}
        return {"node": self.cfg["node_name"], "ok": all_ok,
                "uptime_s": round(time.time() - self.start_ts, 1),
                "children": kids, "log_head": self.log.prev,
                "bind": self.bind}

    def serve_health(self):
        node = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/node-health":
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps(node.health_payload()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self._server = HTTPServer((self.bind, self.cfg["node_port"]), H)
        self._server.serve_forever()

    def supervise(self):
        backoff = self.cfg["restart_backoff_base"]
        while not self.stop_flag:
            for name, c in self.children.items():
                if self.stop_flag:
                    break
                if c.alive() or c.parked:
                    continue
                if c.restarts >= self.cfg["max_restarts"]:
                    c.parked = True
                    self.log.append("parked",
                                    "%s exceeded %d restarts; parked"
                                    % (name, self.cfg["max_restarts"]))
                    continue
                wait = backoff * (2 ** c.restarts)
                c.restarts += 1
                self.log.append("restart",
                                "%s died; restart #%d in %.1fs"
                                % (name, c.restarts, wait))
                time.sleep(wait)
                if self.stop_flag:
                    break
                c.start()
                self.log.append("started", "%s pid %d" % (name, c.pid))
            time.sleep(0.5)

    def run(self):
        if not self.check_single():
            return 2
        self.log.append("boot", "node %s starting" % self.cfg["node_name"])
        self.build_children()
        for name, c in self.children.items():
            c.start()
            self.log.append("started", "%s pid %d" % (name, c.pid))

        def _sig(signum, frame):
            self.stop_flag = True

        for s in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(s, _sig)
            except (OSError, ValueError):
                pass

        t = threading.Thread(target=self.serve_health, daemon=True)
        t.start()
        self.log.append("health", "listening on %s:%d"
                        % (self.bind, self.cfg["node_port"]))
        try:
            self.supervise()
        finally:
            self.shutdown()
        return 0

    def shutdown(self):
        for name, c in self.children.items():
            c.stop(self.cfg["shutdown_timeout"])
            self.log.append("stopped", "%s stopped" % name)
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
        self.log.append("shutdown", "node stopped cleanly")
        self.log.close()
        try:
            os.remove(self.pidfile)
        except OSError:
            pass


def main(argv):
    if "--verify-log" in argv:
        i = argv.index("--verify-log")
        ok, info = NodeLog.verify(argv[i + 1])
        print("chain ok, head %s" % info if ok
              else "CHAIN BROKEN at line %s" % info)
        return 0 if ok else 1
    cfg_path = os.path.join(BIN, "config.yaml")
    if "--config" in argv:
        cfg_path = argv[argv.index("--config") + 1]
    cfg = load_config(cfg_path)
    return Node(cfg).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
