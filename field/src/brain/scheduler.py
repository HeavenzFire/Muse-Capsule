"""Scheduler: background triggers for the Prime brain.

tasks.json format:
  [{"name": "morning-brief", "interval_s": 86400, "prompt": "...",
    "session": "default", "agent": {...}}]

The scheduler thread wakes every 30s, runs due tasks through the entity
loop, and records each run in the audit log. Tasks survive restarts
(tasks.json is the source of truth); per-task last_run is kept in
tasks.state.json.
"""
import json
import os
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE = os.path.join(BASE, "tasks.json")
STATE_FILE = os.path.join(BASE, "tasks.state.json")


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def run_scheduler(kernel, memory, get_capsule, stop_event):
    """Entry point for the scheduler thread. Never raises."""
    import entity
    while not stop_event.is_set():
        try:
            tasks = _load_json(TASKS_FILE, [])
            state = _load_json(STATE_FILE, {})
            now = time.time()
            changed = False
            for t in tasks:
                name = t.get("name", "unnamed")
                interval = max(60, int(t.get("interval_s", 3600)))
                last = state.get(name, 0)
                if now - last < interval:
                    continue
                try:
                    out = entity.run_turn(
                        t.get("prompt", ""), kernel, memory, get_capsule(),
                        session=t.get("session", "scheduler"),
                        tools_allowed=(t.get("agent") or {}).get("tools_allowed"),
                        offline=bool(t.get("offline", False)))
                    kernel.log.append("scheduled_task", task_id=name,
                                      result="ok", route=out.get("route"))
                except Exception as e:  # noqa: BLE001 - a task failure
                    kernel.log.append("scheduled_task", task_id=name,  # is data
                                      result="error: %s" % e)
                state[name] = now
                changed = True
            if changed:
                _save_json(STATE_FILE, state)
        except Exception:  # noqa: BLE001 - scheduler never dies
            pass
        stop_event.wait(30)


def start(kernel, memory, get_capsule):
    stop = threading.Event()
    th = threading.Thread(target=run_scheduler,
                          args=(kernel, memory, get_capsule, stop),
                          daemon=True, name="scheduler")
    th.start()
    # ensure tasks.json exists
    if not os.path.isfile(TASKS_FILE):
        _save_json(TASKS_FILE, [])
    return stop
