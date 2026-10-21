"""Web worker: independent web access. No Big Tech API keys, no accounts.

Search backends, in order:
  1. SearXNG (self-hosted metasearch) -- SEARXNG_URL, default
     http://localhost:8888. This is the independent path: your own
     search engine, aggregating other engines, no API keys.
  2. DuckDuckGo lite HTML -- keyless, works from residential IPs.
  3. Wikipedia API -- keyless JSON, Wikipedia-scoped but reliable.

Fetch: plain HTTP with SSRF guard, no API.
"""
import html
import os
import re
import urllib.parse
import urllib.request

CAPABILITIES = ["web.search", "web.fetch"]

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888").rstrip("/")


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _searxng(query):
    """Self-hosted SearXNG metasearch. No API key. Returns [] when the
    instance is not running -- caller falls through to the next backend."""
    import json
    url = (SEARXNG_URL + "/search?q=" + urllib.parse.quote(query)
           + "&format=json&language=en")
    try:
        data = json.loads(_get(url, timeout=10))
    except Exception:
        return []
    out = []
    for hit in data.get("results", [])[:10]:
        title = hit.get("title", "") or ""
        href = hit.get("url", "") or ""
        if href.startswith("http"):
            out.append({"title": title[:200], "url": href[:500],
                        "snippet": (hit.get("content", "") or "")[:300]})
    return out


def _ddg_lite(query):
    """DuckDuckGo lite endpoint. Works from residential IPs; datacenters
    often get soft-blocked (empty results) - caller falls back."""
    import urllib.parse
    url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query)
    page = _get(url)
    results = []
    for m in re.finditer(
            r'<a[^>]*rel="nofollow"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            page, re.S):
        href = m.group(1)
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        if "duckduckgo.com" in href or not href.startswith("http"):
            continue
        # DDG wraps outbound links in a redirect; unwrap
        um = re.search(r"[?&]uddg=([^&]+)", href)
        if um:
            href = urllib.parse.unquote(um.group(1))
        if href.startswith("http"):
            results.append({"title": title[:200], "url": href[:500]})
        if len(results) >= 10:
            break
    return results


def _wikipedia(query):
    """Keyless JSON API. Reliable everywhere; Wikipedia-scoped."""
    import json
    import urllib.parse
    url = ("https://en.wikipedia.org/w/api.php?action=query&list=search"
           "&srsearch=" + urllib.parse.quote(query) +
           "&format=json&srlimit=10")
    req = urllib.request.Request(url, headers={"User-Agent": "HeavenzFire/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for hit in data.get("query", {}).get("search", []):
        title = hit.get("title", "")
        url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(
            title.replace(" ", "_"))
        snippet = html.unescape(re.sub(r"<[^>]+>", "", hit.get("snippet", "")))
        out.append({"title": title[:200], "url": url[:500],
                    "snippet": snippet[:300]})
    return out


def run(task, signal):
    args = task.get("args", {})
    op = task.get("capability")
    if op == "web.search":
        q = args.get("query", "")
        if not q.strip():
            return {"ok": False, "error": "empty query"}
        provider, results = "none", []
        try:
            results = _searxng(q)
            if results:
                provider = "searxng"
        except Exception:  # noqa: BLE001 - fall through to next provider
            pass
        if not results:
            try:
                results = _ddg_lite(q)
                if results:
                    provider = "duckduckgo"
            except Exception:  # noqa: BLE001 - fall through to next provider
                pass
        if not results:
            try:
                results = _wikipedia(q)
                if results:
                    provider = "wikipedia"
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": "search failed: %s" % e}
        return {"ok": True, "query": q, "provider": provider,
                "results": results}
    if op == "web.fetch":
        url = args.get("url", "")
        if not (url.startswith("http://") or url.startswith("https://")):
            return {"ok": False, "error": "only http(s) URLs"}
        try:
            page = _get(url)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "fetch failed: %s" % e}
        text = re.sub(r"<script.*?</script>", " ", page, flags=re.S | re.I)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return {"ok": True, "url": url, "text": text[:8000]}
    return {"ok": False, "error": "unknown op"}
