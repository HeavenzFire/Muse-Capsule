"""FS worker: file operations rooted at allowed directories.

- No dotfile/dotdir access, ever.
- Writes outside the roots, and all deletes, are destructive: they require
  a recorded approval (see kernel approvals / POST /approve).
"""
import os
import shutil

CAPABILITIES = ["fs.read", "fs.write", "fs.list", "fs.mkdir", "fs.delete"]

DEFAULT_ROOTS = []


def _roots():
    roots = list(DEFAULT_ROOTS)
    roots.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    if os.path.isdir(docs):
        roots.append(os.path.abspath(docs))
    return roots


def _safe(path):
    ap = os.path.abspath(path)
    for part in ap.split(os.sep):
        if part.startswith(".") and part not in (".", ".."):
            return None, "dotfile/dotdir access refused"
    for r in _roots():
        if ap == r or ap.startswith(r + os.sep):
            return ap, None
    return None, "path outside allowed roots"


def _needs_approval(op, ap):
    if op == "fs.delete":
        return True
    if op == "fs.write":
        # writes inside roots are fine; anything else was already refused
        return False
    return False


def _approved(task):
    # approval record lives in kernel approvals file; task carries its id
    from kernel import is_approved, make_task_id  # local import: no cycle
    tid = task.get("approval_id") or make_task_id(
        {"capability": task.get("capability"), "args": task.get("args", {})})
    return is_approved(tid)


def run(task, signal):
    args = task.get("args", {})
    op = task.get("capability")
    ap, err = _safe(args.get("path", ""))
    if err:
        return {"ok": False, "error": err}
    if _needs_approval(op, ap) and not _approved(task):
        return {"ok": False, "error": "destructive op needs approval",
                "approval_required": True, "path": ap}
    try:
        if op == "fs.read":
            with open(ap, "r", encoding="utf-8", errors="replace") as f:
                data = f.read(65536)
            return {"ok": True, "path": ap, "content": data}
        if op == "fs.write":
            os.makedirs(os.path.dirname(ap), exist_ok=True)
            with open(ap, "w", encoding="utf-8") as f:
                f.write(args.get("content", ""))
            return {"ok": True, "path": ap,
                    "bytes": len(args.get("content", ""))}
        if op == "fs.list":
            names = sorted(os.listdir(ap))
            return {"ok": True, "path": ap, "names": names[:500]}
        if op == "fs.mkdir":
            os.makedirs(ap, exist_ok=True)
            return {"ok": True, "path": ap}
        if op == "fs.delete":
            if os.path.isdir(ap) and not os.path.islink(ap):
                shutil.rmtree(ap)
            else:
                os.remove(ap)
            return {"ok": True, "deleted": ap}
    except FileNotFoundError:
        return {"ok": False, "error": "not found: %s" % ap}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    return {"ok": False, "error": "unknown op"}
