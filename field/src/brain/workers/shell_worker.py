"""Shell worker: argv-only execution with an allowlist. No shell strings, ever."""
import os
import subprocess

CAPABILITIES = ["shell.run"]

ALLOWLIST = {"git", "gh", "python", "pip", "node", "npm", "npx", "ollama"}
MAX_OUTPUT = 65536


def run(task, signal):
    args = task.get("args", {})
    argv = args.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        return {"ok": False, "error": "argv must be a non-empty list of strings"}
    prog = os.path.basename(argv[0]).lower()
    if prog not in ALLOWLIST and argv[0] not in ALLOWLIST:
        return {"ok": False, "error": "command not allowlisted: %r" % argv[0]}
    timeout = min(int(args.get("timeout", 60)), 300)
    cwd = args.get("cwd") or None
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, cwd=cwd)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout after %ss" % timeout}
    except FileNotFoundError:
        return {"ok": False, "error": "executable not found: %r" % argv[0]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "exec failed: %s" % e}
    out = (p.stdout or "")[-MAX_OUTPUT:]
    err = (p.stderr or "")[-MAX_OUTPUT:]
    return {"ok": True, "returncode": p.returncode, "stdout": out, "stderr": err}
