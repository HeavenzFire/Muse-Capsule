"""Capsule verify worker: chain-of-custody for the shared mind.

Read-only. Hashes the canonical capsule seeds and their GitHub
instantiation copies and reports whether they agree, file by file,
plus the latest commit in the snapshot sync record. A mismatch is
reported, never repaired silently. Grown 2026-10-21 under the
grow-test-release protocol.
"""
import hashlib
import json
import os

CAPABILITIES = ["capsule.verify"]

HOME = os.path.expanduser("~")
# Anchor to this file's tree (workers/ -> prime-brain-build/ -> workspace/)
# so the worker reports the same truth no matter which process or user
# runs it; $HOME alone lies under systemd (root) vs a user shell.
_HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.environ.get(
    "HF_WORKSPACE", os.path.dirname(os.path.dirname(_HERE)))
CANONICAL = os.path.join(WORKSPACE,
                         "your_files/heavenzfire-capsule/capsule-seed")
REPO = os.path.join(WORKSPACE, "github-instantiation/muse-capsule/capsule")
SYNC = os.path.join(WORKSPACE, "github-instantiation/"
                              "muse-capsule.muse-github-snapshot-sync.json")
FILES = ["soul.md", "standing-orders.md", "memory.md"]


def _sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def run(task, signal):
    files = {}
    all_match = True
    for name in FILES:
        a = _sha(os.path.join(CANONICAL, name))
        b = _sha(os.path.join(REPO, name))
        match = a is not None and a == b
        all_match = all_match and match
        files[name] = {"canonical_sha256": a, "repo_sha256": b,
                       "match": match}
    head = None
    try:
        with open(SYNC) as f:
            entries = json.load(f)
        if entries:
            head = entries[-1].get("commit_sha")
    except Exception:  # noqa: BLE001 - a missing record is a finding
        head = None
    return {"ok": True, "all_match": all_match, "files": files,
            "sync_head_commit": head}
