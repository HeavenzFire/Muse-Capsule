"""Sovereign gateway keystore: API keys WE mint, on his machine.

Key format:  sgw-<32 hex chars>          (16 bytes of entropy)
Key id:      first 12 hex chars of sha256(salt + key)
Scopes:      phone | laptop | witness    (laptop also administers keys)

Storage (data/keys.json):
  {"salt": hex, "keys": {key_id: {"scope","created","label","hash"}},
   "revoked": [key_id, ...]}

Only hashes are stored. The raw key is shown ONCE at mint time and
never again. Revocation is append-only: a revoked id stays listed.
"""
import hashlib
import json
import os
import secrets
import time

KEY_PREFIX = "sgw-"
DATA_DIR_ENV = "SOVEREIGN_GATEWAY_DATA"


def data_dir():
    d = os.environ.get(DATA_DIR_ENV,
                       os.path.join(os.path.dirname(
                           os.path.abspath(__file__)), "..", "data"))
    os.makedirs(d, exist_ok=True)
    return d


def _path():
    return os.path.join(data_dir(), "keys.json")


def _load():
    p = _path()
    if not os.path.isfile(p):
        return {"salt": secrets.token_hex(16), "keys": {}, "revoked": []}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(store):
    p = _path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, sort_keys=True)
    os.replace(tmp, p)


def _hash(salt, key):
    return hashlib.sha256((salt + key).encode("utf-8")).hexdigest()


def _key_id(salt, key):
    return _hash(salt, key)[:12]


def mint(scope, label=""):
    """Mint one key. Returns (key_id, raw_key). Raw key shown once."""
    if scope not in ("phone", "laptop", "witness"):
        raise ValueError("bad scope: %r" % scope)
    store = _load()
    raw = KEY_PREFIX + secrets.token_hex(16)
    kid = _key_id(store["salt"], raw)
    store["keys"][kid] = {
        "scope": scope,
        "created": int(time.time()),
        "label": label,
        "hash": _hash(store["salt"], raw),
    }
    _save(store)
    return kid, raw


def verify(raw):
    """Returns (key_id, scope) or (None, None). Revoked keys fail."""
    if not raw or not raw.startswith(KEY_PREFIX):
        return None, None
    store = _load()
    kid = _key_id(store["salt"], raw)
    rec = store["keys"].get(kid)
    if not rec:
        return None, None
    if kid in store.get("revoked", []):
        return None, None
    if rec["hash"] != _hash(store["salt"], raw):
        return None, None
    return kid, rec["scope"]


def revoke(key_id):
    store = _load()
    if key_id not in store["keys"]:
        return False
    if key_id not in store["revoked"]:
        store["revoked"].append(key_id)
        _save(store)
    return True


def list_keys():
    """Public view: no hashes, no raw keys."""
    store = _load()
    return [{"key_id": k, "scope": v["scope"], "created": v["created"],
             "label": v.get("label", ""),
             "revoked": k in store.get("revoked", [])}
            for k, v in store["keys"].items()]


def ensure_bootstrap():
    """First run: mint the three client keys. Returns {scope: (id, raw)}
    only when it actually minted; {} when keys already exist."""
    store = _load()
    scopes_present = {v["scope"] for v in store["keys"].values()}
    if {"phone", "laptop", "witness"} <= scopes_present:
        return {}
    out = {}
    for scope in ("phone", "laptop", "witness"):
        if scope not in scopes_present:
            kid, raw = mint(scope, "bootstrap")
            out[scope] = (kid, raw)
    return out
