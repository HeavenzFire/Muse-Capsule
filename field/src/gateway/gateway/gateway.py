"""Sovereign gateway: DECOUPLE from their web, RECONNECT on our terms.

One unified REST API fronting every subsystem. One auth. One audit log.
The gateway is the only surface the phone (or anything else) talks to;
the subsystems stay loopback-only behind it.

Subsystems (all 127.0.0.1, all loopback-only):
  /brain/*         -> 18081  PRIME brain (X-API-Key injected from brain.key)
  /orchestrator/*  -> 18082  swarm orchestrator
  /node/health     -> 18090  node supervisor health
  /node/mesh       -> 18091  mesh health
  /node/box/*      -> 18083  box file service
  /node/terminal/* -> 18088  terminal web UI
  /forge/*         -> translated to orchestrator forge.repo.* tasks
  /egress/*        -> the ONLY sanctioned path to the web (allow-listed)

Auth: X-Gateway-Key. Keys are minted on HIS machine (see keystore.py),
scoped per client: phone | laptop | witness. Laptop scope administers
keys. Revocation list enforced.

Bind: 127.0.0.1:18080 by default. Public bind is OPT-IN ONLY via
  SOVEREIGN_GATEWAY_PUBLIC=1  (plaintext; put TLS in front yourself)
and is refused unless the operator set it explicitly. Default off.

Every request and response is hash-chained into the audit log.
No silent calls: even /ping is logged (it just needs no key).

Stdlib only. Our own way.
"""
import http.client
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from gateway import keystore, allowlist  # noqa: E402
from gateway.audit import AuditLog  # noqa: E402
from gateway import egress  # noqa: E402

PORT = int(os.environ.get("SOVEREIGN_GATEWAY_PORT", "18080"))
PUBLIC = os.environ.get("SOVEREIGN_GATEWAY_PUBLIC", "") == "1"

# Subsystem endpoints. Overridable for tests via env.
BRAIN = ("127.0.0.1", int(os.environ.get("SOVEREIGN_BRAIN_PORT", "18081")))
ORCH = ("127.0.0.1", int(os.environ.get("SOVEREIGN_ORCH_PORT", "18082")))
NODE_HEALTH = ("127.0.0.1", 18090)
MESH_HEALTH = ("127.0.0.1", 18091)
BOX = ("127.0.0.1", 18083)
TERMINAL = ("127.0.0.1", 18088)

AUDIT = AuditLog()
STARTED = time.time()


def _brain_key():
    """The brain's own API key, read from its key file. The gateway holds
    it so the phone needs only ONE key (the gateway's)."""
    for cand in (os.environ.get("SOVEREIGN_BRAIN_KEY_FILE", ""),
                 r"C:\sixteen\brain\brain.key",
                 os.path.join(os.path.dirname(HERE), "..",
                              "prime-brain-build", "brain.key")):
        if cand and os.path.isfile(cand):
            with open(cand, "r", encoding="utf-8") as f:
                return f.read().strip()
    return ""


BRAIN_KEY = _brain_key()

HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate",
               "proxy-authorization", "te", "trailers", "transfer-encoding",
               "upgrade", "content-length"}


def _proxy(host, port, method, path, headers, body, extra_headers=None):
    """Reverse-proxy one request. Returns (status, resp_headers, resp_body)."""
    conn = http.client.HTTPConnection(host, port, timeout=30)
    out = {}
    for k, v in headers.items():
        kl = k.lower()
        if kl in HOP_HEADERS or kl == "x-gateway-key":
            continue
        out[k] = v
    out.update(extra_headers or {})
    if body:
        out["Content-Length"] = str(len(body))
    conn.request(method, path or "/", body=body, headers=out)
    r = conn.getresponse()
    data = r.read()
    rh = {k: v for k, v in r.getheaders()
          if k.lower() not in HOP_HEADERS}
    conn.close()
    return r.status, rh, data


class Handler(BaseHTTPRequestHandler):
    server_version = "SovereignGateway/1.0"

    # -- helpers -------------------------------------------------------
    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(n) if n else b""

    def _json(self, code, obj, audit_extra=None):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return body

    # -- CORS (P2: surfaces are browser clients) -------------------------
    # Surfaces (dashboard, IDE, voice, camera pages) run in browsers and
    # reach the field only through this gateway. CORS is not the
    # security boundary — the X-Gateway-Key is, and it is still required
    # on every real request. Only loopback origins and file:// pages
    # (Origin "null") are reflected; anything else gets no CORS header
    # and the browser blocks the read.
    def _cors_origin(self):
        origin = self.headers.get("Origin", "")
        if origin == "null":
            return "null"
        if origin.startswith("http://"):
            host = origin[len("http://"):].split("/", 1)[0]
            name, _, port = host.partition(":")
            if name in ("127.0.0.1", "localhost") and \
                    (not port or port.isdigit()):
                return origin
        return None

    def _cors_headers(self):
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _auth(self):
        raw = self.headers.get("X-Gateway-Key", "")
        return keystore.verify(raw)  # (key_id, scope) or (None, None)

    def _deny(self, req_body, reason):
        res = self._json(401, {"ok": False, "error": reason})
        AUDIT.append(self.command, self.path, 401, client="anon",
                     scope="-", req_body=req_body, res_body=res,
                     verdict="AUTH_DENIED")

    # -- routing --------------------------------------------------------
    def _route(self, body):
        p = self.path.split("?", 1)[0]
        if p == "/ping":
            return ("ping", None, None, None)
        kid, scope = self._auth()
        if not kid:
            return ("denied", None, None, None)
        if p == "/status" or p == "/":
            return ("status", kid, scope, None)
        if p == "/audit/verify":
            return ("audit_verify", kid, scope, None)
        if p.startswith("/keys/"):
            return ("keys", kid, scope, p[len("/keys/"):])
        if p.startswith("/brain/"):
            return ("proxy_brain", kid, scope, p[len("/brain"):])
        if p.startswith("/orchestrator/"):
            return ("proxy_orch", kid, scope, p[len("/orchestrator"):])
        if p.startswith("/node/"):
            return ("proxy_node", kid, scope, p[len("/node"):])
        if p.startswith("/forge/"):
            return ("forge", kid, scope, p[len("/forge"):])
        if p.startswith("/egress/"):
            return ("egress", kid, scope, p[len("/egress/"):])
        return ("notfound", kid, scope, None)

    def _handle(self, body):
        kind, kid, scope, rest = self._route(body)
        client = (kid or "anon")[:12]

        if kind == "denied":
            self._deny(body, "missing or bad X-Gateway-Key")
            return
        if kind == "ping":
            res = self._json(200, {"ok": True, "gateway": "sovereign",
                                   "ts": int(time.time())})
            AUDIT.append(self.command, self.path, 200, client="ping",
                         scope="-", req_body=body, res_body=res)
            return
        if kind == "status":
            v = AUDIT.verify()
            res = self._json(200, {
                "ok": True, "uptime_s": int(time.time() - STARTED),
                "subsystems": {"brain": "%s:%d" % BRAIN,
                               "orchestrator": "%s:%d" % ORCH,
                               "node_health": "%s:%d" % NODE_HEALTH,
                               "mesh_health": "%s:%d" % MESH_HEALTH,
                               "box": "%s:%d" % BOX,
                               "terminal": "%s:%d" % TERMINAL},
                "audit": {"ok": v["ok"], "entries": v["entries"],
                          "head": (v["head"] or "")[:16]},
                "client_scope": scope})
            AUDIT.append(self.command, self.path, 200, client=client,
                         scope=scope, req_body=body, res_body=res)
            return
        if kind == "audit_verify":
            v = AUDIT.verify()
            code = 200 if v["ok"] else 500
            res = self._json(code, {"ok": v["ok"], "entries": v["entries"],
                                    "head": v["head"],
                                    "break_at": v["break_at"]})
            AUDIT.append(self.command, self.path, code, client=client,
                         scope=scope, req_body=body, res_body=res)
            return
        if kind == "keys":
            self._keys(rest, body, kid, scope, client)
            return
        if kind == "proxy_brain":
            extra = {"X-API-Key": BRAIN_KEY} if BRAIN_KEY else {}
            self._proxied(BRAIN, rest, body, extra, kid, scope, client,
                          "proxy")
            return
        if kind == "proxy_orch":
            self._proxied(ORCH, rest, body, {}, kid, scope, client, "proxy")
            return
        if kind == "proxy_node":
            self._node(rest, body, kid, scope, client)
            return
        if kind == "forge":
            self._forge(rest, body, kid, scope, client)
            return
        if kind == "egress":
            self._egress(rest, body, kid, scope, client)
            return
        res = self._json(404, {"ok": False, "error": "unknown path"})
        AUDIT.append(self.command, self.path, 404, client=client,
                     scope=scope, req_body=body, res_body=res)

    # -- sub-handlers ----------------------------------------------------
    def _proxied(self, target, rest, body, extra, kid, scope, client,
                 verdict):
        try:
            st, rh, data = _proxy(target[0], target[1], self.command,
                                  rest or "/", dict(self.headers), body,
                                  extra)
        except Exception as e:  # noqa: BLE001
            res = self._json(502, {"ok": False, "error":
                                   "subsystem unreachable: %s:%d (%s)"
                                   % (target[0], target[1], e)})
            AUDIT.append(self.command, self.path, 502, client=client,
                         scope=scope, req_body=body, res_body=res,
                         verdict="SUBSYSTEM_DOWN")
            return
        self.send_response(st)
        for k, v in rh.items():
            self.send_header(k, v)
        self._cors_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        AUDIT.append(self.command, self.path, st, client=client,
                     scope=scope, req_body=body, res_body=data,
                     verdict=verdict)

    def _node(self, rest, body, kid, scope, client):
        r = rest.strip("/")
        if r == "health":
            self._proxied(NODE_HEALTH, "/node-health", body, {}, kid,
                          scope, client, "proxy")
        elif r == "mesh":
            self._proxied(MESH_HEALTH, "/mesh-health", body, {}, kid,
                          scope, client, "proxy")
        elif r == "box" or r.startswith("box/"):
            self._proxied(BOX, "/" + r[3:].lstrip("/"), body, {}, kid,
                          scope, client, "proxy")
        elif r == "terminal" or r.startswith("terminal/"):
            self._proxied(TERMINAL, "/" + r[8:].lstrip("/"), body, {},
                          kid, scope, client, "proxy")
        else:
            res = self._json(404, {"ok": False,
                                   "error": "node routes: health, mesh, "
                                            "box/*, terminal/*"})
            AUDIT.append(self.command, self.path, 404, client=client,
                         scope=scope, req_body=body, res_body=res)

    def _forge(self, rest, body, kid, scope, client):
        """Translate REST forge ops into orchestrator forge.repo.* tasks."""
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except ValueError:
            data = {}
        mapping = {
            "repo/sync": "forge.repo.sync",
            "repo/status": "forge.repo.status",
            "repo/check": "forge.repo.check",
            "issue/create": "forge.issue.create",
            "issue/list": "forge.issue.list",
        }
        cap = mapping.get(rest.strip("/"))
        if not cap:
            res = self._json(404, {"ok": False,
                                   "error": "forge routes: "
                                            + ", ".join(sorted(mapping))})
            AUDIT.append(self.command, self.path, 404, client=client,
                         scope=scope, req_body=body, res_body=res)
            return
        task = json.dumps({"task": {"capability": cap,
                                    "args": data}}).encode()
        self._proxied(ORCH, "/submit", task,
                      {"Content-Type": "application/json"}, kid, scope,
                      client, "forge:" + cap)

    def _egress(self, rest, body, kid, scope, client):
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except ValueError:
            data = {}
        cap = data.get("capability", "web.fetch")
        r = rest.strip("/")
        if r == "fetch":
            out = egress.fetch(data.get("url", ""), capability=cap)
            code = 200 if out.get("ok") else \
                (403 if out.get("verdict") == "DENIED" else 502)
            res = self._json(code, out)
            AUDIT.append(self.command, self.path, code, client=client,
                         scope=scope, req_body=body, res_body=res,
                         capability=cap, verdict="egress:" + out["verdict"])
        elif r == "search":
            out = egress.search(data.get("query", ""), capability=cap)
            code = 200 if out.get("ok") else \
                (403 if out.get("verdict") == "DENIED" else 502)
            res = self._json(code, out)
            AUDIT.append(self.command, self.path, code, client=client,
                         scope=scope, req_body=body, res_body=res,
                         capability=cap, verdict="egress:" + out["verdict"])
        elif r == "relay":
            st, rbody, verdict = egress.relay(
                data.get("host", ""), data.get("method", "GET"),
                data.get("path", "/"), data.get("query", ""),
                (data.get("body") or "").encode(),
                data.get("headers", {}), capability=cap)
            self.send_response(st)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.send_header("Content-Length", str(len(rbody)))
            self.end_headers()
            self.wfile.write(rbody)
            AUDIT.append(self.command, self.path, st, client=client,
                         scope=scope, req_body=body, res_body=rbody,
                         capability=cap, verdict="egress:" + verdict)
        else:
            res = self._json(404, {"ok": False,
                                   "error": "egress routes: fetch, "
                                            "search, relay"})
            AUDIT.append(self.command, self.path, 404, client=client,
                         scope=scope, req_body=body, res_body=res)

    def _keys(self, rest, body, kid, scope, client):
        if scope != "laptop":
            res = self._json(403, {"ok": False,
                                   "error": "key management needs the "
                                            "laptop key"})
            AUDIT.append(self.command, self.path, 403, client=client,
                         scope=scope, req_body=body, res_body=res,
                         verdict="KEY_ADMIN_DENIED")
            return
        r = rest.strip("/")
        if r == "list" and self.command == "GET":
            res = self._json(200, {"ok": True,
                                   "keys": keystore.list_keys()})
            AUDIT.append(self.command, self.path, 200, client=client,
                         scope=scope, req_body=body, res_body=res,
                         verdict="key_list")
        elif r == "mint" and self.command == "POST":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                data = {}
            try:
                new_id, raw = keystore.mint(data.get("scope", "phone"),
                                            data.get("label", ""))
            except ValueError as e:
                res = self._json(400, {"ok": False, "error": str(e)})
                AUDIT.append(self.command, self.path, 400, client=client,
                             scope=scope, req_body=body, res_body=res)
                return
            # The raw key is returned ONCE, in this response. The audit
            # log records only a marker: the key itself never touches
            # the log (audit stores body hashes, and we withhold this one).
            res = self._json(200, {"ok": True, "key_id": new_id,
                                   "key": raw,
                                   "warning": "copy now; never shown again"})
            AUDIT.append(self.command, self.path, 200, client=client,
                         scope=scope, req_body=b"",
                         res_body=b"<key material withheld>",
                         verdict="key_minted")
        elif r == "revoke" and self.command == "POST":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                data = {}
            ok = keystore.revoke(data.get("key_id", ""))
            res = self._json(200 if ok else 404,
                             {"ok": ok,
                              "revoked": data.get("key_id", "")})
            AUDIT.append(self.command, self.path, 200 if ok else 404,
                         client=client, scope=scope, req_body=body,
                         res_body=res, verdict="key_revoked")
        else:
            res = self._json(404, {"ok": False,
                                   "error": "keys routes: list (GET), "
                                            "mint (POST), revoke (POST)"})
            AUDIT.append(self.command, self.path, 404, client=client,
                         scope=scope, req_body=body, res_body=res)

    # -- HTTP verbs --------------------------------------------------------
    def do_OPTIONS(self):
        # Browser preflight. Carries no authority: no key is sent on a
        # preflight and none is honored; the real request still auths.
        self.send_response(204)
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods",
                             "GET, POST, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers",
                             "X-Gateway-Key, Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self._handle(self._body())

    def do_POST(self):
        self._handle(self._body())

    def do_PUT(self):
        self._handle(self._body())

    def do_DELETE(self):
        self._handle(self._body())

    def log_message(self, fmt, *args):
        sys.stderr.write("GATEWAY %s\n" % (fmt % args))


def main():
    if "--init" in sys.argv:
        minted = keystore.ensure_bootstrap()
        if not minted:
            print("keys already exist; nothing minted. "
                  "Use the laptop key: POST /keys/mint")
            return
        print("SOVEREIGN GATEWAY keys minted on THIS machine.")
        print("Copy each key NOW. They are never shown again.")
        print("The phone app needs the PHONE key as X-Gateway-Key.")
        for scope in ("phone", "laptop", "witness"):
            kid, raw = minted[scope]
            print("  %-8s id=%s key=%s" % (scope, kid, raw))
        return
    if "--verify-audit" in sys.argv:
        print(json.dumps(AuditLog().verify(), indent=2))
        return
    bind = "0.0.0.0" if PUBLIC else "127.0.0.1"
    if PUBLIC:
        print("WARNING: public bind explicitly enabled "
              "(SOVEREIGN_GATEWAY_PUBLIC=1). Put TLS in front.")
    else:
        print("loopback only: 127.0.0.1:%d  (public bind is opt-in)" % PORT)
    if not BRAIN_KEY:
        print("note: no brain.key found; /brain/* proxies without X-API-Key")
    srv = ThreadingHTTPServer((bind, PORT), Handler)
    print("sovereign gateway on %s:%d" % (bind, PORT))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
