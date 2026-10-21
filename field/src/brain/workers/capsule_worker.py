"""Capsule worker: loads CRAYDON-CAPSULE.json, verifies envelope.

Unsigned / missing capsule -> LIMITED mode. The worker states the mode on
every response; it never invents identity claims.
"""
import json
import os

CAPABILITIES = ["capsule.load", "capsule.section", "capsule.append"]

# load/section read state the system itself can change (capsule.append
# mutates the capsule), so a cached answer can report a capsule that no
# longer exists. They bypass the kernel result cache; append stays
# deduped — an identical re-submit is the same task, applied once.
STATEFUL_CAPABILITIES = ["capsule.load", "capsule.section"]

# The field instantiates its capsule in the field tree and points the
# brain at it with HF_CAPSULE_PATH; the default (capsule beside the
# brain) is unchanged for the desktop drop-in.
CAPSULE_PATH = os.environ.get("HF_CAPSULE_PATH") or os.path.join(
    os.path.dirname(__file__), "..", "CRAYDON-CAPSULE.json")

REQUIRED_TOP_KEYS = {"version", "identity", "user", "boundaries",
                     "standing_orders", "memory", "projects"}


def _load():
    if not os.path.isfile(CAPSULE_PATH):
        return None, "missing"
    try:
        with open(CAPSULE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        return None, "unreadable: %s" % e
    keys = set(data.keys())
    missing = REQUIRED_TOP_KEYS - keys
    sig = data.get("signature", {})
    signed = bool(sig.get("valid") is True)
    mode = "SIGNED" if (signed and not missing) else "LIMITED"
    note = []
    if missing:
        note.append("missing keys: %s" % sorted(missing))
    if not signed:
        note.append("signature not valid -> LIMITED mode, identity claims withheld")
    return {"data": data, "mode": mode, "note": "; ".join(note) or "ok",
            "version": data.get("version")}, None


def run(task, signal):
    op = task.get("capability")
    loaded, err = _load()
    if err:
        return {"ok": True, "mode": "LIMITED",
                "note": "capsule %s; running LIMITED" % err}
    if op == "capsule.load":
        d = loaded["data"]
        # identity claims withheld in LIMITED mode
        identity = d["identity"] if loaded["mode"] == "SIGNED" else \
            {"mode": "LIMITED", "note": "identity withheld for unsigned capsule"}
        return {"ok": True, "mode": loaded["mode"], "version": loaded["version"],
                "identity": identity, "user": d["user"],
                "boundaries": d["boundaries"],
                "standing_orders": d["standing_orders"],
                "projects": d["projects"],
                "memory_count": len(d["memory"]) if isinstance(d.get("memory"), list) else 0,
                "note": loaded["note"]}
    if op == "capsule.section":
        name = task.get("args", {}).get("section", "")
        d = loaded["data"]
        if name == "identity" and loaded["mode"] != "SIGNED":
            return {"ok": True, "mode": "LIMITED",
                    "note": "identity withheld for unsigned capsule"}
        if name not in d:
            return {"ok": False, "error": "no such section: %r" % name}
        return {"ok": True, "mode": loaded["mode"], "section": name,
                "value": d[name]}
    if op == "capsule.append":
        # Append-only memory write-back. Refused on SIGNED capsules
        # (would break the signature); allowed on LIMITED/dev capsules.
        if loaded["mode"] == "SIGNED":
            return {"ok": False,
                    "error": "capsule is SIGNED; append refused (would break "
                             "signature). Memory write-back goes through the "
                             "ceremony holder."}
        entry = task.get("args", {}).get("entry", {})
        if not isinstance(entry, dict) or not entry:
            return {"ok": False, "error": "args.entry must be a non-empty object"}
        import datetime
        d = loaded["data"]
        mem = d.get("memory")
        if not isinstance(mem, list):
            return {"ok": False, "error": "capsule has no memory list"}
        entry = dict(entry)
        entry.setdefault("date", datetime.date.today().isoformat())
        mem.append(entry)
        tmp = CAPSULE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
        os.replace(tmp, CAPSULE_PATH)
        return {"ok": True, "mode": loaded["mode"],
                "memory_count": len(mem)}
    return {"ok": False, "error": "unknown op"}
