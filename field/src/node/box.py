#!/usr/bin/env python3
"""
Box — our own Catbox. One file, stdlib only, no accounts, no telemetry.

A "box" is a tiny file host that runs on YOUR hardware. Files are stored
by their SHA-256 hash — the URL IS the verification. Any box can serve
any file; run several and they form a pack.

The pack (each instance takes a name):
    dogbox      — the first, the fetcher. Fast, loyal, temporary files.
    goatbox     — stubborn. Permanent storage, never expires.
    monkeybox   — playful. Thumbnails, previews, small media.
    penguinbox  — formal. Release artifacts, signed manifests.

Usage:
    python box.py                      # DogBox on :18083, data in ./box-data
    BOX_NAME=goatbox PORT=18084 python box.py

Endpoints:
    GET  /            tiny upload form (browser)
    GET  /health      {"ok": true, "box": "<name>", "files": N}
    POST /upload      multipart file=... + header X-Box-Key -> {"url","sha256","size"}
    GET  /f/<sha256>  serve file (unlisted URL, like Catbox)

The upload key prints on first run and is saved to box-data/.key.
Files are public to anyone with the URL — same model as Catbox.
Binds 127.0.0.1 by default; set BIND=0.0.0.0 for LAN/Tailscale.
"""

import hashlib
import json
import os
import secrets
import shutil
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

BOX_NAME = os.environ.get("BOX_NAME", "dogbox")
PORT = int(os.environ.get("PORT", "18083"))
BIND = os.environ.get("BIND", "127.0.0.1")
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.getcwd(), "box-data"))
MAX_SIZE = int(os.environ.get("MAX_SIZE", str(100 * 1024 * 1024)))


def box_key():
    keyfile = os.path.join(DATA_DIR, ".key")
    if os.path.exists(keyfile):
        with open(keyfile) as f:
            return f.read().strip()
    key = secrets.token_hex(16)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(keyfile, "w") as f:
        f.write(key)
    return key


KEY = box_key()
FILES = os.path.join(DATA_DIR, "files")
UPLOADS = os.path.join(DATA_DIR, "uploads")
os.makedirs(FILES, exist_ok=True)
os.makedirs(UPLOADS, exist_ok=True)


def file_count():
    try:
        return len(os.listdir(FILES))
    except OSError:
        return 0


class Handler(BaseHTTPRequestHandler):
    server_version = "Box/1.0"

    def log_message(self, *a):
        sys.stderr.write("[%s] %s\n" % (BOX_NAME, " ".join(str(x) for x in a)))

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json({"ok": True, "box": BOX_NAME, "files": file_count()})
            return
        if parsed.path == "/":
            html = ("<html><body><h1>%s</h1>"
                    "<form method=post action=/upload enctype=multipart/form-data>"
                    "key: <input name=key><br>file: <input type=file name=file><br>"
                    "<input type=submit></form></body></html>") % BOX_NAME
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path.startswith("/f/"):
            sha = parsed.path[3:].split("/")[0].split("?")[0]
            if len(sha) == 64 and all(c in "0123456789abcdef" for c in sha):
                path = os.path.join(FILES, sha)
                if os.path.isfile(path):
                    size = os.path.getsize(path)
                    # Range support: resume interrupted downloads.
                    rh = self.headers.get("Range", "")
                    start, end = 0, size - 1
                    partial = False
                    if rh.startswith("bytes="):
                        try:
                            spec = rh[6:].split(",")[0].strip()
                            a, b = spec.split("-")
                            start = int(a) if a else 0
                            end = int(b) if b else size - 1
                            end = min(end, size - 1)
                            if 0 <= start <= end:
                                partial = True
                        except ValueError:
                            pass
                    length = end - start + 1
                    self.send_response(206 if partial else 200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(length))
                    self.send_header("Accept-Ranges", "bytes")
                    if partial:
                        self.send_header("Content-Range",
                                         "bytes %d-%d/%d" % (start, end, size))
                    self.end_headers()
                    with open(path, "rb") as f:
                        f.seek(start)
                        remaining = length
                        while remaining > 0:
                            chunk = f.read(min(65536, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                    return
            self.send_response(404)
            self.end_headers()
            return

    def _chunked(self, p, raw):
        """Resumable chunked upload: init -> chunks -> done. JSON + X-Box-Key."""
        import base64
        key_given = self.headers.get("X-Box-Key", "")
        if key_given != KEY:
            self._json({"ok": False, "error": "bad key"}, 403)
            return
        if p == "/upload-init":
            uid = secrets.token_hex(8)
            open(os.path.join(UPLOADS, uid + ".part"), "wb").close()
            self._json({"ok": True, "upload_id": uid})
            return
        if p == "/upload-chunk":
            try:
                args = json.loads(raw.decode("utf-8"))
                uid = str(args["id"])
                offset = int(args["offset"])
                chunk = base64.b64decode(args["data"])
            except Exception:
                self._json({"ok": False, "error": "bad chunk"}, 400)
                return
            if len(chunk) > MAX_SIZE:
                self._json({"ok": False, "error": "too large"}, 413)
                return
            # Contain the id: hex only, no path tricks.
            if not all(c in "0123456789abcdef" for c in uid):
                self._json({"ok": False, "error": "bad id"}, 400)
                return
            ppath = os.path.join(UPLOADS, uid + ".part")
            if not os.path.isfile(ppath):
                self._json({"ok": False, "error": "unknown upload"}, 404)
                return
            cur = os.path.getsize(ppath)
            if offset != cur:
                self._json({"ok": False, "error": "offset mismatch",
                            "expected": cur}, 400)
                return
            if cur + len(chunk) > MAX_SIZE:
                self._json({"ok": False, "error": "too large"}, 413)
                return
            with open(ppath, "ab") as f:
                f.write(chunk)
            self._json({"ok": True, "received": cur + len(chunk)})
            return
        if p == "/upload-done":
            try:
                uid = str(json.loads(raw.decode("utf-8"))["id"])
            except Exception:
                self._json({"ok": False, "error": "bad request"}, 400)
                return
            if not all(c in "0123456789abcdef" for c in uid):
                self._json({"ok": False, "error": "bad id"}, 400)
                return
            ppath = os.path.join(UPLOADS, uid + ".part")
            if not os.path.isfile(ppath):
                self._json({"ok": False, "error": "unknown upload"}, 404)
                return
            sha = hashlib.sha256()
            with open(ppath, "rb") as f:
                for blk in iter(lambda: f.read(65536), b""):
                    sha.update(blk)
            digest = sha.hexdigest()
            dest = os.path.join(FILES, digest)
            if os.path.exists(dest):
                os.remove(ppath)
            else:
                os.rename(ppath, dest)
            size = os.path.getsize(dest)
            host = self.headers.get("Host", "localhost:%d" % PORT)
            self._json({"ok": True, "box": BOX_NAME, "sha256": digest,
                        "size": size,
                        "url": "http://%s/f/%s" % (host, digest)})
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        p = urlparse(self.path).path
        if p not in ("/upload", "/upload-init", "/upload-chunk", "/upload-done"):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_SIZE + 65536:
            self._json({"ok": False, "error": "bad size"}, 400)
            return
        raw = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "")

        # Chunked resumable upload: JSON protocol, key via header.
        if p in ("/upload-init", "/upload-chunk", "/upload-done"):
            self._chunked(p, raw)
            return

        # Single-shot multipart upload below.
        if "multipart/form-data" not in ctype:
            self._json({"ok": False, "error": "multipart required"}, 400)
            return
        try:
            boundary = ctype.split("boundary=")[1].split(";")[0].strip().strip('"')
        except IndexError:
            self._json({"ok": False, "error": "no boundary"}, 400)
            return
        # Minimal multipart parse: find file= part and optional key field.
        parts = raw.split(("--" + boundary).encode())
        file_bytes = None
        key_given = self.headers.get("X-Box-Key", "")
        for part in parts:
            if b'name="file"' in part or b"name='file'" in part:
                head, _, data = part.partition(b"\r\n\r\n")
                file_bytes = data.rstrip(b"\r\n").rstrip(b"--").rstrip(b"\r\n")
                # filename for the log only, never trusted for storage
            elif b'name="key"' in part:
                _, _, data = part.partition(b"\r\n\r\n")
                key_given = key_given or data.decode("utf-8", "ignore").strip().rstrip("-")
        if not key_given or key_given != KEY:
            self._json({"ok": False, "error": "bad key"}, 403)
            return
        if not file_bytes:
            self._json({"ok": False, "error": "no file"}, 400)
            return
        if len(file_bytes) > MAX_SIZE:
            self._json({"ok": False, "error": "too large"}, 413)
            return
        sha = hashlib.sha256(file_bytes).hexdigest()
        dest = os.path.join(FILES, sha)
        if not os.path.exists(dest):
            with open(dest, "wb") as f:
                f.write(file_bytes)
        host = self.headers.get("Host", "localhost:%d" % PORT)
        self._json({"ok": True, "box": BOX_NAME, "sha256": sha,
                    "size": len(file_bytes),
                    "url": "http://%s/f/%s" % (host, sha)})


def main():
    print("[%s] key: %s" % (BOX_NAME, KEY))
    print("[%s] data: %s" % (BOX_NAME, DATA_DIR))
    print("[%s] listening on %s:%d" % (BOX_NAME, BIND, PORT))
    HTTPServer((BIND, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
