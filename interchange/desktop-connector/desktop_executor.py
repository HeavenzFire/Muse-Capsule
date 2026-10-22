#!/usr/bin/env python3
"""Desktop Connector executor — Muse side. Stdlib only.

Takes a desktop_request package (GPT -> Muse, see
desktop_request.schema.json), validates it, enforces the
authorization tiers, executes the action through Desktop
Commander V1 on this host, and writes a desktop_result package
(see desktop_result.schema.json).

Usage:
    COMMANDER_KEY_FILE=/path/to/commander.key \
        python3 desktop_executor.py <request.json> --out <result.json> \
        [--commander-base http://127.0.0.1:18077]

Rules enforced here, in order, BEFORE any commander contact:
  1. Validation — required fields/enums from the sibling schema,
     per-type payload fields, and hard rules: credentials_in_packages
     must be false, irreversibles_require_user_word must be true,
     and no credential-like content anywhere in the package (the one
     exemption: action.text, the exact text Zachary approved typing).
     The commander key is a 64-char hex string; any 64-char hex
     string in a scanned field is treated as credential-like.
  2. Authorization tiers —
       status, file_read:        an already_given entry names the action
       exec, browser_render:     the specific action is named in
                                 already_given (a command/URL named
                                 after a colon must match exactly)
       type, click, file_write:  DENIED unless already_given
                                 explicitly names that exact action
                                 (exact text / coordinates / path)
       anything in still_required: DENIED, reason recorded
     A denial never contacts the commander; its ledger cannot move.

The key is read from the file named by COMMANDER_KEY_FILE at call
time and sent as X-Commander-Key. It is never written to the
result, to stdout, or to any log.

Exit code: 0 = result package written (check its status),
1 = package failed validation (a failed result is still written),
2 = usage / IO error (no result written).
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "desktop_request.schema.json")
DEFAULT_BASE = "http://127.0.0.1:18077"
OUTPUT_CAP = 64 * 1024  # matches the commander's per-stream cap
SOURCE_PLATFORMS = ["meta-ai-muse", "chatgpt", "gemini", "qwen",
                    "local-field", "human", "other"]
ACTION_TYPES = ["status", "shot", "exec", "type", "click",
                "browser_render", "file_read", "file_write"]
HOSTS = ["asus", "vm"]

CRED_MARKERS = ("password", "passwd", "secret", "token", "otp",
                "api_key", "apikey", "x-commander-key", "bearer ")
HEX64 = re.compile(r"\b[0-9a-fA-F]{64}\b")


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- validation

def scan_credentials(value, where, errors, exempt=False):
    """Flag credential-like content in any package string.
    action.text is exempt: it is the exact text Zachary approved
    typing, and it is ledgered by the commander as count+hash only."""
    if isinstance(value, str):
        if exempt:
            return
        lowered = value.lower()
        for marker in CRED_MARKERS:
            if marker in lowered:
                errors.append("hard rule: %s looks like it carries a "
                              "credential (contains %r); credentials "
                              "never travel in packages" % (where, marker))
                return
        if HEX64.search(value):
            errors.append("hard rule: %s contains a 64-char hex string, "
                          "treated as credential-like (the commander "
                          "key's shape); keys never travel in packages"
                          % where)
        return
    if isinstance(value, dict):
        for k, v in value.items():
            scan_credentials(v, "%s.%s" % (where, k), errors)
        return
    if isinstance(value, list):
        for i, v in enumerate(value):
            scan_credentials(v, "%s[%d]" % (where, i), errors)


def validate(pkg):
    errors = []
    schema = load_json(SCHEMA_PATH)
    props = schema.get("properties", {})

    if not isinstance(pkg, dict):
        return ["package: expected a JSON object"]

    for field in schema.get("required", []):
        if field not in pkg:
            errors.append("package: missing required field '%s'" % field)

    if pkg.get("kind") != "desktop_request":
        errors.append("field 'kind': must be 'desktop_request', got %r"
                      % (pkg.get("kind"),))
    if pkg.get("schema_version") != "1.0.0":
        errors.append("field 'schema_version': must be '1.0.0', got %r"
                      % (pkg.get("schema_version"),))
    if pkg.get("source_platform") not in SOURCE_PLATFORMS:
        errors.append("field 'source_platform': %r is not one of %s"
                      % (pkg.get("source_platform"), SOURCE_PLATFORMS))
    if pkg.get("host") not in HOSTS:
        errors.append("field 'host': %r is not one of %s (a label only — "
                      "never an address)" % (pkg.get("host"), HOSTS))
    if pkg.get("action_type") not in ACTION_TYPES:
        errors.append("field 'action_type': %r is not one of %s"
                      % (pkg.get("action_type"), ACTION_TYPES))

    for block in ("authorization", "permissions", "conversation_reference"):
        if block in pkg and block in props:
            for field in props[block].get("required", []):
                if not isinstance(pkg.get(block), dict) \
                        or field not in pkg[block]:
                    errors.append("block '%s': missing required field '%s'"
                                  % (block, field))

    perms = pkg.get("permissions")
    if isinstance(perms, dict):
        if perms.get("credentials_in_packages") is not False:
            errors.append("hard rule: permissions.credentials_in_packages "
                          "must be false")
        if perms.get("irreversibles_require_user_word") is not True:
            errors.append("hard rule: permissions."
                          "irreversibles_require_user_word must be true")

    stop = pkg.get("stop_conditions")
    if stop is not None and (not isinstance(stop, list) or not stop):
        errors.append("field 'stop_conditions': must be a non-empty list")

    # per-type payload fields
    action = pkg.get("action")
    atype = pkg.get("action_type")
    if isinstance(action, dict) and atype in ACTION_TYPES:
        def need_str(field):
            if not isinstance(action.get(field), str) \
                    or not action.get(field):
                errors.append("action payload: '%s' (non-empty string) "
                              "required for action_type %r" % (field, atype))
        if atype == "exec":
            need_str("command")
        elif atype == "type":
            if not isinstance(action.get("text"), str):
                errors.append("action payload: 'text' (string) required "
                              "for action_type 'type'")
        elif atype == "click":
            for axis in ("x", "y"):
                v = action.get(axis)
                if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                    errors.append("action payload: '%s' (non-negative "
                                  "integer) required for action_type "
                                  "'click'" % axis)
        elif atype == "browser_render":
            url = action.get("url")
            if not isinstance(url, str) \
                    or not url.startswith(("http://", "https://")):
                errors.append("action payload: 'url' (http(s) URL) "
                              "required for action_type 'browser_render'")
        elif atype in ("file_read", "file_write"):
            need_str("path")
            if atype == "file_write" \
                    and not isinstance(action.get("content"), str):
                errors.append("action payload: 'content' (string) "
                              "required for action_type 'file_write'")
    elif atype in ACTION_TYPES and not isinstance(action, dict):
        errors.append("field 'action': expected an object")

    # credential scan — everything except the approved type text
    scan_pkg = dict(pkg)
    if isinstance(scan_pkg.get("action"), dict):
        scan_pkg = dict(scan_pkg)
        scan_pkg["action"] = {k: v for k, v in scan_pkg["action"].items()
                              if k != "text"}
    scan_credentials(scan_pkg, "package", errors)

    return errors


# ---------------------------------------------------------------- authorization

def _entry_names(entry_action, token):
    """True if an already_given action string names this type token
    ('exec', 'exec: ...', 'exec ...', 'file read', ...)."""
    a = entry_action.strip().lower()
    variants = (token, token.replace("_", " "))
    for v in variants:
        if a == v or a.startswith(v + ":") or a.startswith(v + " "):
            return True
    return False


def _entry_detail(entry_action, token):
    """The text after 'token:' in an entry, or None if unspecified."""
    a = entry_action.strip()
    for v in (token, token.replace("_", " ")):
        if a.lower().startswith(v + ":"):
            return a[len(v) + 1:].strip()
    return None


def authorize(pkg):
    """Return None if authorized, else the denial reason."""
    atype = pkg["action_type"]
    action = pkg.get("action") or {}
    auth = pkg.get("authorization") or {}
    given = auth.get("already_given") or []
    still = auth.get("still_required") or []

    if still:
        return ("authorization.still_required is not empty — these "
                "approvals are still outstanding and cannot be "
                "pre-spent by a package: %s" % "; ".join(still))

    entries = [g.get("action", "") for g in given if isinstance(g, dict)]
    naming = [e for e in entries if _entry_names(e, atype)]
    if not naming:
        return ("no authorization.already_given entry names action "
                "type %r; the commander was not contacted" % atype)

    if atype == "type":
        text = action.get("text")
        for e in naming:
            detail = _entry_detail(e, "type")
            if detail is not None and detail == text:
                return None
        return ("action_type 'type' changes state on Zachary's "
                "machine and requires already_given to name the "
                "exact text ('type: <exact text>'); the commander "
                "was not contacted")
    if atype == "click":
        want = ("%d,%d" % (action["x"], action["y"]),
                "%d, %d" % (action["x"], action["y"]))
        for e in naming:
            detail = _entry_detail(e, "click")
            if detail in want:
                return None
        return ("action_type 'click' changes state on Zachary's "
                "machine and requires already_given to name the "
                "exact coordinates ('click: <x>,<y>'); the commander "
                "was not contacted")
    if atype == "file_write":
        for e in naming:
            detail = _entry_detail(e, "file_write")
            if detail == action.get("path"):
                return None
        return ("action_type 'file_write' changes state on "
                "Zachary's machine and requires already_given to "
                "name the exact path ('file_write: <path>'); the "
                "commander was not contacted")
    if atype == "exec":
        for e in naming:
            detail = _entry_detail(e, "exec")
            if detail is None or detail == action.get("command"):
                return None
        return ("authorization.already_given names exec but for a "
                "different specific command; this exact command is "
                "not authorized and the commander was not contacted")
    if atype == "browser_render":
        for e in naming:
            detail = _entry_detail(e, "browser_render")
            if detail is None or detail == action.get("url"):
                return None
        return ("authorization.already_given names browser_render "
                "but for a different specific URL; this exact URL "
                "is not authorized and the commander was not "
                "contacted")
    # status, shot, file_read: naming the action is sufficient
    return None


# ---------------------------------------------------------------- commander

def read_key():
    path = os.environ.get("COMMANDER_KEY_FILE")
    if not path:
        return None, None
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip(), path


def commander_call(base, method, endpoint, key, body=None, timeout=70):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base.rstrip("/") + endpoint,
                                 data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    req.add_header("X-Commander-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"ok": False, "error": raw}


GENESIS_HASH = hashlib.sha256(b"").hexdigest()  # the chain's zero point


def ledger_state(key_path):
    """(head_hash, entries) from the ledger beside the key file —
    the commander's data dir. An absent/empty ledger is the chain
    at genesis: (GENESIS_HASH, 0). (None, None) only when the key
    file location itself is unknown."""
    if not key_path:
        return None, None
    ledger = os.path.join(os.path.dirname(os.path.abspath(key_path)),
                          "ledger.jsonl")
    if not os.path.exists(ledger):
        return GENESIS_HASH, 0
    head, count = None, 0
    with open(ledger, "rb") as f:
        for raw in f:
            line = raw.rstrip(b"\n")
            if not line:
                continue
            count += 1
            head = hashlib.sha256(line).hexdigest()
    return head, count


# ---------------------------------------------------------------- result

def base_result(pkg, status):
    return {
        "schema_version": "1.0.0",
        "kind": "desktop_result",
        "request_id": pkg.get("request_id"),
        "project_id": pkg.get("project_id"),
        "source_platform": "meta-ai-muse",
        "timestamp": now_iso(),
        "host": pkg.get("host"),
        "action_type": pkg.get("action_type"),
        "status": status,
        "performed": [],
        "output": None,
        "artifacts": [],
        "ledger_head_hash": None,
        "ledger_entries": None,
        "unresolved": [],
        "failures": [],
        "permissions": {
            "irreversibles_require_user_word": True,
            "credentials_in_packages": False,
            "notes": "Commander key read from COMMANDER_KEY_FILE at "
                     "call time; written nowhere.",
        },
    }


def trunc(s):
    if s is None:
        return None, False
    b = s.encode("utf-8", "replace")
    if len(b) <= OUTPUT_CAP:
        return s, False
    return b[:OUTPUT_CAP].decode("utf-8", "replace"), True


# ---------------------------------------------------------------- execution

ENDPOINTS = {
    "status": ("GET", "/status", lambda a: None),
    "exec": ("POST", "/exec",
             lambda a: {"command": a["command"],
                        **({"timeout_s": a["timeout_s"]}
                           if a.get("timeout_s") else {})}),
    "shot": ("POST", "/shot", lambda a: {}),
    "type": ("POST", "/type", lambda a: {"text": a["text"]}),
    "click": ("POST", "/click", lambda a: {"x": a["x"], "y": a["y"]}),
    "browser_render": ("POST", "/browser/render",
                       lambda a: {"url": a["url"]}),
}


def run(pkg, base):
    atype = pkg["action_type"]
    action = pkg.get("action") or {}
    result = base_result(pkg, "failed")
    result["performed"].append("executor validated package: PASS")
    result["performed"].append(
        "authorization check: PASS (tier for %r)" % atype)

    try:
        key, key_path = read_key()
    except OSError as exc:
        result["failures"].append({
            "step": "read commander key file",
            "message": "COMMANDER_KEY_FILE unreadable: %s" % exc})
        return result, 0
    root = os.path.dirname(os.path.abspath(key_path)) if key_path else None

    if atype in ("file_read", "file_write"):
        result["performed"].append(
            "Commander V1 exposes no file endpoint; executor performs "
            "this itself on the host, contained in the commander "
            "root (%s)" % (root or "unknown"))
        if not root:
            result["failures"].append({
                "step": "file operation",
                "message": "COMMANDER_KEY_FILE not set; commander "
                           "root cannot be established"})
            return result, 0
        target = os.path.realpath(os.path.join(root,
                                               action.get("path", "")))
        if os.path.commonpath([root, target]) != root:
            result["status"] = "denied"
            result["failures"].append({
                "step": "file operation containment check",
                "message": "path %r escapes the commander root; "
                           "denied" % action.get("path")})
            return result, 0
        try:
            if atype == "file_read":
                with open(target, "rb") as f:
                    raw = f.read(OUTPUT_CAP + 1)
                out, was_trunc = trunc(raw.decode("utf-8", "replace"))
                result["output"] = {
                    "stdout": out, "stderr": None, "exit_code": 0,
                    "stdout_truncated": was_trunc,
                    "stderr_truncated": False,
                    "commander_response": None}
            else:
                with open(target, "w", encoding="utf-8") as f:
                    f.write(action["content"])
                result["output"] = {
                    "stdout": None, "stderr": None, "exit_code": 0,
                    "stdout_truncated": False,
                    "stderr_truncated": False,
                    "commander_response": {
                        "written_path": action["path"],
                        "bytes": len(action["content"].encode("utf-8"))}}
            result["status"] = "ok"
            result["performed"].append(
                "%s completed at %s" % (atype, action["path"]))
        except OSError as exc:
            result["failures"].append({"step": atype, "message": str(exc)})
        head, count = ledger_state(key_path)
        result["ledger_head_hash"], result["ledger_entries"] = head, count
        if head is None:
            result["unresolved"].append(
                "commander ledger not readable from this host; head "
                "hash not recorded")
        return result, 0

    if not key:
        result["failures"].append({
            "step": "read commander key",
            "message": "COMMANDER_KEY_FILE is not set; the executor "
                       "cannot authenticate to the commander and no "
                       "key travels any other way"})
        return result, 0

    method, endpoint, build = ENDPOINTS[atype]
    result["performed"].append(
        "%s %s via commander at %s (host label: %s)"
        % (method, endpoint, base, pkg.get("host")))
    try:
        http_status, resp = commander_call(base, method, endpoint,
                                           key, build(action))
    except Exception as exc:  # unreachable / no response at all
        result["status"] = "unknown"
        result["failures"].append({
            "step": "%s %s" % (method, endpoint),
            "message": "commander unreachable: %s: %s"
                       % (type(exc).__name__, exc)})
        head, count = ledger_state(key_path)
        result["ledger_head_hash"], result["ledger_entries"] = head, count
        return result, 0

    head, count = ledger_state(key_path)
    result["ledger_head_hash"], result["ledger_entries"] = head, count
    if head is None:
        result["unresolved"].append(
            "commander ledger not readable from this host; head hash "
            "not recorded")

    if http_status == 200 and resp.get("ok"):
        result["status"] = "ok"
        if atype == "exec":
            out, out_t = trunc(resp.get("stdout"))
            err, err_t = trunc(resp.get("stderr"))
            result["output"] = {
                "stdout": out, "stderr": err,
                "exit_code": resp.get("exit_code"),
                "stdout_truncated": out_t, "stderr_truncated": err_t,
                "commander_response": None}
        elif atype == "shot":
            shot_path = resp.get("path")
            artifact = {"kind": "screenshot", "sha256": None,
                        "bytes": resp.get("bytes")}
            if shot_path and os.path.exists(shot_path):
                h = hashlib.sha256()
                with open(shot_path, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 16), b""):
                        h.update(chunk)
                artifact["sha256"] = h.hexdigest()
            else:
                result["unresolved"].append(
                    "screenshot file not readable from the executor "
                    "host; sha256 not recorded (bytes from commander "
                    "response only)")
            result["artifacts"].append(artifact)
            result["output"] = {
                "stdout": None, "stderr": None, "exit_code": None,
                "stdout_truncated": False, "stderr_truncated": False,
                "commander_response": {
                    "tool": resp.get("tool"), "bytes": resp.get("bytes"),
                    "note": "image delivered to Zachary in chat; "
                            "referenced here by sha256 + bytes only"}}
            result["performed"].append(
                "screenshot recorded as artifact reference "
                "(sha256 + bytes only; image never enters a package)")
        else:
            result["output"] = {
                "stdout": None, "stderr": None, "exit_code": None,
                "stdout_truncated": False, "stderr_truncated": False,
                "commander_response": resp}
    else:
        # Includes the honest 501s: recorded verbatim, never faked.
        result["status"] = "failed"
        result["failures"].append({
            "step": "%s %s" % (method, endpoint),
            "message": "HTTP %d: %s" % (http_status,
                                         resp.get("error", resp))})
        result["output"] = {
            "stdout": None, "stderr": None, "exit_code": None,
            "stdout_truncated": False, "stderr_truncated": False,
            "commander_response": resp}
    return result, 0


def main(argv):
    args = []
    base = DEFAULT_BASE
    out_path = None
    i = 1
    while i < len(argv):
        if argv[i] == "--commander-base" and i + 1 < len(argv):
            base = argv[i + 1]
            i += 2
        elif argv[i] == "--out" and i + 1 < len(argv):
            out_path = argv[i + 1]
            i += 2
        elif argv[i].startswith("--"):
            i += 1
        else:
            args.append(argv[i])
            i += 1
    if len(args) != 1 or not out_path:
        print("usage: desktop_executor.py <request.json> --out "
              "<result.json> [--commander-base URL]")
        return 2
    try:
        pkg = load_json(args[0])
    except (OSError, json.JSONDecodeError) as exc:
        print("FAIL %s: cannot read package: %s" % (args[0], exc))
        return 2

    def write_result(res):
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, ensure_ascii=False)
            f.write("\n")

    errors = validate(pkg)
    if errors:
        res = base_result(pkg if isinstance(pkg, dict) else {}, "failed")
        res["performed"].append("executor validation: FAIL — no "
                                "commander contact")
        for err in errors:
            res["failures"].append({"step": "validation",
                                    "message": err})
        write_result(res)
        print("FAIL %s (desktop_request package): %d problem(s)"
              % (args[0], len(errors)))
        for err in errors:
            print("  - %s" % err)
        print("result written to %s (status: failed)" % out_path)
        return 1

    denial = authorize(pkg)
    if denial:
        res = base_result(pkg, "denied")
        res["performed"].append("executor validated package: PASS")
        res["performed"].append("no commander contact (denied at "
                                "authorization check)")
        res["failures"].append({"step": "authorization",
                                "message": denial})
        write_result(res)
        print("DENIED %s: %s" % (args[0], denial))
        print("result written to %s (status: denied)" % out_path)
        return 0

    res, code = run(pkg, base)
    write_result(res)
    print("DONE %s -> %s (status: %s)"
          % (args[0], out_path, res["status"]))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
