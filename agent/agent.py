#!/usr/bin/env python3
"""
heavenzfire-agent: the think-act-observe agent loop for Zachary's local machine.

Like the cloud agent: the model reasons, calls tools, observes results, and
continues until the task is done. Not a chatbot -- a doer.

- stdlib only (urllib, json, subprocess, hashlib). Nothing leaves the machine.
- Model: Ollama `heavenzfire` (env HF_AGENT_MODEL) at 127.0.0.1:11434.
- Soul + capsule loaded as system context every run.
- Approval gate: destructive actions PAUSE and ask Zachary in the console.
  Nothing destructive runs unapproved. This is his tap, enforced in code.
- Every thought, tool call, and observation goes into a hash-chained audit
  log (kernel EventLog format). Bodies are hashed; the log never holds secrets.

Usage:
    python agent.py "summarize the notes in ./notes and save a digest"
    python agent.py "check which python version is installed" --max-rounds 10
    python agent.py --verify-audit
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
import datetime

# ---------------------------------------------------------------- config

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OLLAMA_URL = os.environ.get("HF_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("HF_AGENT_MODEL", "heavenzfire")
AGENT_DIR = os.environ.get("HF_AGENT_DIR", os.path.join(SCRIPT_DIR, "data"))
AUDIT_LOG = os.path.join(AGENT_DIR, "audit.log")
WORKDIR = os.path.abspath(os.environ.get("HF_AGENT_WORKDIR", os.getcwd()))
MAX_ROUNDS_DEFAULT = 25
MAX_OUTPUT = 65536          # captured subprocess output cap
OBS_TRUNC = 4000            # what the model sees per observation

SHELL_ALLOWLIST = {"git", "gh", "python", "pip", "node", "npm", "npx", "ollama"}


def _capsule_dir():
    env = os.environ.get("HF_CAPSULE_DIR")
    if env and os.path.isdir(env):
        return env
    win = r"C:\sixteen\capsule"
    if os.path.isdir(win):
        return win
    local = os.path.join(SCRIPT_DIR, "capsule")
    if os.path.isdir(local):
        return local
    return None


# ---------------------------------------------------------------- EventLog
# Vendored from prime-brain-build/kernel.py (EventLog). Same format:
# entry hash = sha256(canonical_json(line)), chained via "prev".

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class EventLog:
    def __init__(self, path=AUDIT_LOG):
        self.path = path
        self.seq = 0
        self.tick = 0
        self.head = "GENESIS"
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        if os.path.exists(path):
            self._replay()

    def _replay(self):
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                e = json.loads(line)
                self.seq = e["seq"]
                self.tick = e["t"]
                self.head = sha256_hex(line.encode("utf-8"))

    def append(self, etype, **fields):
        self.seq += 1
        self.tick += 1
        e = {"seq": self.seq, "t": self.tick, "type": etype, "prev": self.head}
        e.update(fields)
        line = canonical(e)
        h = sha256_hex(line.encode("utf-8"))
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        self.head = h
        return {"seq": self.seq, "hash": h}

    def verify(self):
        if not os.path.exists(self.path):
            return {"ok": True, "entries": 0, "head": "GENESIS"}
        prev = "GENESIS"
        n = 0
        with open(self.path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line:
                    continue
                n += 1
                e = json.loads(line)
                if e.get("seq") != n or e.get("prev") != prev:
                    return {"ok": False, "at": n}
                prev = sha256_hex(line.encode("utf-8"))
        return {"ok": True, "entries": n, "head": prev}


# ---------------------------------------------------------------- capsule

def load_capsule():
    """Returns combined soul + standing orders + memory text (may be empty)."""
    d = _capsule_dir()
    if not d:
        return ""
    parts = []
    for name in ("soul.md", "standing-orders.md", "memory.md"):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    parts.append(f.read().strip())
            except Exception:
                pass
    return "\n\n".join(p for p in parts if p)


def capsule_memory_path():
    d = _capsule_dir()
    if not d:
        return None
    return os.path.join(d, "memory.md")


# ---------------------------------------------------------------- ollama

class OllamaError(Exception):
    pass


def ollama_chat(messages, model=MODEL, temperature=0.3, num_ctx=8192,
                 timeout=300):
    """One non-streaming /api/chat call. Returns the assistant's text."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL + "/api/chat", data=payload,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise OllamaError(
            "cannot reach Ollama at %s: %s. Is Ollama running and is the "
            "'%s' model built? (ollama create %s -f Modelfile)"
            % (OLLAMA_URL, e, model, model))
    msg = (data.get("message") or {}).get("content", "")
    if not msg:
        raise OllamaError("empty response from model %r" % model)
    return msg

# ---------------------------------------------------------------- tools
# Each maps to the corresponding PRIME worker logic (shell_worker allowlist,
# fs_worker rooted paths, web_worker read-only fetch). Reused, not reinvented.

TOOLS = {
    "shell.exec": {
        "desc": "Run a command as an argv list (no shell strings). "
                "Allowlisted programs only.",
        "args": {"argv": ["git", "status"], "cwd": "/optional/dir",
                 "timeout": 60},
    },
    "fs.read": {
        "desc": "Read a text file (first 64KB). Paths stay inside the work dir.",
        "args": {"path": "notes/todo.md"},
    },
    "fs.write": {
        "desc": "Write a text file. Inside the work dir: fine. Outside: "
                "needs Zachary's approval.",
        "args": {"path": "out/report.md", "content": "..."},
    },
    "fs.list": {
        "desc": "List a directory (first 500 names).",
        "args": {"path": "."},
    },
    "web.fetch": {
        "desc": "Read-only fetch of an http(s) URL, returned as plain text.",
        "args": {"url": "https://example.com"},
    },
    "memory.save": {
        "desc": "Append a dated entry to the capsule memory. Durable.",
        "args": {"text": "Zachary prefers ..."},
    },
    "memory.search": {
        "desc": "Grep the capsule files for a query.",
        "args": {"query": "standing order"},
    },
    "forge.dry": {
        "desc": "Azazel dry-run: READ-ONLY inspection of a path (tree + "
                "sizes + file heads). Never executes anything.",
        "args": {"path": "./src"},
    },
}


def _extra_roots():
    roots = [WORKDIR]
    env = os.environ.get("HF_AGENT_ROOTS", "")
    for r in env.split(os.pathsep):
        if r.strip():
            roots.append(os.path.abspath(r))
    cap = _capsule_dir()
    if cap:
        roots.append(os.path.abspath(cap))
    return roots


def _safe_path(path):
    """Resolve under allowed roots; refuse dotfiles and escapes."""
    ap = os.path.abspath(os.path.join(WORKDIR, path or ""))
    for part in ap.split(os.sep):
        if part.startswith(".") and part not in (".", ".."):
            return None, "dotfile/dotdir access refused"
    for r in _extra_roots():
        if ap == r or ap.startswith(r + os.sep):
            return ap, None
    return None, "path outside allowed roots: %s" % path


def _is_destructive_shell(argv):
    toks = [str(t).lower() for t in argv]
    if not toks:
        return False, ""
    if toks[0] in ("rm", "del", "rmdir", "rd", "format", "mkfs", "dd"):
        return True, "delete/format command: %s" % toks[0]
    if "--force" in toks or "-rf" in toks:
        return True, "force flag present"
    joined = " ".join(toks)
    if re.search(r"\bgit\s+(push\b|clean\b.*-f|reset\s+--hard)", joined):
        return True, "destructive git operation"
    if re.search(r"\b(drop|delete)\b.*\b(table|database)\b", joined):
        return True, "destructive database operation"
    return False, ""


def tool_shell_exec(args):
    argv = args.get("argv")
    if not isinstance(argv, list) or not argv or \
            not all(isinstance(a, str) for a in argv):
        return {"ok": False, "error": "argv must be a non-empty list of strings"}
    prog = os.path.basename(argv[0]).lower()
    if prog not in SHELL_ALLOWLIST and argv[0] not in SHELL_ALLOWLIST:
        return {"ok": False, "error": "command not allowlisted: %r" % argv[0]}
    destructive, why = _is_destructive_shell(argv)
    timeout = min(int(args.get("timeout", 60) or 60), 300)
    cwd = args.get("cwd") or WORKDIR
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
    return {"ok": True, "returncode": p.returncode, "stdout": out,
            "stderr": err, "_destructive": destructive, "_why": why}


def tool_fs_read(args):
    ap, err = _safe_path(args.get("path", ""))
    if err:
        return {"ok": False, "error": err}
    try:
        with open(ap, "r", encoding="utf-8", errors="replace") as f:
            return {"ok": True, "path": ap, "content": f.read(65536)}
    except FileNotFoundError:
        return {"ok": False, "error": "not found: %s" % ap}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


def tool_fs_write(args):
    raw = args.get("path", "")
    ap = os.path.abspath(os.path.join(WORKDIR, raw))
    inside = (ap == WORKDIR or ap.startswith(WORKDIR + os.sep))
    safe, err = _safe_path(raw)
    if err:
        return {"ok": False, "error": err}
    needs_approval = not inside
    try:
        os.makedirs(os.path.dirname(safe), exist_ok=True)
        content = args.get("content", "")
        if not isinstance(content, str):
            return {"ok": False, "error": "content must be a string"}
        with open(safe, "w", encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "path": safe, "bytes": len(content),
                "_needs_approval": needs_approval}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


def tool_fs_list(args):
    ap, err = _safe_path(args.get("path", "."))
    if err:
        return {"ok": False, "error": err}
    try:
        names = sorted(os.listdir(ap))
        return {"ok": True, "path": ap, "names": names[:500]}
    except FileNotFoundError:
        return {"ok": False, "error": "not found: %s" % ap}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


_BLOCKED_HOSTS = {"169.254.169.254", "metadata.google.internal",
                  "metadata.google.internal."}


def tool_web_fetch(args):
    url = args.get("url", "")
    if not (url.startswith("http://") or url.startswith("https://")):
        return {"ok": False, "error": "only http(s) URLs"}
    host = re.sub(r"^https?://", "", url).split("/")[0].split("@")[-1].split(":")[0]
    if host.lower() in _BLOCKED_HOSTS:
        return {"ok": False, "error": "blocked host"}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HeavenzFire/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            page = r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "fetch failed: %s" % e}
    import html as _html
    text = re.sub(r"<script.*?</script>", " ", page, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return {"ok": True, "url": url, "text": text[:8000]}


def tool_memory_save(args):
    text = args.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "error": "text must be a non-empty string"}
    mp = capsule_memory_path()
    if not mp:
        return {"ok": False, "error": "no capsule dir found"}
    entry = "- %s: %s\n" % (datetime.date.today().isoformat(), text.strip())
    try:
        os.makedirs(os.path.dirname(mp), exist_ok=True)
        with open(mp, "a", encoding="utf-8") as f:
            f.write(entry)
        return {"ok": True, "saved": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


def tool_memory_search(args):
    q = args.get("query", "")
    if not isinstance(q, str) or not q.strip():
        return {"ok": False, "error": "query must be a non-empty string"}
    d = _capsule_dir()
    if not d:
        return {"ok": False, "error": "no capsule dir found"}
    hits = []
    ql = q.lower()
    for name in ("soul.md", "standing-orders.md", "memory.md"):
        p = os.path.join(d, name)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if ql in line.lower():
                        hits.append("%s:%d: %s" % (name, i, line.strip()))
                        if len(hits) >= 30:
                            break
        except Exception:
            pass
    return {"ok": True, "query": q, "hits": hits}


def tool_forge_dry(args):
    """Azazel dry-run: read-only inspection. Never executes anything."""
    ap, err = _safe_path(args.get("path", "."))
    if err:
        return {"ok": False, "error": err}
    if not os.path.isdir(ap):
        return {"ok": False, "error": "not a directory: %s" % ap}
    entries = []
    for root, dirs, files in os.walk(ap):
        dirs[:] = [d for d in dirs if not d.startswith(".")][:50]
        rel = os.path.relpath(root, ap)
        for fn in sorted(files):
            if fn.startswith("."):
                continue
            fp = os.path.join(root, fn)
            try:
                sz = os.path.getsize(fp)
            except OSError:
                continue
            entries.append({"path": os.path.normpath(os.path.join(rel, fn)),
                            "bytes": sz})
            if len(entries) >= 200:
                break
        if len(entries) >= 200:
            break
    heads = {}
    for e in entries[:10]:
        fp = os.path.join(ap, e["path"])
        if e["bytes"] > 20480:
            continue
        if not re.search(r"\.(py|md|txt|json|js|ps1|toml|yaml|yml|cfg|ini)$",
                         e["path"]):
            continue
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                heads[e["path"]] = "".join(f.readlines()[:40])
        except OSError:
            pass
    return {"ok": True, "path": ap, "entries": len(entries),
            "tree": entries[:200], "heads": heads,
            "note": "dry-run: inspected only, nothing executed"}


TOOL_FUNCS = {
    "shell.exec": tool_shell_exec,
    "fs.read": tool_fs_read,
    "fs.write": tool_fs_write,
    "fs.list": tool_fs_list,
    "web.fetch": tool_web_fetch,
    "memory.save": tool_memory_save,
    "memory.search": tool_memory_search,
    "forge.dry": tool_forge_dry,
}


def needs_approval(tool, args, result):
    """His tap, enforced in code. Returns (needed: bool, description)."""
    if tool == "shell.exec":
        if result.get("_destructive"):
            return True, "destructive shell command: %s (%s)" % (
                " ".join(args.get("argv", [])), result.get("_why", ""))
        return False, ""
    if tool == "fs.write":
        if result.get("_needs_approval"):
            return True, "write outside work dir: %s" % result.get("path", "?")
        return False, ""
    return False, ""

# ---------------------------------------------------------------- approval
# The gate MUST run before execution. precheck() classifies without touching
# anything; the loop asks Zachary in the console and only executes on "y".

def precheck(tool, args):
    """Returns (needs_approval: bool, description: str). No side effects."""
    if tool == "shell.exec":
        argv = args.get("argv", [])
        bad, why = _is_destructive_shell(argv if isinstance(argv, list) else [])
        if bad:
            return True, "destructive shell command: %s (%s)" % (
                " ".join(str(a) for a in argv), why)
        return False, ""
    if tool == "fs.write":
        raw = args.get("path", "")
        ap = os.path.abspath(os.path.join(WORKDIR, raw))
        if not (ap == WORKDIR or ap.startswith(WORKDIR + os.sep)):
            return True, "write outside work dir: %s" % ap
        return False, ""
    return False, ""


def console_approver(desc):
    print("\n[APPROVAL NEEDED] %s" % desc)
    try:
        ans = input("Approve? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nno approval given.")
        return False
    return ans in ("y", "yes")


# ---------------------------------------------------------------- parsing

def _extract_json(text):
    """Pull the model's tool-call JSON out of its reply.

    Contract: one ```json fence with a single object. Fallbacks handle
    sloppy fencing from small models; unparseable output is an error the
    loop feeds back so the model can correct itself.
    """
    blocks = re.findall(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    for b in reversed(blocks):
        b = b.strip()
        if b.startswith("{"):
            try:
                return json.loads(b)
            except Exception:
                continue
    # fallback: largest {...} span
    for m in sorted(re.finditer(r"\{.*\}", text, re.S),
                    key=lambda m: m.end() - m.start(), reverse=True):
        try:
            return json.loads(m.group(0))
        except Exception:
            continue
    return None


# ---------------------------------------------------------------- agent

AGENT_SYSTEM = """{soul}

You are operating in AGENT MODE on Zachary's own machine. You accomplish
tasks by calling tools in a loop: reason, call one tool, read the
observation, continue until done. You are a doer, not a chatbot.

CAPSULE (his memory, standing orders — already part of you):
{capsule}

TOOLS — call exactly one per response:
- shell.exec: {{"argv": ["git", "status"], "cwd": "/optional/dir", "timeout": 60}}
  argv lists only, no shell strings. Allowlisted: git gh python pip node npm npx ollama.
- fs.read: {{"path": "notes/todo.md"}}
- fs.write: {{"path": "out/report.md", "content": "..."}}
- fs.list: {{"path": "."}}
- web.fetch: {{"url": "https://example.com"}} (read-only)
- memory.save: {{"text": "..."}} (durable capsule entry)
- memory.search: {{"query": "..."}}
- forge.dry: {{"path": "./src"}} (read-only inspection, never executes)

WORK DIR: {workdir}
- fs.read/fs.list/fs.write stay inside it or the capsule. Writes outside it
  pause for Zachary's approval (asked automatically — you just call the tool).
- Destructive shell commands (delete/format/force/git push) pause the same way.

RESPONSE FORMAT — every response is exactly one JSON object in a ```json fence:
```json
{{"thought": "what I am doing and why", "tool": "fs.list", "args": {{"path": "."}}}}
```
When the task is fully complete:
```json
{{"thought": "brief summary", "done": true, "result": "final answer for Zachary"}}
```

RULES:
- One tool per response. Never invent tool results — call the tool.
- Prefer reading before writing. Verify before claiming done.
- If an observation shows an error, adjust and retry; don't repeat the same
  failing call more than twice.
- If you are stuck, declare done with what you found — never loop forever.
- Plain and direct. His words. No mysticism.
"""


class Agent:
    def __init__(self, task, model=MODEL, max_rounds=MAX_ROUNDS_DEFAULT,
                 workdir=WORKDIR, log=None, approver=None, chat_fn=None):
        self.task = task
        self.model = model
        self.max_rounds = max_rounds
        self.workdir = os.path.abspath(workdir)
        # Tools are module-level functions rooted at the WORKDIR global.
        # A running agent owns its process, so its workdir governs them.
        global WORKDIR
        WORKDIR = self.workdir
        self.log = log or EventLog()
        self.approver = approver or console_approver
        self.chat_fn = chat_fn or (lambda msgs: ollama_chat(
            msgs, model=self.model))
        soul = load_capsule()
        self.system = AGENT_SYSTEM.format(
            soul="(no capsule found — running on the soul prompt only)"
            if not soul else "",
            capsule=soul if soul else "(capsule not found)",
            workdir=workdir)

    def _audit(self, etype, secret_fields=(), **fields):
        # Bodies are hashed; the log never holds secrets or full outputs.
        safe = {}
        for k, v in fields.items():
            if k in secret_fields:
                s = json.dumps(v, sort_keys=True, default=str)
                safe[k + "_sha256"] = sha256_hex(s.encode("utf-8"))
                safe[k + "_preview"] = str(v)[:300]
            else:
                safe[k] = v
        return self.log.append(etype, **safe)

    def run(self):
        self._audit("task_started", task=self.task, model=self.model,
                    workdir=self.workdir, max_rounds=self.max_rounds)
        print("task: %s" % self.task)
        print("model: %s  workdir: %s" % (self.model, self.workdir))
        messages = [
            {"role": "system", "content": self.system},
            {"role": "user", "content": "TASK: " + self.task},
        ]
        for rnd in range(1, self.max_rounds + 1):
            print("\n--- round %d/%d ---" % (rnd, self.max_rounds))
            try:
                reply = self.chat_fn(messages)
            except OllamaError as e:
                print("OLLAMA ERROR: %s" % e)
                self._audit("task_stopped", reason="ollama_error",
                            secret_fields=("error",), error=str(e))
                return {"ok": False, "error": str(e)}
            messages.append({"role": "assistant", "content": reply})
            call = _extract_json(reply)
            if call is None:
                obs = ("ERROR: I could not find a JSON tool call in your "
                       "reply. Respond with exactly one ```json fenced object "
                       "using the documented format.")
                print("! unparseable reply; asking model to reformat")
                self._audit("thought", secret_fields=("text",),
                            text="(unparseable reply)")
                messages.append({"role": "user", "content": obs})
                continue
            thought = call.get("thought", "")
            print("thought: %s" % thought[:300])
            self._audit("thought", secret_fields=("text",), text=thought)
            if call.get("done"):
                result = call.get("result", "")
                print("\nDONE: %s" % result[:500])
                self._audit("task_done", secret_fields=("result",),
                            result=result, rounds=rnd)
                return {"ok": True, "result": result, "rounds": rnd}
            tool = call.get("tool")
            args = call.get("args", {}) or {}
            if tool not in TOOL_FUNCS:
                obs = "ERROR: unknown tool %r. Available: %s" % (
                    tool, ", ".join(sorted(TOOL_FUNCS)))
                print("! %s" % obs)
                messages.append({"role": "user", "content": obs})
                continue
            # --- approval gate: BEFORE execution ---
            need, desc = precheck(tool, args)
            if need:
                self._audit("approval_asked", tool=tool,
                            secret_fields=("desc",), desc=desc)
                ok = self.approver(desc)
                self._audit("approval_decision", tool=tool, approved=bool(ok))
                if not ok:
                    obs = ("APPROVAL DENIED by Zachary. Do not retry this "
                           "action. Find another way or declare done.")
                    print("! approval denied")
                    messages.append({"role": "user", "content": obs})
                    continue
                print("approval granted.")
            # --- execute ---
            self._audit("tool_call", tool=tool, secret_fields=("args",),
                        args=args)
            print("tool: %s %s" % (tool, json.dumps(args)[:200]))
            try:
                res = TOOL_FUNCS[tool](args)
            except Exception as e:  # noqa: BLE001 - tool faults are data
                res = {"ok": False, "error": "%s: %s"
                       % (type(e).__name__, e)}
            res = {k: v for k, v in res.items() if not k.startswith("_")}
            preview = json.dumps(res, default=str)[:OBS_TRUNC]
            print("observation: %s" % preview[:300])
            self._audit("tool_result", tool=tool, ok=bool(res.get("ok")),
                        secret_fields=("result",), result=res)
            messages.append({
                "role": "user",
                "content": "OBSERVATION from %s:\n%s" % (tool, preview),
            })
        print("\nSTOPPED: max rounds (%d) reached." % self.max_rounds)
        self._audit("task_stopped", reason="max_rounds",
                    rounds=self.max_rounds)
        return {"ok": False, "error": "max rounds reached",
                "rounds": self.max_rounds}


# ---------------------------------------------------------------- cli

def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="HeavenzFire local agent")
    ap.add_argument("task", nargs="?", help="natural-language task")
    ap.add_argument("--max-rounds", type=int, default=MAX_ROUNDS_DEFAULT)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--workdir", default=WORKDIR)
    ap.add_argument("--verify-audit", action="store_true",
                    help="verify the audit chain and exit")
    ns = ap.parse_args(argv)

    if ns.verify_audit:
        v = EventLog().verify()
        print("audit verify: %s" % v)
        return 0 if v["ok"] else 1
    if not ns.task:
        ap.print_help()
        print("\nexample: python agent.py \"list the notes dir and summarize\"")
        return 2
    agent = Agent(ns.task, model=ns.model, max_rounds=ns.max_rounds,
                  workdir=os.path.abspath(ns.workdir))
    out = agent.run()
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
