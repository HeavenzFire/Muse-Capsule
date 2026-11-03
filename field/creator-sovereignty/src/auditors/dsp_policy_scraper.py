#!/usr/bin/env python3
"""DSP policy snapshot auditor — HeavenzFire Creator-Sovereignty.

Purpose
-------
Fetch a list of *public* policy/terms URLs, save each fetched page as a
timestamped snapshot, and on a later run detect whether each page changed
relative to its previous snapshot. The snapshot record is the evidence:
URL, fetch time (UTC), HTTP status, and SHA-256 of the fetched body.

What this tool does NOT do
---------------------------
- No login, no credentials, no cookies, no session handling.
- No bot-check bypass, no CAPTCHA solving, no header spoofing beyond a
  plain, identifying User-Agent, and no retry around a block.
- No paywalled or login-required pages. If a fetch fails, returns a
  non-200 status, or returns a bot/block page, that URL is recorded as
  failed/blocked and NO snapshot body is saved for it. The previous
  snapshot, if any, is left untouched.
- No claim that a snapshot proves what a platform's *enforced* policy is;
  it proves only what that public URL returned at that time.

Standard library only (urllib). Runs with python3 alone.

Config file (JSON), supplied by the user
----------------------------------------
Example — save as, e.g., ``policies.json``::

    {
      "urls": [
        "https://example.com/terms",
        {"url": "https://example.com/privacy", "name": "example-privacy"}
      ]
    }

Each entry is either a URL string or an object with ``url`` and an
optional ``name`` (used only for display and file naming).

Snapshots
---------
Default output directory (relative to this repository)::

    field/creator-sovereignty/data/evidence/

Override with ``--out``. Per URL, one directory is created, named
``<slug>-<first 12 hex of sha256(url)>`` where slug is the host plus a
sanitized path. Inside it, each successful fetch writes::

    <UTC timestamp>.body      # raw fetched bytes, exactly as received
    <UTC timestamp>.json      # metadata: url, timestamp, sha256, status,
                              # http_status, bytes, content_type

Failed/blocked fetches write only a ``<UTC timestamp>.json`` metadata
record with ``status`` set to ``failed`` or ``blocked`` and no body file.

CLI
---
    python3 dsp_policy_scraper.py --config policies.json
    python3 dsp_policy_scraper.py --config policies.json --out ./evidence
    python3 dsp_policy_scraper.py --config policies.json --out ./evidence --diff

``--diff`` does not fetch anything: it compares the two most recent
successful snapshots for each configured URL in ``--out`` and prints a
summary. A normal (fetching) run also prints a summary comparing each
new snapshot against the previous successful snapshot for that URL:
``new`` (first snapshot), ``unchanged``, ``changed`` (hashes differ),
or ``failed``/``blocked``.

Exit code: 0 even when some URLs fail or change (a change is a finding,
not a script error); 2 on a usage/config error.
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "HeavenzFire-DSP-Auditor/1.0 (public-policy snapshot; no login)"
DEFAULT_TIMEOUT = 30

# Markers that indicate a bot/block page rather than the requested policy
# text. Matching any of these means: record blocked, save no body.
BOT_MARKERS = (
    "captcha",
    "verify you are human",
    "are you a robot",
    "access denied",
    "request blocked",
    "bot detection",
)


def repo_evidence_dir() -> Path:
    """Default evidence dir, relative to this repo clone.

    Script lives at field/creator-sovereignty/src/auditors/, so the repo
    root is four levels up. If that layout is not present (script copied
    elsewhere), fall back to ./data/evidence under the working directory.
    """
    here = Path(__file__).resolve()
    if len(here.parents) >= 5:
        candidate = here.parents[4] / "field" / "creator-sovereignty" / "data" / "evidence"
        if candidate.parent.parent.name == "creator-sovereignty":
            return candidate
    return Path.cwd() / "data" / "evidence"


def slug_for(url: str) -> str:
    """Filesystem-safe slug for a URL, plus a hash suffix for uniqueness."""
    host_path = re.sub(r"^https?://", "", url)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", host_path).strip("-").lower()
    slug = slug[:80] or "url"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}"


def load_config(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: cannot read config {path}: {exc}") from exc
    urls = data.get("urls") if isinstance(data, dict) else None
    if not isinstance(urls, list) or not urls:
        raise SystemExit(
            "error: config must be JSON with a non-empty \"urls\" list "
            "(strings, or objects with a \"url\" field)"
        )
    entries = []
    for item in urls:
        if isinstance(item, str):
            entries.append({"url": item, "name": None})
        elif isinstance(item, dict) and isinstance(item.get("url"), str):
            entries.append({"url": item["url"], "name": item.get("name")})
        else:
            raise SystemExit(f"error: invalid config entry (need a URL): {item!r}")
    return entries


def utc_now() -> str:
    """UTC timestamp safe for filenames, e.g. 20261102T220000123456Z.

    Microsecond precision, so two runs in the same second never share a
    snapshot filename (the first test run caught a second-resolution
    collision overwriting the previous snapshot).
    """
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def unique_base(url_dir: Path, stamp: str) -> str:
    """Filename base that does not overwrite an existing snapshot."""
    base, n = stamp, 2
    while (url_dir / f"{base}.json").exists() or (url_dir / f"{base}.body").exists():
        base, n = f"{stamp}-{n}", n + 1
    return base


def list_snapshots(url_dir: Path) -> list[dict]:
    """Successful snapshot metadata for one URL, oldest first."""
    metas = []
    if not url_dir.is_dir():
        return metas
    for meta_path in sorted(url_dir.glob("*.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if meta.get("status") == "ok" and meta.get("sha256"):
            metas.append(meta)
    metas.sort(key=lambda m: m.get("timestamp", ""))
    return metas


def write_meta(url_dir: Path, meta: dict, base: str | None = None) -> Path:
    meta_path = url_dir / f"{base or meta['timestamp']}.json"
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    return meta_path


def fetch_one(entry: dict, out_dir: Path, timeout: int) -> dict:
    """Fetch one URL once. Single attempt only — never retry around a block."""
    url = entry["url"]
    url_dir = out_dir / slug_for(url)
    url_dir.mkdir(parents=True, exist_ok=True)
    previous = list_snapshots(url_dir)
    prev_hash = previous[-1]["sha256"] if previous else None
    stamp = utc_now()
    base = unique_base(url_dir, stamp)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        # HTTPError carries the status: 403/429/503 etc. are blocks, not
        # snapshots. Record, do not retry, do not save a body.
        blocked = exc.code in (401, 403, 429, 503)
        meta = {
            "url": url, "name": entry["name"], "timestamp": stamp,
            "status": "blocked" if blocked else "failed",
            "http_status": exc.code, "error": str(exc),
            "sha256": None, "bytes": None, "content_type": None,
        }
        write_meta(url_dir, meta, base)
        return {"url": url, "name": entry["name"], "result": meta["status"],
                "http_status": exc.code, "sha256": None, "prev_sha256": prev_hash}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        meta = {
            "url": url, "name": entry["name"], "timestamp": stamp,
            "status": "failed", "http_status": None, "error": str(exc),
            "sha256": None, "bytes": None, "content_type": None,
        }
        write_meta(url_dir, meta, base)
        return {"url": url, "name": entry["name"], "result": "failed",
                "http_status": None, "sha256": None, "prev_sha256": prev_hash}

    if status != 200:
        meta = {
            "url": url, "name": entry["name"], "timestamp": stamp,
            "status": "failed", "http_status": status,
            "error": f"unexpected HTTP status {status}",
            "sha256": None, "bytes": None, "content_type": content_type,
        }
        write_meta(url_dir, meta, base)
        return {"url": url, "name": entry["name"], "result": "failed",
                "http_status": status, "sha256": None, "prev_sha256": prev_hash}

    lowered = body.lower()
    if any(marker.encode("utf-8") in lowered for marker in BOT_MARKERS):
        meta = {
            "url": url, "name": entry["name"], "timestamp": stamp,
            "status": "blocked", "http_status": status,
            "error": "body matches a bot/block page marker; no snapshot saved",
            "sha256": None, "bytes": None, "content_type": content_type,
        }
        write_meta(url_dir, meta, base)
        return {"url": url, "name": entry["name"], "result": "blocked",
                "http_status": status, "sha256": None, "prev_sha256": prev_hash}

    digest = hashlib.sha256(body).hexdigest()
    (url_dir / f"{base}.body").write_bytes(body)
    meta = {
        "url": url, "name": entry["name"], "timestamp": stamp,
        "status": "ok", "http_status": status, "error": None,
        "sha256": digest, "bytes": len(body), "content_type": content_type,
    }
    write_meta(url_dir, meta, base)
    if prev_hash is None:
        result = "new"
    elif digest == prev_hash:
        result = "unchanged"
    else:
        result = "changed"
    return {"url": url, "name": entry["name"], "result": result,
            "http_status": status, "sha256": digest, "prev_sha256": prev_hash}


def diff_only(entries: list[dict], out_dir: Path) -> list[dict]:
    """Compare the two most recent successful snapshots per URL, no fetching."""
    rows = []
    for entry in entries:
        snaps = list_snapshots(out_dir / slug_for(entry["url"]))
        if len(snaps) < 2:
            result = "new" if len(snaps) == 1 else "no_snapshot"
            rows.append({"url": entry["url"], "name": entry["name"],
                         "result": result, "http_status": None,
                         "sha256": snaps[-1]["sha256"] if snaps else None,
                         "prev_sha256": None})
        else:
            latest, prev = snaps[-1], snaps[-2]
            rows.append({"url": entry["url"], "name": entry["name"],
                         "result": ("unchanged" if latest["sha256"] == prev["sha256"]
                                    else "changed"),
                         "http_status": latest.get("http_status"),
                         "sha256": latest["sha256"],
                         "prev_sha256": prev["sha256"]})
    return rows


def print_summary(rows: list[dict]) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["result"]] = counts.get(row["result"], 0) + 1
        label = row["name"] or row["url"]
        line = f"{row['result']:>10}  {label}"
        if row.get("http_status") is not None:
            line += f"  http={row['http_status']}"
        if row.get("sha256"):
            line += f"  sha256={row['sha256'][:16]}..."
        if row["result"] == "changed":
            line += f"  prev={row['prev_sha256'][:16]}..."
        print(line)
    summary = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"summary: {summary}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Snapshot public DSP policy/terms URLs and detect changes "
                    "vs the previous snapshot. No login, no bot-check bypass.")
    parser.add_argument("--config", required=True,
                        help="JSON config file with a \"urls\" list (see docstring)")
    parser.add_argument("--out", default=None,
                        help="evidence directory (default: "
                             "field/creator-sovereignty/data/evidence/ in this repo)")
    parser.add_argument("--diff", action="store_true",
                        help="do not fetch; compare the two most recent "
                             "successful snapshots per URL in --out")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"per-request timeout in seconds (default {DEFAULT_TIMEOUT})")
    args = parser.parse_args(argv)
    entries = load_config(Path(args.config))
    out_dir = Path(args.out) if args.out else repo_evidence_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.diff:
        rows = diff_only(entries, out_dir)
    else:
        rows = [fetch_one(entry, out_dir, args.timeout) for entry in entries]
    print_summary(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
