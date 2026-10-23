#!/usr/bin/env python3
"""
Desktop Commander V1 — Zachary's combined desktop commander, remote
desktop, and browser agent, in one Python 3 standard-library program.

One authenticated HTTP service on loopback:

    GET  /status          host / OS / uptime / version / backends
    POST /exec            {command, timeout_s} -> {stdout, stderr, exit_code}
    POST /shot            -> screenshot PNG under shots/ (backend permitting)
    POST /type  {text}    -> keyboard input injection (backend permitting)
    POST /click {x, y}    -> mouse move + click (backend permitting)
    POST /browser/render  {url} -> rendered title + text (headless Chromium)

Security model (non-negotiable):
  * Binds 127.0.0.1 by default.
  * EVERY endpoint requires the X-Commander-Key header; the key lives in
    commander.key (mode 0600) in the data directory, is generated on
    first run and printed exactly once, and is never logged.
  * Key comparison is constant-time (hmac.compare_digest).
  * Every action is appended to a hash-chained ledger (ledger.jsonl).
    Each entry's prev_hash is the sha256 of the exact previous ledger
    line's text with NO trailing newline. `commander.py --verify`
    re-checks the chain.

Honest degradation: a missing backend (no screenshot tool, no xdotool,
no Chromium) yields a clear error naming what was looked for. Nothing
is faked, stubbed silently, or simulated.
"""

import argparse
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

VERSION = "1.0.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18077
MAX_BODY_BYTES = 1 * 1024 * 1024          # request body cap
MAX_OUTPUT_BYTES = 64 * 1024              # per-stream exec output cap
DEFAULT_EXEC_TIMEOUT_S = 30
MAX_EXEC_TIMEOUT_S = 300
RENDER_TEXT_CAP = 32 * 1024
# Genesis link: sha256 of the empty string, the chain's agreed zero point.
GENESIS_HASH = hashlib.sha256(b"").hexdigest()

STARTED_AT = time.time()

# ---------------------------------------------------------------- backends

SCREENSHOT_TOOLS = [
    # (name, argv builder) — first one found on PATH wins.
    ("grim", lambda p: ["grim", p]),
    ("scrot", lambda p: ["scrot", p]),
    ("maim", lambda p: ["maim", p]),
    ("gnome-screenshot", lambda p: ["gnome-screenshot", "-f", p]),
    ("import", lambda p: ["import", "-window", "root", p]),
]
SCREENSHOT_TOOL_NAMES = [name for name, _ in SCREENSHOT_TOOLS]
CHROMIUM_NAMES = ["chromium", "chromium-browser", "google-chrome",
                  "google-chrome-stable"]


def find_screenshot_tool():
    for name, build in SCREENSHOT_TOOLS:
        path = shutil.which(name)
        if path:
            return name, path, build
    return None, None, None


def find_input_tool():
    return shutil.which("xdotool")


def find_chromium():
    for name in CHROMIUM_NAMES:
        path = shutil.which(name)
        if path:
            return path
    return None


def backends():
    sname, _, _ = find_screenshot_tool()
    return {
        "screenshot": sname,                       # tool name or None
        "input": "xdotool" if find_input_tool() else None,
        "chromium": find_chromium(),               # path or None
    }


# ---------------------------------------------------------------- ledger

class Ledger:
    """Append-only, hash-chained JSONL ledger.

    Line format (canonical): json.dumps(entry, sort_keys=True,
    separators=(",", ":")) and entry["prev_hash"] is the hex sha256 of
    the previous line's exact bytes (no trailing newline). The first
    entry links to GENESIS_HASH.
    """

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.seq = 0
        self.last_hash = GENESIS_HASH
        if os.path.exists(path):
            with open(path, "rb") as f:
                for raw in f:
                    line = raw.rstrip(b"\n")
                    if not line:
                        continue
                    self.seq += 1
                    self.last_hash = hashlib.sha256(line).hexdigest()

    def append(self, action, detail):
        with self.lock:
            self.seq += 1
            entry = {
                "seq": self.seq,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "action": action,
                "detail": detail,
                "prev_hash": self.last_hash,
            }
            line = json.dumps(entry, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
            with open(self.path, "ab") as f:
                f.write(line + b"\n")
            self.last_hash = hashlib.sha256(line).hexdigest()
            return self.seq


def verify_ledger(path):
    """Return (ok, entries, first_bad_seq_or_None)."""
    if not os.path.exists(path):
        return True, 0, None
    prev = GENESIS_HASH
    seq = 0
    with open(path, "rb") as f:
        for raw in f:
            line = raw.rstrip(b"\n")
            if not line:
                continue
            seq += 1
            try:
                entry = json.loads(line.decode("utf-8"))
            except Exception:
                return False, seq, seq
            if entry.get("seq") != seq or entry.get("prev_hash") != prev:
                return False, seq, seq
            prev = hashlib.sha256(line).hexdigest()
    return True, seq, None


# ---------------------------------------------------------------- key file

def load_or_create_key(data_dir):
    """Return (key, created). The key is printed by the caller only when
    it was just created — exactly once, ever."""
    key_path = os.path.join(data_dir, "commander.key")
    if os.path.exists(key_path):
        with open(key_path, "r", encoding="utf-8") as f:
            return f.read().strip(), False
    key = secrets.token_hex(32)
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, (key + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass  # POSIX mode bits; Windows is handled just below
    if os.name == "nt":
        # Windows has no mode bits: enforce the same owner-only privacy
        # with the NTFS ACL - strip inheritance, grant only the current
        # user (and SYSTEM). Fail closed: if the ACL cannot be set,
        # delete the key and refuse to run with a broadly readable one.
        import getpass
        user = getpass.getuser()
        domain = os.environ.get("USERDOMAIN")
        principal = "%s\\%s" % (domain, user) if domain else user
        try:
            res = subprocess.run(
                ["icacls", key_path, "/inheritance:r",
                 "/grant:r", principal + ":F", "SYSTEM:F"],
                capture_output=True, text=True, timeout=15)
            if res.returncode != 0:
                raise OSError("icacls: %s" % (res.stderr or res.stdout))
        except Exception:
            try:
                os.unlink(key_path)
            except OSError:
                pass
            raise
    return key, True


# ---------------------------------------------------------------- helpers

def cap_bytes(data, cap):
    if len(data) <= cap:
        return data, False
    return data[:cap], True


def render_text_and_title(dom):
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", dom, re.I | re.S)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
    body = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", dom)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    body = (body.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&#39;", "'"))
    text = re.sub(r"\s+", " ", body).strip()
    return title, text


# ---------------------------------------------------------------- handler

class State:
    def __init__(self, key, ledger, data_dir):
        self.key = key
        self.ledger = ledger
        self.data_dir = data_dir
        self.shots_dir = os.path.join(data_dir, "shots")
        os.makedirs(self.shots_dir, exist_ok=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "DesktopCommander/" + VERSION
    state = None  # set by main()

    # -- plumbing ------------------------------------------------------
    def log_message(self, fmt, *args):  # keep stdout clean of the key
        sys.stderr.write("[dc] %s %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        supplied = self.headers.get("X-Commander-Key") or ""
        return hmac.compare_digest(supplied, self.state.key)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            return None
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        return obj if isinstance(obj, dict) else None

    def _route(self, method):
        if not self._authorized():
            self._send_json(401, {"ok": False, "error": "unauthorized: "
                                  "missing or wrong X-Commander-Key"})
            return
        path = urlparse(self.path).path
        try:
            if method == "GET" and path == "/status":
                self.handle_status()
            elif method == "POST" and path == "/exec":
                self.handle_exec()
            elif method == "POST" and path == "/shot":
                self.handle_shot()
            elif method == "POST" and path == "/type":
                self.handle_type()
            elif method == "POST" and path == "/click":
                self.handle_click()
            elif method == "POST" and path == "/browser/render":
                self.handle_render()
            else:
                self._send_json(404, {"ok": False,
                                      "error": "no such endpoint: " + path})
        except BrokenPipeError:
            pass
        except Exception as exc:  # never leak a stack to the client
            self._send_json(500, {"ok": False,
                                  "error": "internal error: %s" % exc})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    # -- endpoints -----------------------------------------------------
    def handle_status(self):
        self._send_json(200, {
            "ok": True,
            "name": "desktop-commander",
            "version": VERSION,
            "hostname": socket.gethostname(),
            "os": platform.platform(),
            "system": platform.system(),
            "python": platform.python_version(),
            "uptime_s": round(time.time() - STARTED_AT, 1),
            "backends": backends(),
            "ledger_entries": self.state.ledger.seq,
        })

    def handle_exec(self):
        body = self._read_body()
        if body is None:
            self._send_json(400, {"ok": False, "error": "invalid JSON body"})
            return
        command = body.get("command")
        if not isinstance(command, str) or not command:
            self._send_json(400, {"ok": False,
                                  "error": "field 'command' (string) required"})
            return
        timeout = body.get("timeout_s", DEFAULT_EXEC_TIMEOUT_S)
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            self._send_json(400, {"ok": False,
                                  "error": "'timeout_s' must be a number"})
            return
        timeout = max(1.0, min(timeout, float(MAX_EXEC_TIMEOUT_S)))
        timed_out = False
        try:
            proc = subprocess.run(command, shell=True, capture_output=True,
                                  timeout=timeout)
            out, err, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            out, err, code = exc.stdout or b"", exc.stderr or b"", None
        out, out_trunc = cap_bytes(out, MAX_OUTPUT_BYTES)
        err, err_trunc = cap_bytes(err, MAX_OUTPUT_BYTES)
        self.state.ledger.append("exec", {
            "command": command[:512],
            "exit_code": code,
            "timed_out": timed_out,
        })
        self._send_json(200, {
            "ok": True,
            "stdout": out.decode("utf-8", "replace"),
            "stderr": err.decode("utf-8", "replace"),
            "exit_code": code,
            "timed_out": timed_out,
            "stdout_truncated": out_trunc,
            "stderr_truncated": err_trunc,
        })

    def handle_shot(self):
        name, path_bin, build = find_screenshot_tool()
        if not name:
            self.state.ledger.append("shot", {"ok": False,
                                              "reason": "no_backend"})
            self._send_json(501, {
                "ok": False,
                "error": "no screenshot backend on this host; looked for: "
                         + ", ".join(SCREENSHOT_TOOL_NAMES)
                         + " (none on PATH; DISPLAY=%s)"
                         % os.environ.get("DISPLAY", "unset"),
            })
            return
        stamp = time.strftime("%Y%m%d-%H%M%S") + "-%03d" % int(
            (time.time() % 1) * 1000)
        out_path = os.path.join(self.state.shots_dir, "shot-%s.png" % stamp)
        try:
            proc = subprocess.run(build(out_path), capture_output=True,
                                  timeout=20)
        except subprocess.TimeoutExpired:
            self._send_json(502, {"ok": False,
                                  "error": "screenshot tool %s timed out" % name})
            return
        if proc.returncode != 0 or not os.path.exists(out_path) \
                or os.path.getsize(out_path) == 0:
            detail = proc.stderr.decode("utf-8", "replace")[:300]
            self.state.ledger.append("shot", {"ok": False, "tool": name,
                                              "reason": "tool_failed"})
            self._send_json(502, {
                "ok": False,
                "error": "screenshot tool %s failed (exit %s): %s"
                         % (name, proc.returncode, detail),
            })
            return
        size = os.path.getsize(out_path)
        self.state.ledger.append("shot", {"ok": True, "tool": name,
                                          "path": out_path, "bytes": size})
        self._send_json(200, {"ok": True, "path": out_path, "bytes": size,
                              "tool": name})

    def handle_type(self):
        body = self._read_body()
        if body is None or not isinstance(body.get("text"), str):
            self._send_json(400, {"ok": False,
                                  "error": "field 'text' (string) required"})
            return
        text = body["text"]
        tool = find_input_tool()
        if not tool:
            self.state.ledger.append("type", {"ok": False,
                                              "reason": "no_backend"})
            self._send_json(501, {
                "ok": False,
                "error": "no input backend on this host; keyboard injection "
                         "needs xdotool on PATH (none found; DISPLAY=%s)"
                         % os.environ.get("DISPLAY", "unset"),
            })
            return
        proc = subprocess.run([tool, "type", "--", text],
                              capture_output=True, timeout=20)
        ok = proc.returncode == 0
        # Ledger records the act, not the typed content (may be sensitive).
        self.state.ledger.append("type", {
            "ok": ok,
            "chars": len(text),
            "text_sha256_16": hashlib.sha256(
                text.encode("utf-8")).hexdigest()[:16],
        })
        if not ok:
            self._send_json(502, {"ok": False,
                                  "error": "xdotool failed: " + proc.stderr
                                  .decode("utf-8", "replace")[:300]})
            return
        self._send_json(200, {"ok": True, "chars": len(text)})

    def handle_click(self):
        body = self._read_body()
        x, y = (body or {}).get("x"), (body or {}).get("y")
        if not isinstance(x, int) or not isinstance(y, int) or x < 0 or y < 0:
            self._send_json(400, {"ok": False,
                                  "error": "fields 'x' and 'y' (non-negative "
                                           "integers) required"})
            return
        tool = find_input_tool()
        if not tool:
            self.state.ledger.append("click", {"ok": False, "x": x, "y": y,
                                               "reason": "no_backend"})
            self._send_json(501, {
                "ok": False,
                "error": "no input backend on this host; mouse injection "
                         "needs xdotool on PATH (none found; DISPLAY=%s)"
                         % os.environ.get("DISPLAY", "unset"),
            })
            return
        proc = subprocess.run([tool, "mousemove", str(x), str(y),
                               "click", "1"], capture_output=True, timeout=20)
        ok = proc.returncode == 0
        self.state.ledger.append("click", {"ok": ok, "x": x, "y": y})
        if not ok:
            self._send_json(502, {"ok": False,
                                  "error": "xdotool failed: " + proc.stderr
                                  .decode("utf-8", "replace")[:300]})
            return
        self._send_json(200, {"ok": True, "x": x, "y": y})

    def handle_render(self):
        body = self._read_body()
        url = (body or {}).get("url")
        if not isinstance(url, str) or \
                urlparse(url).scheme not in ("http", "https"):
            self._send_json(400, {"ok": False,
                                  "error": "field 'url' must be an http(s) URL"})
            return
        chrome = find_chromium()
        if not chrome:
            self.state.ledger.append("browser_render", {
                "ok": False, "url": url[:512], "reason": "no_backend"})
            self._send_json(501, {
                "ok": False,
                "error": "no Chromium on this host; looked for: "
                         + ", ".join(CHROMIUM_NAMES) + " (none on PATH)",
            })
            return
        try:
            proc = subprocess.run(
                [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                 "--dump-dom", "--virtual-time-budget=10000", url],
                capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            self.state.ledger.append("browser_render", {
                "ok": False, "url": url[:512], "reason": "timeout"})
            self._send_json(502, {"ok": False,
                                  "error": "headless Chromium timed out"})
            return
        if proc.returncode != 0:
            self.state.ledger.append("browser_render", {
                "ok": False, "url": url[:512], "reason": "chrome_failed"})
            self._send_json(502, {
                "ok": False,
                "error": "headless Chromium failed (exit %s): %s"
                         % (proc.returncode,
                            proc.stderr.decode("utf-8", "replace")[:300]),
            })
            return
        dom = proc.stdout.decode("utf-8", "replace")
        title, text = render_text_and_title(dom)
        truncated = len(text) > RENDER_TEXT_CAP
        text = text[:RENDER_TEXT_CAP]
        self.state.ledger.append("browser_render", {
            "ok": True, "url": url[:512], "title": title[:200]})
        self._send_json(200, {
            "ok": True, "url": url, "title": title, "text": text,
            "text_truncated": truncated,
            "limits": "headless render of initial DOM only: no session, "
                      "no cookies, no clicking or form-filling",
        })


# ---------------------------------------------------------------- config

def load_config(data_dir):
    cfg = {"host": DEFAULT_HOST, "port": DEFAULT_PORT}
    cfg_path = os.path.join(data_dir, "commander.json")
    # Also accept a config beside this script when data dir is default.
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            for k in ("host", "port"):
                if k in loaded:
                    cfg[k] = loaded[k]
        except Exception as exc:
            print("warning: ignoring bad commander.json: %s" % exc,
                  file=sys.stderr)
    return cfg


def main(argv=None):
    parser = argparse.ArgumentParser(description="Desktop Commander V1")
    parser.add_argument("--data-dir", default=os.path.dirname(
        os.path.abspath(__file__)),
        help="directory for commander.key, commander.json, ledger.jsonl, "
             "shots/ (default: this script's directory)")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None,
                        help="0 picks an ephemeral port")
    parser.add_argument("--verify", action="store_true",
                        help="verify ledger.jsonl and exit")
    args = parser.parse_args(argv)

    data_dir = os.path.abspath(args.data_dir)
    os.makedirs(data_dir, exist_ok=True)

    if args.verify:
        ok, count, bad = verify_ledger(os.path.join(data_dir, "ledger.jsonl"))
        if ok:
            print("ledger OK: %d entries, chain intact" % count)
            return 0
        print("ledger BROKEN at entry %s (of %d seen)" % (bad, count))
        return 1

    cfg = load_config(data_dir)
    host = args.host or cfg["host"]
    port = args.port if args.port is not None else int(cfg["port"])

    key, created = load_or_create_key(data_dir)
    if created:
        # Printed exactly once: the first run that creates the key.
        print("COMMANDER KEY (shown once — save it now): %s" % key)
        sys.stdout.flush()

    ledger = Ledger(os.path.join(data_dir, "ledger.jsonl"))
    Handler.state = State(key, ledger, data_dir)
    server = ThreadingHTTPServer((host, port), Handler)
    bound_host, bound_port = server.server_address[:2]
    print("LISTENING http://%s:%d" % (bound_host, bound_port))
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
