"""Field worker: truthful aggregate status of the Unified Field.

Read-only. Probes each field service on loopback and reports what
actually answered. A service that does not answer is reported down —
never smoothed over. Grown 2026-10-21 under the grow-test-release
protocol; passed isolated-kernel trials before registration.
"""
import json
import os
import urllib.request

CAPABILITIES = ["field.status"]
# Liveness is a measurement of right now; a cached answer reports the
# past as the present. Never serve this capability from the result cache.
STATEFUL_CAPABILITIES = ["field.status"]

_HERE = os.path.dirname(os.path.abspath(__file__))
_BRAIN_DIR = os.path.dirname(_HERE)

SERVICES = [
    ("brain", "http://127.0.0.1:18081/status", True),
    ("node", "http://127.0.0.1:18090/node-health", False),
    ("mesh", "http://127.0.0.1:18091/mesh-health", False),
    ("orchestrator", "http://127.0.0.1:18082/status", False),
    ("gateway", "http://127.0.0.1:18080/ping", False),
]


def _brain_key():
    try:
        with open(os.path.join(_BRAIN_DIR, "brain.key")) as f:
            return f.read().strip()
    except OSError:
        return ""


def _probe(url, use_key, timeout=3):
    req = urllib.request.Request(url)
    if use_key:
        key = _brain_key()
        if key:
            req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        return {"alive": bool(data.get("ok", True)), "detail": "ok"}
    except urllib.error.HTTPError as e:
        # A 401 still proves the service is up and gating correctly.
        if e.code == 401:
            return {"alive": True, "detail": "responding, key required"}
        return {"alive": False, "detail": "http %s" % e.code}
    except Exception as e:  # noqa: BLE001 - a dead service is data
        return {"alive": False, "detail": "%s: %s" % (type(e).__name__, e)}


def run(task, signal):
    services = {}
    for name, url, use_key in SERVICES:
        if signal is not None and signal.is_set():
            return {"ok": False, "error": "aborted"}
        services[name] = _probe(url, use_key)
    down = [n for n, s in services.items() if not s["alive"]]
    return {
        "ok": not down,
        "services": services,
        "alive_count": len(services) - len(down),
        "down": down,
    }
