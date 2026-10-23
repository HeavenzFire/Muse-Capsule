"""Provider adapters for HeavenzFire's model federation.

No provider is contacted until the agent makes a chat call. Credentials are
read from environment variables and are never intentionally logged.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


class ProviderError(RuntimeError):
    """A configured model provider could not complete a request."""


def _is_loopback_url(url):
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def _origin(url):
    parts = urllib.parse.urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        port = None
    if port is None:
        port = 443 if parts.scheme.lower() == "https" else 80
    return (parts.scheme.lower(), (parts.hostname or "").lower(), port)


def _validate_base_url(base, name):
    """Provider base URLs must be https://; http:// is allowed only for
    loopback hosts (e.g. local Ollama on 127.0.0.1)."""
    try:
        scheme = urllib.parse.urlsplit(base).scheme.lower()
    except ValueError:
        scheme = ""
    if scheme == "https" or _is_loopback_url(base):
        return
    raise ProviderError(
        "Provider %s base URL must use https:// (got %r); http:// is "
        "allowed only for loopback hosts (127.0.0.1/localhost)" % (name, base))


_EXTERNAL_NOTICE_SHOWN = False


def _require_external_opt_in(name, base):
    """External (non-loopback) endpoints receive the capsule (soul, standing
    orders, memory) and the run's tool transcript. That external transmission
    requires an explicit per-run opt-in: HF_ALLOW_EXTERNAL=1 set for this
    run, or the agent CLI's --allow-external-provider flag (which sets it).
    A provider merely being configured is not consent for each run.
    Loopback endpoints are local and unaffected."""
    global _EXTERNAL_NOTICE_SHOWN
    if _is_loopback_url(base):
        return
    if os.environ.get("HF_ALLOW_EXTERNAL", "") != "1":
        raise ProviderError(
            "Provider %s endpoint %s is external (non-loopback) and would "
            "receive the capsule and tool transcript. Refusing without a "
            "per-run opt-in: set HF_ALLOW_EXTERNAL=1 or pass "
            "--allow-external-provider for this run." % (name, base))
    if not _EXTERNAL_NOTICE_SHOWN:
        _EXTERNAL_NOTICE_SHOWN = True
        print("notice: sending capsule context and tool transcript to "
              "external provider %s at %s; provider-side retention is "
              "governed by that provider's terms." % (name, base),
              file=sys.stderr)


class _StripCrossHostAuth(urllib.request.HTTPRedirectHandler):
    """Follow redirects, but never forward the Authorization header to a
    different origin (scheme/host/port) than the original request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and _origin(req.full_url) != _origin(newurl):
            for mapping in (new.headers, new.unredirected_hdrs):
                for key in [k for k in mapping if k.lower() == "authorization"]:
                    del mapping[key]
        return new


_OPENER = urllib.request.build_opener(_StripCrossHostAuth())


def _open(request, timeout):
    """Single transport seam (tests patch this). Goes through an opener
    whose redirect handler strips Authorization on cross-origin redirects."""
    return _OPENER.open(request, timeout=timeout)


def provider_status(provider=None):
    name = (provider or os.environ.get("HF_AGENT_PROVIDER", "ollama")).strip().lower()
    if name == "ollama":
        return {
            "provider": name,
            "status": "CONFIGURED_LOCAL",
            "endpoint": os.environ.get("HF_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            "credential_present": False,
        }
    if name in ("deepseek", "openai-compatible"):
        key_name = "DEEPSEEK_API_KEY" if name == "deepseek" else "HF_OPENAI_COMPATIBLE_API_KEY"
        endpoint_default = "https://api.deepseek.com" if name == "deepseek" else ""
        endpoint = os.environ.get("HF_AGENT_BASE_URL", endpoint_default).rstrip("/")
        key_present = bool(os.environ.get(key_name))
        return {
            "provider": name,
            "status": "AUTH_CONFIGURED" if key_present and endpoint else
                      "AUTH_REQUIRED" if endpoint else "NOT_CONFIGURED",
            "endpoint_configured": bool(endpoint),
            "credential_present": key_present,
            "credential_env": key_name,
        }
    return {"provider": name, "status": "UNSUPPORTED_PROVIDER",
            "credential_present": False}


def provider_chat(messages, provider=None, model=None, temperature=0.3,
                  num_ctx=8192, timeout=120):
    """Return assistant text from Ollama or an OpenAI-compatible endpoint."""
    name = (provider or os.environ.get("HF_AGENT_PROVIDER", "ollama")).strip().lower()
    selected_model = model or os.environ.get("HF_AGENT_MODEL", "heavenzfire")
    if name == "ollama":
        base = os.environ.get("HF_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        _validate_base_url(base, name)
        _require_external_opt_in(name, base)
        payload = {"model": selected_model, "messages": messages, "stream": False,
                   "options": {"temperature": temperature, "num_ctx": num_ctx}}
        url = base + "/api/chat"
        headers = {"Content-Type": "application/json"}
    elif name in ("deepseek", "openai-compatible"):
        key_env = "DEEPSEEK_API_KEY" if name == "deepseek" else "HF_OPENAI_COMPATIBLE_API_KEY"
        key = os.environ.get(key_env, "")
        base_default = "https://api.deepseek.com" if name == "deepseek" else ""
        base = os.environ.get("HF_AGENT_BASE_URL", base_default).rstrip("/")
        if not base:
            raise ProviderError("No base URL configured for provider %s" % name)
        if not key:
            raise ProviderError("Provider %s requires environment variable %s" % (name, key_env))
        _validate_base_url(base, name)
        _require_external_opt_in(name, base)
        payload = {"model": selected_model, "messages": messages,
                   "temperature": temperature, "stream": False}
        url = base + "/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
    else:
        raise ProviderError("Unsupported provider %r; supported: ollama, deepseek, openai-compatible" % name)
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
    try:
        with _open(request, timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # Do not include response bodies: providers can echo sensitive request details.
        raise ProviderError("Provider %s returned HTTP %s" % (name, exc.code))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError("Provider %s request failed: %s" % (name, type(exc).__name__))
    try:
        data = json.loads(raw.decode("utf-8"))
        if name == "ollama":
            text = (data.get("message") or {}).get("content", "")
        else:
            choices = data.get("choices") or []
            text = ((choices[0].get("message") or {}).get("content", "")
                    if choices else "")
    except (ValueError, TypeError, AttributeError, KeyError, IndexError) as exc:
        # Malformed JSON, undecodable bytes, or an unexpected response shape
        # surface as one clean provider error, not a stray exception type.
        raise ProviderError("Provider %s returned a malformed response: %s"
                            % (name, type(exc).__name__))
    if not isinstance(text, str) or not text.strip():
        raise ProviderError("Provider %s returned no assistant text" % name)
    return text
