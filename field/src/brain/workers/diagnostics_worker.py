"""Diagnostics worker: read-only self checks."""
import os
import shutil
import socket
import urllib.request

CAPABILITIES = ["diag.check"]


def _tcp_open(host, port, timeout=2):
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except OSError:
        return False


def _ollama_models(timeout=4):
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags",
                                    timeout=timeout) as r:
            data = r.read().decode("utf-8", "replace")
        import json
        models = [m.get("name") for m in json.loads(data).get("models", [])]
        return {"reachable": True, "models": models}
    except Exception as e:  # noqa: BLE001
        return {"reachable": False, "error": "%s: %s" % (type(e).__name__, e)}


def run(task, signal):
    from kernel import EventLog, AUDIT_LOG  # local import: no cycle
    model_want = os.environ.get("SIXTEEN_MODEL", "qwen2.5:7b")
    oll = _ollama_models()
    disk = shutil.disk_usage(os.path.dirname(os.path.abspath(__file__)))
    chain = EventLog(AUDIT_LOG).verify()
    return {
        "ok": True,
        "disk_free_gb": round(disk.free / (1024 ** 3), 2),
        "ollama": oll,
        "model_wanted": model_want,
        "model_present": model_want in oll.get("models", []),
        "port_18081": _tcp_open("127.0.0.1", 18081),
        "port_3000": _tcp_open("127.0.0.1", 3000),
        "audit_chain": chain,
    }
