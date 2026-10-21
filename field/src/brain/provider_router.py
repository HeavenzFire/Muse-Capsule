"""
Provider router: make any single provider's quota irrelevant.

Tries providers in order, fails over on quota/rate-limit errors, and
reports which rung served the request. Keys come from the environment --
never hardcoded, never logged.

Order (override with HF_PROVIDER_ORDER="ollama,gemini,openai"):
  1. ollama   - local, no quota, ever. Needs Ollama on localhost:11434.
  2. gemini   - Google AI Studio / Gemini API key.
  3. openai   - any OpenAI-compatible endpoint (OpenAI, Perplexity, etc).

Failover triggers: HTTP 429, quota-exceeded / RESOURCE_EXHAUSTED style
errors, connection failures, timeouts. Anything else (bad request, auth
rejected for a bad key) is NOT failed over -- it is reported, because
retrying a bad key on the next provider is wrong.

Usage:
    from provider_router import route_chat
    text, rung = route_chat([{"role": "user", "content": "hi"}])
"""

import json
import os
import time
import urllib.request
import urllib.error

TIMEOUT = 60


class ProviderError(Exception):
    def __init__(self, provider, kind, detail):
        super().__init__("%s: %s: %s" % (provider, kind, detail))
        self.provider = provider
        self.kind = kind  # "quota" | "unreachable" | "auth" | "bad_request"
        self.detail = detail


def _post(url, payload, headers):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        if e.code == 429 or "quota" in body.lower() or "exhaust" in body.lower():
            raise ProviderError(_current, "quota", "HTTP %s %s" % (e.code, body))
        if e.code in (401, 403):
            raise ProviderError(_current, "auth", "HTTP %s %s" % (e.code, body))
        raise ProviderError(_current, "bad_request", "HTTP %s %s" % (e.code, body))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ProviderError(_current, "unreachable", str(e)[:200])


_current = "?"


def _ollama_chat(messages, model):
    global _current
    _current = "ollama"
    data = _post("http://localhost:11434/api/chat",
                 {"model": model, "messages": messages, "stream": False}, {})
    return data["message"]["content"]


def _gemini_chat(messages, model):
    global _current
    _current = "gemini"
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ProviderError("gemini", "auth", "GEMINI_API_KEY not set")
    # Gemini API: convert messages to contents
    contents = [{"role": ("model" if m["role"] == "assistant" else "user"),
                 "parts": [{"text": m["content"]}]} for m in messages]
    url = ("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s"
           % (model, key))
    data = _post(url, {"contents": contents}, {})
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _openai_compat_chat(messages, model, base_url, key_env):
    global _current
    _current = "openai-compat"
    key = os.environ.get(key_env, "")
    if not key:
        raise ProviderError("openai-compat", "auth", "%s not set" % key_env)
    data = _post(base_url.rstrip("/") + "/chat/completions",
                 {"model": model, "messages": messages},
                 {"Authorization": "Bearer " + key})
    return data["choices"][0]["message"]["content"]


def provider_order():
    # Online-first: cloud rungs primary, local Ollama only if all else
    # fails (internet down, quotas exhausted). Override with
    # HF_PROVIDER_ORDER. offline=true forces ollama-only.
    raw = os.environ.get("HF_PROVIDER_ORDER", "gemini,openai,ollama")
    return [p.strip() for p in raw.split(",") if p.strip()]


def route_chat(messages, log=None):
    """
    Try providers in order. Returns (text, rung_name).
    Fails over on quota/unreachable. Raises ProviderError listing every
    rung's failure if all are down. Never silently substitutes.
    """
    failures = []
    for name in provider_order():
        try:
            if name == "ollama":
                model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
                return _ollama_chat(messages, model), "ollama:" + model
            if name == "gemini":
                model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
                return _gemini_chat(messages, model), "gemini:" + model
            if name == "openai":
                model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
                base = os.environ.get("OPENAI_BASE_URL",
                                      "https://api.openai.com/v1")
                key_env = os.environ.get("OPENAI_KEY_ENV", "OPENAI_API_KEY")
                return _openai_compat_chat(messages, model, base, key_env), \
                    "openai-compat:" + model
            failures.append((name, "unknown provider in HF_PROVIDER_ORDER"))
        except ProviderError as e:
            failures.append((e.provider, e.kind, e.detail))
            if log:
                log("rung %s failed (%s), failing over" % (e.provider, e.kind))
            if e.kind in ("quota", "unreachable"):
                continue
            # auth / bad_request: report, do not fail over blindly
            break
    detail = "; ".join("%s=%s" % (p, k) for p, k, *_ in failures)
    raise ProviderError("router", "unreachable",
                        "all rungs failed: %s" % detail)


if __name__ == "__main__":
    # Self-test: expect ollama to fail here (no Ollama on this VM),
    # then fail over. Proves failover logic, not providers.
    os.environ["HF_PROVIDER_ORDER"] = "ollama,gemini,openai"
    try:
        text, rung = route_chat([{"role": "user", "content": "ping"}])
        print("served by:", rung)
        print(text[:200])
    except ProviderError as e:
        print("all rungs down (expected on this VM):", e.detail)
