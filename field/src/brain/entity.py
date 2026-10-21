"""Entity: capsule-driven system prompt + Ollama tool-calling loop.

- System prompt is built from the capsule (identity/user/boundaries/orders).
- Unsigned capsule -> LIMITED mode, identity claims withheld, stated plainly.
- Tool loop: max 5 rounds, 90s wall budget. Model emits tool calls as
  ```tool {"capability": "...", "args": {...}}``` fenced blocks.
- Boundary veto: if the capsule boundaries refuse the request, no model call.
"""
import json
import os
import re
import time
import urllib.request

MODEL = os.environ.get("SIXTEEN_MODEL", "qwen2.5:7b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MAX_ROUNDS = 5
BUDGET_S = 90

# Cloud spare rung: provider-agnostic, OpenAI-compatible. Local is primary;
# this rung is SKIPPED when the key or model is empty (his key, his choice).
CLOUD_API_KEY = os.environ.get("CLOUD_API_KEY", "")
CLOUD_API_URL = os.environ.get("CLOUD_API_URL", "https://api.openai.com/v1")
CLOUD_MODEL = os.environ.get("CLOUD_MODEL", "")

TOOL_RE = re.compile(r"```tool\s*(\{.*?\})\s*```", re.DOTALL)


def ollama_chat(messages, model=MODEL, timeout=60):
    body = json.dumps({"model": model, "messages": messages,
                       "stream": False}).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["message"]["content"]


def cloud_chat(messages, timeout=60):
    """Spare rung. Returns None when unconfigured (key/model empty) -> skipped."""
    if not CLOUD_API_KEY or not CLOUD_MODEL:
        return None
    body = json.dumps({"model": CLOUD_MODEL, "messages": messages}).encode("utf-8")
    req = urllib.request.Request(
        CLOUD_API_URL.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + CLOUD_API_KEY})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def model_chat(messages, timeout=60, offline=False):
    """Local primary, cloud spares. Returns (text, rung).
    offline=True: only the ollama rung is tried; anything else is refused.
    Uses provider_router: tries rungs in HF_PROVIDER_ORDER, failing over
    on quota/unreachable. Never silently substitutes."""
    import provider_router
    provider_router.TIMEOUT = timeout
    if offline:
        os.environ["HF_PROVIDER_ORDER"] = "ollama"
    try:
        return provider_router.route_chat(messages)
    except provider_router.ProviderError as e:
        raise RuntimeError(str(e))


def build_system_prompt(capsule):
    mode = capsule.get("mode", "LIMITED")
    lines = [
        "You are the local entity running on Zachary's own machine.",
        "Voice: plain, warm, blunt, mechanism-first. No mysticism.",
        "User: %s" % capsule.get("user", "Zachary"),
        "Capsule mode: %s" % mode,
    ]
    if mode != "SIGNED":
        lines.append("LIMITED mode: identity claims are withheld. Say so when asked.")
    else:
        lines.append("Identity: %s" % json.dumps(capsule.get("identity", {}))[:500])
    lines.append("Boundaries (never cross): %s"
                 % json.dumps(capsule.get("boundaries", []))[:800])
    lines.append("Standing orders: %s"
                 % json.dumps(capsule.get("standing_orders", []))[:800])
    lines.append("Projects: %s" % json.dumps(capsule.get("projects", []))[:500])
    lines.append(
        "Tools: emit a fenced block ```tool {\"capability\": \"...\", \"args\": {...}}``` "
        "to call a tool. Capabilities: shell.run, fs.read, fs.write, fs.list, "
        "fs.mkdir, browse.open, web.search, web.fetch, notes.create, notes.read, "
        "notes.list, notes.search, diag.check, capsule.section, capsule.append "
        "(append a {entry:{...}} memory fact to the capsule; append-only, never rewrite). "
        "Destructive actions need approval and will "
        "be refused without it. When done, reply in plain text with no tool block.")
    return "\n".join(lines)


def check_veto(capsule, text):
    """Boundary veto before the model is even called."""
    low = text.lower()
    for b in capsule.get("boundaries", []):
        bl = str(b).lower()
        if "offensive" in bl and any(w in low for w in
                                     ["attack", "hack", "exploit", "ddos"]):
            return "boundary: offensive action refused"
        if "unauthorized access" in bl and any(w in low for w in
                                               ["bypass login", "crack password",
                                                "unauthorized"]):
            return "boundary: unauthorized access refused"
    return None


def run_turn(user_text, kernel, memory, capsule, session="default",
             tools_allowed=None, offline=False, on_event=None):
    veto = check_veto(capsule, user_text)
    if veto:
        memory.add("turn", "VETOED user text: %s" % user_text[:200], session)
        return {"text": "I can't do that — %s." % veto, "vetoed": True,
                "route": "veto", "capsule": capsule.get("mode", "LIMITED")}

    def emit(etype, **fields):
        if on_event:
            try:
                on_event({"type": etype, "session": session, **fields})
            except Exception:
                pass

    # tools_allowed: None = all non-destructive defaults; list = explicit filter
    allowed = set(tools_allowed) if tools_allowed else None

    system = build_system_prompt(capsule)
    facts = memory.facts()
    if any(facts.get(k) for k in ("facts", "preferences", "decisions", "commitments")):
        system += "\nDurable memory: %s" % json.dumps(facts)[:1500]

    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user_text}]
    deadline = time.time() + BUDGET_S
    tool_results = []
    final_text = ""
    rung = "local"
    for _ in range(MAX_ROUNDS):
        if time.time() > deadline:
            break
        try:
            reply, rung = model_chat(messages,
                                     timeout=min(60, max(5, deadline - time.time())),
                                     offline=offline)
            emit("rung", rung=rung)
        except Exception as e:  # noqa: BLE001 - model faults are data
            return {"text": "No model reachable: %s" % e,
                    "vetoed": False, "route": "model_error",
                    "capsule": capsule.get("mode", "LIMITED")}
        m = TOOL_RE.search(reply)
        if not m:
            final_text = reply
            break
        try:
            call = json.loads(m.group(1))
        except Exception:
            final_text = reply
            break
        cap = call.get("capability", "")
        if allowed is not None and cap not in allowed \
                and not any(cap == a or (a.endswith("*") and cap.startswith(a[:-1]))
                            for a in allowed):
            emit("tool_denied", capability=cap)
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user",
                             "content": "Tool %s is not allowed in this session. "
                             "Continue without it or reply." % cap})
            continue
        emit("tool_start", capability=cap)
        res = kernel.submit({"capability": cap, "args": call.get("args", {})},
                            timeout=60)
        emit("tool_done", capability=cap, ok=bool(res.get("ok")))
        tool_results.append({"capability": cap, "ok": res.get("ok"),
                             "summary": str(res.get("error") or
                                            res.get("note") or "ok")[:120]})
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user",
                         "content": "Tool result for %s: %s\nContinue or reply."
                         % (cap, json.dumps(res)[:2000])})
    else:
        final_text = final_text or "Tool budget exhausted."

    memory.add("turn", "user: %s\nentity: %s" % (user_text[:500], final_text[:1500]),
               session)
    return {"text": final_text, "vetoed": False, "route": "entity-" + rung,
            "capsule": capsule.get("mode", "LIMITED"),
            "limited": capsule.get("mode") != "SIGNED",
            "tools_used": tool_results}
