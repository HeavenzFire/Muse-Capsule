"""Egress allow-list: default-deny. Nothing leaves except what's declared.

Each entry: {"domain", "purpose", "capabilities"[], "note"}.
A request is allowed only when:
  1. the target host matches a listed domain (exact or subdomain), AND
  2. the requesting capability is in that entry's capability list.

Loopback (127.0.0.1, ::1, localhost) is always allowed: those are OUR
services (Ollama, SearXNG), not the web. Private LAN ranges are allowed
only for the forge entries whose URL the owner configured (his Gitea).

This is the same list documented in DECOUPLE.md. Change one, change both.
"""
import ipaddress
import os
import socket
import urllib.parse

# --- the declared list -------------------------------------------------
ALLOW = [
    {"domain": "en.wikipedia.org",
     "purpose": "research search/fetch, keyless",
     "capabilities": ["web.search", "web.fetch"],
     "note": "GATEWAYED: no key, reliable, logged"},
    {"domain": "lite.duckduckgo.com",
     "purpose": "keyless search fallback when SearXNG is down",
     "capabilities": ["web.search"],
     "note": "GATEWAYED: no key, residential-IP friendly, logged"},
    {"domain": "api.github.com",
     "purpose": "forge MIRROR only: issue read/create",
     "capabilities": ["forge.issue.create", "forge.issue.list",
                      "forge.repo.check"],
     "note": "GATEWAYED: mirror direction only; Gitea is source of truth"},
    {"domain": "github.com",
     "purpose": "forge MIRROR only: git push/pull",
     "capabilities": ["forge.repo.sync", "forge.repo.check"],
     "note": "GATEWAYED: mirror direction only"},
    {"domain": "generativelanguage.googleapis.com",
     "purpose": "frontier model rung (Seer vision, spare chat)",
     "capabilities": ["seer.vision", "model.chat"],
     "note": "GATEWAYED: local 7B cannot match frontier quality yet; "
              "logged per-call; replace when a local vision model lands"},
    {"domain": "api.openai.com",
     "purpose": "OpenAI-compatible spare model rung",
     "capabilities": ["model.chat"],
     "note": "GATEWAYED: only when HE configures a key; skipped otherwise"},
]

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _is_loopback(host):
    return host.lower() in _LOOPBACK


def _domain_match(host, domain):
    host, domain = host.lower(), domain.lower()
    return host == domain or host.endswith("." + domain)


def check(host, capability, extra_domains=()):
    """Returns (allowed: bool, entry|None, reason: str)."""
    host = (host or "").lower()
    # strip an explicit port: "example.com:8080" -> "example.com"
    if host.count(":") == 1:
        host = host.split(":")[0]
    elif host.startswith("["):
        host = host.split("]")[0].lstrip("[")
    if _is_loopback(host):
        return True, {"domain": host, "purpose": "our own services",
                      "capabilities": ["*"],
                      "note": "SOVEREIGN: loopback is not the web"}, "loopback"
    for e in list(ALLOW) + list(extra_domains):
        if _domain_match(host, e["domain"]):
            if capability in e["capabilities"] or "*" in e["capabilities"]:
                return True, e, "allow-listed"
            return (False, e,
                    "domain allow-listed but capability %r is not "
                    "declared for it" % capability)
    return False, None, "default-deny: %s is not on the allow-list" % host


def ssrf_guard(url):
    """Refuse URLs that smuggle private targets behind public names.

    Allows http(s) only. Resolves the host; refuses loopback, private,
    link-local and multicast IPs UNLESS the host was literally a
    loopback name (those are ours). Returns (ok, reason).
    """
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return False, "unparseable URL"
    if p.scheme not in ("http", "https"):
        return False, "only http(s)"
    host = p.hostname or ""
    if _is_loopback(host):
        return True, "loopback"
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False, "DNS failed"
    for _fam, _typ, _proto, _canon, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return False, "bad resolved address"
        if (ip.is_loopback or ip.is_private or ip.is_link_local
                or ip.is_multicast or ip.is_reserved):
            return False, "resolves to non-public IP %s" % ip
    return True, "public"


def gitea_entry(gitea_url):
    """Build the allow-list entry for HIS Gitea from his configured URL.
    His server, his rules: full forge capabilities, LAN or public."""
    if not gitea_url:
        return None
    host = (urllib.parse.urlparse(gitea_url).hostname or "").strip().lower()
    if not host:
        return None
    return {"domain": host,
            "purpose": "sovereign source of truth: git + API",
            "capabilities": ["forge.repo.sync", "forge.repo.check",
                             "forge.issue.create", "forge.issue.list"],
            "note": "SOVEREIGN: his own server"}
