#!/usr/bin/env python3
"""mesh-daemon.py — one long-running swarmgentic mesh node.

Runs a UnifiedNode (Track 1 transport + Track 5 trust gate + Track 3
coordinator + Track 4 field observer) as a persistent service:

  - Ed25519 identity generated ONCE into DATA_DIR/mesh-identity.key
    (32 raw bytes, chmod 600, never regenerated silently)
  - self-owned genesis: the node admits itself; the owner IS this node
    until Zachary joins it to a wider mesh out-of-band
  - /mesh-health on 127.0.0.1 (JSON: peers, members, coherence, log head)
  - hash-chained log at DATA_DIR/logs/mesh.log
  - periodic attestation broadcasts + seed-peer healer
    (the prototype transport can drop connections under crypto load;
    the healer redials — a demo crutch, documented in README)

Stdlib only. Loopback only. No telemetry. No hardcoded secrets.

Env:
  MESH_NAME           node name            (default: asus-mesh)
  MESH_HEALTH_PORT    /mesh-health port    (default: 18091)
  DATA_DIR            keys/state/logs      (default: ./mesh-data)
  MESH_SEEDS          "host:port,..." peers to dial (default: none)
  MESH_CAPABILITIES   comma list           (default: compute)
  ATTEST_INTERVAL_S   seconds between ATTEST broadcasts (default: 600)
  HEAL_INTERVAL_S     seconds between seed redials      (default: 60)

Usage:
  python3 mesh-daemon.py
  python3 mesh-daemon.py --verify-log DATA_DIR/logs/mesh.log
"""

import hashlib
import json
import os
import secrets
import signal
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

BIN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BIN)

from mesh.transport import mesh
from mesh.transport.mesh import Identity
from mesh.node.unified_node import UnifiedNode, CODE_HASH
from mesh.field.observer import FieldObserver


def getenv(name, default):
    return os.environ.get(name, default)


MESH_NAME = getenv("MESH_NAME", "asus-mesh")
MESH_HEALTH_PORT = int(getenv("MESH_HEALTH_PORT", "18091"))
DATA_DIR = getenv("DATA_DIR", os.path.join(os.getcwd(), "mesh-data"))
SEEDS = [s.strip() for s in getenv("MESH_SEEDS", "").split(",") if s.strip()]
CAPABILITIES = [c.strip() for c in getenv("MESH_CAPABILITIES", "compute")
                .split(",") if c.strip()]
ATTEST_INTERVAL_S = float(getenv("ATTEST_INTERVAL_S", "600"))
HEAL_INTERVAL_S = float(getenv("HEAL_INTERVAL_S", "60"))
BIND = "127.0.0.1"


class MeshLog:
    """Append-only hash-chained JSONL log (same pattern as the node
    supervisor's NodeLog). Tampering anywhere breaks the tail."""

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


def ensure_identity(path):
    """Generate the node's Ed25519 secret ONCE. Never regenerate silently."""
    if os.path.exists(path):
        with open(path, "rb") as f:
            sk = f.read()
        if len(sk) != 32:
            raise ValueError("identity key corrupt: %s" % path)
        return sk, False
    sk = secrets.token_bytes(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, sk)
    finally:
        os.close(fd)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return sk, True


def port_open(port, timeout=0.5):
    try:
        with socket.create_connection((BIND, port), timeout=timeout):
            return True
    except OSError:
        return False


class Daemon:
    def __init__(self):
        self.data_dir = DATA_DIR
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "logs"), exist_ok=True)
        self.pidfile = os.path.join(self.data_dir, "mesh.pid")
        self.log = MeshLog(os.path.join(self.data_dir, "logs", "mesh.log"))
        self.stop_flag = False
        self.start_ts = time.time()
        self.node = None
        self.observer = None
        self._server = None
        self._last_attest = 0.0

    # ---- lifecycle ----
    def check_single(self):
        if os.path.exists(self.pidfile):
            try:
                with open(self.pidfile) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                print("mesh-daemon already running (pid %d) — refusing "
                      "double start" % pid, file=sys.stderr)
                return False
            except (OSError, ValueError):
                pass  # stale pidfile
        with open(self.pidfile, "w") as f:
            f.write(str(os.getpid()))
        return True

    def load_or_create_node(self):
        key_path = os.path.join(self.data_dir, "mesh-identity.key")
        sk, fresh = ensure_identity(key_path)
        ident = Identity(sk)
        state_path = os.path.join(self.data_dir, "mesh-node.json")
        if os.path.exists(state_path):
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
            if state.get("node_id") != ident.node_id:
                self.log.append("identity-mismatch",
                                "state file does not match key; re-genesis")
                state = None
        else:
            state = None
        if state is None:
            # Self-owned genesis: this node is its own owner until
            # Zachary joins it to a wider mesh out-of-band.
            state = {"node_id": ident.node_id,
                     "pubkey_hex": ident.pk.hex(),
                     "owner_id": ident.node_id,
                     "owner_pubkey_hex": ident.pk.hex(),
                     "code_hash": CODE_HASH,
                     "created_ts": time.time()}
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            self.log.append("genesis",
                            "identity %screated; self-owned node %s"
                            % (" " if fresh else "loaded, ",
                               ident.node_id[:12]))
        self.node = UnifiedNode(MESH_NAME, CAPABILITIES,
                                state["owner_id"], state["owner_pubkey_hex"],
                                identity=ident)
        self.node.admit_local(ident.node_id, ident.pk.hex(), CODE_HASH,
                              admitted_by=state["owner_id"])
        self.observer = FieldObserver([ident.node_id])
        return fresh

    # ---- health ----
    def health_payload(self):
        n = self.node
        return {"node": MESH_NAME, "ok": True,
                "node_id": n.node_id, "pubkey": n.pubkey_hex,
                "mesh_port": n.transport.port,
                "peers": sorted(n.peer_ids),
                "members": len(n.gate.members),
                "capabilities": CAPABILITIES,
                "uptime_s": round(time.time() - self.start_ts, 1),
                "coherence_R": round(self.observer.coherence, 4),
                "gossip_rounds": self.observer.rounds,
                "log_head": self.log.prev[:16], "bind": BIND}

    def serve_health(self):
        daemon = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/mesh-health":
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps(daemon.health_payload()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self._server = HTTPServer((BIND, MESH_HEALTH_PORT), H)
        self._server.serve_forever()

    # ---- background work ----
    def heal_seeds(self):
        for seed in SEEDS:
            if self.stop_flag:
                return
            try:
                host, port = seed.rsplit(":", 1)
                port = int(port)
            except ValueError:
                self.log.append("bad-seed", "ignoring malformed seed %r"
                                % seed)
                continue
            try:
                peer_id = self.node.connect(host, port, timeout=10.0)
                self.log.append("seed-dial", "dialed %s -> %s"
                                % (seed, peer_id[:12]))
            except Exception as ex:
                self.log.append("seed-dial-fail", "%s: %s" % (seed, ex))

    def worker(self):
        next_heal = 0.0
        while not self.stop_flag:
            now = time.time()
            if now >= next_heal:
                self.heal_seeds()
                try:
                    self.observer.on_gossip_round()
                except Exception:
                    pass
                next_heal = now + HEAL_INTERVAL_S
            if now - self._last_attest >= ATTEST_INTERVAL_S:
                try:
                    self.node.attest(
                        uptime_s=round(now - self.start_ts, 1))
                    self._last_attest = now
                except Exception as ex:
                    self.log.append("attest-fail", str(ex))
            self.stop_flag_wait(1.0)

    def stop_flag_wait(self, secs):
        end = time.time() + secs
        while time.time() < end and not self.stop_flag:
            time.sleep(0.1)

    # ---- run ----
    def run(self):
        if not self.check_single():
            return 2
        self.load_or_create_node()
        self.node.start()
        self.log.append("start",
                        "mesh node %s listening on %s:%d (health :%d)"
                        % (self.node.node_id[:12], BIND,
                           self.node.transport.port, MESH_HEALTH_PORT))

        def _sig(signum, frame):
            self.stop_flag = True

        for s in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(s, _sig)
            except (OSError, ValueError):
                pass

        t = threading.Thread(target=self.serve_health, daemon=True)
        t.start()
        w = threading.Thread(target=self.worker, daemon=True)
        w.start()
        try:
            while not self.stop_flag:
                time.sleep(0.5)
        finally:
            self.shutdown()
        return 0

    def shutdown(self):
        try:
            if self.node is not None:
                self.node.stop()
        except Exception:
            pass
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
        self.log.append("shutdown", "mesh daemon stopped cleanly")
        self.log.close()
        try:
            os.remove(self.pidfile)
        except OSError:
            pass


def main(argv):
    if "--verify-log" in argv:
        i = argv.index("--verify-log")
        ok, info = MeshLog.verify(argv[i + 1])
        print("chain ok, head %s" % info if ok
              else "CHAIN BROKEN at line %s" % info)
        return 0 if ok else 1
    return Daemon().run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
