"""Provider adapters for HeavenzFire's model federation.

No provider is contacted until the agent makes a chat call. Credentials are
read from environment variables and are never intentionally logged.
"""
import json
import os
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    """A configured model provider could not complete a request."""


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
        payload = {"model": selected_model, "messages": messages,
                   "temperature": temperature, "stream": False}
        url = base + "/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
    else:
        raise ProviderError("Unsupported provider %r; supported: ollama, deepseek, openai-compatible" % name)
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Do not include response bodies: providers can echo sensitive request details.
        raise ProviderError("Provider %s returned HTTP %s" % (name, exc.code))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError("Provider %s request failed: %s" % (name, type(exc).__name__))
    if name == "ollama":
        text = (data.get("message") or {}).get("content", "")
    else:
        choices = data.get("choices") or []
        text = ((choices[0].get("message") or {}).get("content", "")
                if choices else "")
    if not isinstance(text, str) or not text.strip():
        raise ProviderError("Provider %s returned no assistant text" % name)
    return text
