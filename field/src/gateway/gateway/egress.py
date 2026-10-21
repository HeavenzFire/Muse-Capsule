"""Sanctioned egress: the ONLY path from our stack to the web.

Two uses:
  1. Inside gateway.py: implements POST /egress/fetch, /egress/search,
     /egress/relay behind the allow-list.
  2. As a shim for subsystem workers: `from egress import fetch` routes
     through the gateway when SOVEREIGN_GATEWAY is set
     (http://127.0.0.1:18080 + SOVEREIGN_GATEWAY_KEY), otherwise enforces
     the same allow-list locally. Workers stop calling urllib directly;
     they call this. Migration path documented in DECOUPLE.md.

Default-deny: anything not allow-listed is refused AND logged.
"""
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from . import allowlist

TIMEOUT = 20


def _extra_domains():
    gitea_url = os.environ.get("GITEA_URL", "")
    e = allowlist.gitea_entry(gitea_url)
    return [e] if e else []


def permitted(url, capability):
    """(allowed, entry, reason) for a URL + capability."""
    host = (urllib.parse.urlparse(url).hostname or "")
    ok, entry, reason = allowlist.check(host, capability, _extra_domains())
    if not ok:
        return False, entry, reason
    ok2, reason2 = allowlist.ssrf_guard(url)
    if not ok2:
        return False, entry, "ssrf guard: " + reason2
    return True, entry, reason


def _raw_get(url, headers=None, timeout=TIMEOUT):
    req = urllib.request.Request(
        url, headers={"User-Agent": "HeavenzFire-Sovereign/1.0",
                      **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def fetch(url, capability="web.fetch"):
    """Fetch a URL's text. Returns dict (never raises on refusal)."""
    ok, entry, reason = permitted(url, capability)
    if not ok:
        return {"ok": False, "error": "egress denied: " + reason,
                "verdict": "DENIED"}
    try:
        status, raw = _raw_get(url)
        page = raw.decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "fetch failed: %s: %s"
                % (type(e).__name__, e), "verdict": "ERROR"}
    text = re.sub(r"<script.*?</script>", " ", page, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return {"ok": True, "url": url, "status": status,
            "text": text[:8000], "via": entry["domain"],
            "verdict": "ALLOWED"}


def search(query, capability="web.search"):
    """Web search: SearXNG (ours) first, then allow-listed fallbacks."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "verdict": "DENIED"}
    # 1. SearXNG: our own metasearch, loopback, always permitted.
    searx = os.environ.get("SEARXNG_URL", "http://localhost:8888").rstrip("/")
    try:
        status, raw = _raw_get(searx + "/search?q="
                               + urllib.parse.quote(q)
                               + "&format=json&language=en", timeout=10)
        out = []
        for hit in json.loads(raw.decode("utf-8",
                                         "replace")).get("results", [])[:10]:
            href = hit.get("url", "") or ""
            if href.startswith("http"):
                out.append({"title": (hit.get("title", "") or "")[:200],
                            "url": href[:500],
                            "snippet": (hit.get("content", "")
                                        or "")[:300]})
        if out:
            return {"ok": True, "query": q, "provider": "searxng",
                    "results": out, "verdict": "ALLOWED"}
    except Exception:  # noqa: BLE001
        pass
    # 2. Wikipedia: allow-listed, keyless.
    wiki = ("https://en.wikipedia.org/w/api.php?action=query&list=search"
            "&srsearch=" + urllib.parse.quote(q) + "&format=json&srlimit=10")
    ok, entry, reason = permitted(wiki, capability)
    if not ok:
        return {"ok": False, "error": "egress denied: " + reason,
                "verdict": "DENIED"}
    try:
        status, raw = _raw_get(wiki)
        out = []
        for hit in json.loads(raw.decode("utf-8")).get("query",
                                                       {}).get("search", []):
            title = hit.get("title", "")
            url = ("https://en.wikipedia.org/wiki/"
                   + urllib.parse.quote(title.replace(" ", "_")))
            snippet = html.unescape(re.sub(r"<[^>]+>", "",
                                           hit.get("snippet", "")))
            out.append({"title": title[:200], "url": url[:500],
                        "snippet": snippet[:300]})
        return {"ok": True, "query": q, "provider": "wikipedia",
                "results": out, "verdict": "ALLOWED"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "search failed: %s" % e,
                "verdict": "ERROR"}


def relay(host, method, path, query="", body=b"", headers=None,
          capability="forge.repo.sync"):
    """Generic allow-listed API relay (GitHub REST, Gitea REST...).

    Returns (status, body_bytes, verdict). Never raises on refusal.
    """
    ok, entry, reason = allowlist.check(host, capability, _extra_domains())
    if not ok:
        return 403, b'{"ok":false,"error":"egress denied: %s"}' \
            % reason.encode(), "DENIED"
    scheme = "http" if host in ("127.0.0.1", "localhost", "::1") \
        else "https"
    url = "%s://%s%s%s" % (scheme, host, path,
                           ("?" + query) if query else "")
    ok2, reason2 = allowlist.ssrf_guard(url)
    if not ok2:
        return 403, b'{"ok":false,"error":"ssrf guard"}', "DENIED"
    try:
        req = urllib.request.Request(url, data=body or None,
                                     headers=headers or {},
                                     method=method.upper())
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read(), "ALLOWED"
    except urllib.error.HTTPError as e:
        return e.code, e.read(), "ALLOWED"
    except Exception as e:  # noqa: BLE001
        return 502, ('{"ok":false,"error":"relay failed: %s"}'
                     % e).encode(), "ERROR"


# --- worker shim: route through the gateway when configured -------------
def via_gateway():
    base = os.environ.get("SOVEREIGN_GATEWAY", "").rstrip("/")
    key = os.environ.get("SOVEREIGN_GATEWAY_KEY", "")
    return (base, key) if base and key else (None, None)


def gateway_post(path, payload):
    """POST to the gateway's egress endpoints. For worker migration."""
    base, key = via_gateway()
    if not base:
        return None
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        base + path, data=data,
        headers={"Content-Type": "application/json",
                 "X-Gateway-Key": key})
    with urllib.request.urlopen(req, timeout=TIMEOUT + 10) as r:
        return json.loads(r.read().decode("utf-8"))
