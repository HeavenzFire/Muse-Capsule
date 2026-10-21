# FINISH ON THE DESKTOP — the Unified Field on Zachary's machine

The field is verified live on the VM proving ground (see FIELD-STATE.md).
This is the sequence that brings the same field up on the desktop (ASUS).
Every step ends with a check; a failed check stops the sequence — that's
the design, not a failure of nerve.

## 0. What you need in hand

- The unified download (`heavenzfire-unified.zip`) — the stack installer.
- This repo, cloned or downloaded: the `field/` folder carries tonight's
  repairs, which the zip predates.

## 1. Install the stack

Extract the zip, run `.\Start-Here.ps1`. Five stages, each tested before
the next: stack, soul, capsule, field, release staging.

## 2. Drop in the execution-path repair

Copy `field/brain/server.py` over the installed brain's `server.py`
(`C:\sixteen\brain\server.py`). This is the repair that lets tasks
execute without a model rung: `POST /task` dispatches straight to the
kernel's workers (diag, fs, notes, capsule, shell — gates unchanged).

## 3. Give the brain its local mind

If stage 2 of Start-Here didn't already build it:
`ollama create heavenzfire -f Modelfile` (Modelfile is in this repo's
root). With Ollama up on the desktop, the brain leaves LIMITED mode —
the router has a real rung, and the model carries the soul.

## 4. Boot the field

Run `Enter-UnifiedField.ps1` (from the unified download): Ollama ->
brain -> node -> orchestrator-data services -> gateway, in manifest
order. Then start the orchestrator face:
`.\field\Run-Orchestrator.ps1` (from this repo's field folder).

## 5. The birth certificate — five checks + one task

- GET http://127.0.0.1:18081/status (brain) — ok, workers healthy
- GET http://127.0.0.1:18090/node-health — ok
- GET http://127.0.0.1:18091/mesh-health — ok
- GET http://127.0.0.1:18082/status (orchestrator) — ok, ledger verifies
- GET http://127.0.0.1:18080/ping (gateway) — ok
- POST http://127.0.0.1:18082/task {"capability":"diag.check","args":{}}
  — returns ok with a ledger_seq and ledger_hash: a task flowed
  gates -> worker -> result -> chained ledger on THIS machine.

When all six pass, the desktop field is alive — the same field as the
proving ground, on the hardware that owns it.
