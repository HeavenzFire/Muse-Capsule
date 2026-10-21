"""Deterministic scheduling: same inputs -> same dispatch order.

Ordering rule (no wall-clock, no thread timing inside the order):
  1. priority band (task["priority"], default 0; lower runs first)
  2. canonical task_id (lexicographic)

A batch submitted together always dispatches in this order, on every
machine, every run. Replay: feed the same task list, get the same order.
The seeded PRNG (mulberry32, same construction as the PRIME kernel) is
available for explicitly-randomized policies, but the DEFAULT order is
fully deterministic with no randomness at all.
"""
from .canonical import make_task_id, sha256_hex


def mulberry32(seed: int):
    a = seed & 0xFFFFFFFF

    def rand():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        step = ((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF
        t = (((t + step) & 0xFFFFFFFF) ^ t) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return rand


def order(tasks):
    """Deterministic dispatch order for a batch of task dicts."""
    keyed = []
    for t in tasks:
        tid = t.get("task_id") or make_task_id(t)
        keyed.append((t.get("priority", 0), tid, t))
    keyed.sort(key=lambda k: (k[0], k[1]))
    return [t for _, _, t in keyed]


def replay_digest(tasks):
    """One hash pinning a batch's dispatch order. Same tasks -> same digest."""
    ordered = order(tasks)
    ids = [t.get("task_id") or make_task_id(t) for t in ordered]
    return sha256_hex(",".join(ids).encode("utf-8"))
