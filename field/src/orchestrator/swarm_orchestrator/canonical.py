"""Canonical JSON + task IDs.

Identical function to prime-brain-build/kernel.py and the mesh transport:
sha256 of canonical JSON. One ID function for the whole orchestrated flow —
a task entering via any subsystem carries the same ID everywhere.
"""
import hashlib
import json


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def make_task_id(task: dict) -> str:
    """Deterministic 16-hex task ID from capability + args.

    Matches kernel.make_task_id exactly: same task -> same ID in PRIME,
    in the mesh (task_id_of(spec) uses the same construction), and here.
    """
    core = {"capability": task.get("capability"), "args": task.get("args", {})}
    return sha256_hex(canonical(core).encode("utf-8"))[:16]
