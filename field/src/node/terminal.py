#!/usr/bin/env python3
"""Sovereign Terminal Server — our own terminal, our own protocol.

A local terminal server for Zachary's machine. The phone (Sovereign ONE)
and any LAN browser talk to THIS instead of a Microsoft console:

  - persistent shell sessions (PowerShell on Windows, $TERM_SHELL elsewhere)
  - script library: one-tap runs of .ps1 files, no paste-mangling ever
  - every input/output chunk appended to a hash-chained session log
  - key auth on every API call; nothing here phones home

Stdlib only. No installs, no accounts, no cloud.

  python3 terminal.py            # BIND=0.0.0.0 PORT=18088 (env overrides)
  TERM_SHELL="/bin/bash" python3 terminal.py   # test on Linux

Protocol (all JSON unless noted, all need X-Term-Key except GET /):
  POST /api/session                  -> {"id": "..."}
  POST /api/session/<id>/input       {"data": "..."} -> {"ok": true}
  GET  /api/session/<id>/output?cursor=N -> {"cursor": M, "data": "..."}
  POST /api/session/<id>/run         {"script": "01-audit.ps1"} -> {"ok": true}
  GET  /api/scripts                  -> {"scripts": ["01-audit.ps1", ...]}
  DELETE /api/session/<id>           -> {"ok": true}
  GET  /                            -> the terminal web UI
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
SCRIPTS = os.path.join(HERE, "scripts")
SESSDIR = os.path.join(HERE, "sessions")
os.makedirs(SESSDIR, exist_ok=True)
os.makedirs(SCRIPTS, exist_ok=True)

BIND = os.environ.get("BIND", "0.0.0.0")
PORT = int(os.environ.get("PORT", "18088"))
KEY = os.environ.get("TERM_KEY") or secrets.token_hex(16)
SHELL_CMD = os.environ.get("TERM_SHELL", "powershell.exe -NoLogo -NoExit -Command -")
IDLE_TIMEOUT = int(os.environ.get("IDLE_TIMEOUT", "1800"))  # reap after 30 min idle
MAX_SESSIONS = 8
MAX_BODY = 1 << 20  # 1 MB per request


def chain_hash(prev, payload):
    h = hashlib.sha256()
    h.update(prev.encode("utf-8"))
    h.update(payload.encode("utf-8", "replace"))
    return h.hexdigest()


class TermSession:
    """One persistent shell with a reader thread and a hash-chained log."""

    def __init__(self, sid):
        self.id = sid
        self.lock = threading.Lock()
        self.buf = bytearray()
        self.log_path = os.path.join(SESSDIR, sid + ".jsonl")
        self.prev_hash = "GENESIS"
        self.seq = 0
        self.last_active = time.time()
        args = SHELL_CMD.split()
        self.proc = subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=0,
            cwd=os.path.expanduser("~"))
        self.alive = True
        self.reader = threading.Thread(target=self._pump, daemon=True)
        self.reader.start()

    def _pump(self):
        try:
            while True:
                chunk = self.proc.stdout.read(1024)
                if not chunk:
                    break
                with self.lock:
                    self.buf += chunk
                    self.last_active = time.time()
                self._log("out", chunk)
        except Exception:
            pass
        finally:
            self.alive = False

    def _log(self, direction, data):
        if isinstance(data, bytes):
            text = data.decode("utf-8", "replace")
        else:
            text = data
        with self.lock:
            self.seq += 1
            seq, prev = self.seq, self.prev_hash
        payload = "%d|%s|%s|%s" % (seq, direction, prev, text)
        digest = chain_hash(prev, payload)
        with self.lock:
            self.prev_hash = digest
        line = json.dumps({"seq": seq, "ts": time.time(), "dir": direction,
                           "data": text, "prev": prev, "hash": digest})
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def write(self, data):
        if not self.alive:
            return False
        try:
            self.proc.stdin.write(data.encode("utf-8", "replace"))
            self.proc.stdin.flush()
        except Exception:
            try:
                self.proc.stdin.write(data.encode("utf-8", "replace") + b"\n")
                self.proc.stdin.flush()
            except Exception:
                return False
        with self.lock:
            self.last_active = time.time()
        self._log("in", data)
        return True

    def read(self, cursor):
        with self.lock:
            data = bytes(self.buf[cursor:])
            self.last_active = time.time()
            return len(self.buf), data.decode("utf-8", "replace")

    def close(self):
        self.alive = False
        try:
            self.proc.terminate()
        except Exception:
            pass


sessions = {}
sessions_lock = threading.Lock()


def new_session():
    with sessions_lock:
        if len(sessions) >= MAX_SESSIONS:
            return None
        sid = secrets.token_hex(8)
        sessions[sid] = TermSession(sid)
        return sid


def get_session(sid):
    with sessions_lock:
        return sessions.get(sid)


def drop_session(sid):
    with sessions_lock:
        s = sessions.pop(sid, None)
    if s:
        s.close()


def reap_idle():
    while True:
        time.sleep(60)
        now = time.time()
        with sessions_lock:
            stale = [sid for sid, s in sessions.items()
                     if now - s.last_active > IDLE_TIMEOUT or not s.alive and now - s.last_active > 300]
        for sid in stale:
            drop_session(sid)


class Handler(BaseHTTPRequestHandler):
    server_version = "SovereignTerminal/1.0"

    def log_message(self, fmt, *args):
        pass

    # -- helpers ------------------------------------------------------
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        given = self.headers.get("X-Term-Key", "")
        return bool(given) and hmac.compare_digest(given, KEY)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return None
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    # -- routes --------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        p = parsed.path
        if p == "/" or p == "/index.html":
            fp = os.path.join(STATIC, "terminal.html")
            if os.path.isfile(fp):
                with open(fp, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()
            return
        if not self._authed():
            self._json({"ok": False, "error": "bad key"}, 403)
            return
        if p == "/api/scripts":
            files = sorted(f for f in os.listdir(SCRIPTS)
                           if f.endswith(".ps1") and os.path.isfile(os.path.join(SCRIPTS, f)))
            self._json({"ok": True, "scripts": files})
            return
        m = re.match(r"^/api/session/([0-9a-f]+)/output$", p)
        if m:
            s = get_session(m.group(1))
            if not s:
                self._json({"ok": False, "error": "no session"}, 404)
                return
            try:
                cursor = int(parse_qs(parsed.query).get("cursor", ["0"])[0])
            except ValueError:
                cursor = 0
            new_cursor, data = s.read(max(0, cursor))
            self._json({"ok": True, "cursor": new_cursor, "data": data})
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        p = parsed.path
        if not self._authed():
            self._json({"ok": False, "error": "bad key"}, 403)
            return
        if p == "/api/session":
            sid = new_session()
            if not sid:
                self._json({"ok": False, "error": "too many sessions"}, 503)
                return
            self._json({"ok": True, "id": sid})
            return
        m = re.match(r"^/api/session/([0-9a-f]+)/input$", p)
        if m:
            s = get_session(m.group(1))
            if not s:
                self._json({"ok": False, "error": "no session"}, 404)
                return
            args = self._body()
            if not args or "data" not in args:
                self._json({"ok": False, "error": "need data"}, 400)
                return
            ok = s.write(str(args["data"]))
            self._json({"ok": ok})
            return
        m = re.match(r"^/api/session/([0-9a-f]+)/run$", p)
        if m:
            s = get_session(m.group(1))
            if not s:
                self._json({"ok": False, "error": "no session"}, 404)
                return
            args = self._body()
            name = str((args or {}).get("script", ""))
            # Contain the name: must be a plain .ps1 file in scripts/.
            if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.ps1$", name):
                self._json({"ok": False, "error": "bad script name"}, 400)
                return
            fp = os.path.join(SCRIPTS, name)
            if not os.path.isfile(fp):
                self._json({"ok": False, "error": "unknown script"}, 404)
                return
            s.write('powershell -ExecutionPolicy Bypass -File "%s"\n' % fp)
            self._json({"ok": True, "script": name})
            return
        self.send_response(404)
        self.end_headers()

    def do_DELETE(self):
        if not self._authed():
            self._json({"ok": False, "error": "bad key"}, 403)
            return
        m = re.match(r"^/api/session/([0-9a-f]+)$", urlparse(self.path).path)
        if m:
            drop_session(m.group(1))
            self._json({"ok": True})
            return
        self.send_response(404)
        self.end_headers()


def main():
    threading.Thread(target=reap_idle, daemon=True).start()
    lan_ip = "?"
    try:
        import socket
        lan_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        pass
    print("[sovereign-terminal] key: %s" % KEY)
    print("[sovereign-terminal] listening on %s:%d" % (BIND, PORT))
    print("[sovereign-terminal] local:  http://127.0.0.1:%d/" % PORT)
    print("[sovereign-terminal] lan:    http://%s:%d/  (phone -> this URL)" % (lan_ip, PORT))
    print("[sovereign-terminal] scripts: %s" % SCRIPTS)
    HTTPServer((BIND, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
