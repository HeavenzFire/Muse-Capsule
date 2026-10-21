"""Notes worker: local markdown notes store."""
import os
import re

CAPABILITIES = ["notes.create", "notes.read", "notes.list", "notes.search"]

NOTES_DIR = os.path.join(os.path.dirname(__file__), "..", "notes")


def _safe_name(name):
    name = re.sub(r"[^A-Za-z0-9 _.-]", "", name).strip()
    if not name or name.startswith("."):
        return None
    if not name.endswith(".md"):
        name += ".md"
    return name


def run(task, signal):
    args = task.get("args", {})
    op = task.get("capability")
    os.makedirs(NOTES_DIR, exist_ok=True)
    if op == "notes.create":
        name = _safe_name(args.get("name", ""))
        if not name:
            return {"ok": False, "error": "bad note name"}
        p = os.path.join(NOTES_DIR, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(args.get("content", ""))
        return {"ok": True, "note": name}
    if op == "notes.read":
        name = _safe_name(args.get("name", ""))
        p = os.path.join(NOTES_DIR, name or "")
        if not name or not os.path.isfile(p):
            return {"ok": False, "error": "not found"}
        with open(p, encoding="utf-8") as f:
            return {"ok": True, "note": name, "content": f.read(65536)}
    if op == "notes.list":
        names = sorted(n for n in os.listdir(NOTES_DIR) if n.endswith(".md"))
        return {"ok": True, "notes": names}
    if op == "notes.search":
        q = args.get("query", "").lower()
        hits = []
        for n in os.listdir(NOTES_DIR):
            if not n.endswith(".md"):
                continue
            with open(os.path.join(NOTES_DIR, n), encoding="utf-8",
                      errors="replace") as f:
                content = f.read()
            if q in content.lower():
                idx = content.lower().index(q)
                hits.append({"note": n,
                             "snippet": content[max(0, idx - 80):idx + 120]})
        return {"ok": True, "hits": hits[:20]}
    return {"ok": False, "error": "unknown op"}
