# TEST-RUN — desktop connector, live run 2026-10-22

The executor was run against the **real Desktop Commander V1**
(`~/workspace/desktop-commander/commander.py`, unmodified), booted
on a scratch port with a throwaway data dir under `/tmp`:

- Commander: `python3 commander.py --data-dir /tmp/dc-gpt-test/data --host 127.0.0.1 --port 18099`
  → console: `LISTENING http://127.0.0.1:18099`; temp `commander.key`
  mode `600` (the key value was redacted from every record and
  appears in none of the connector files — verified by grep).
- Executor, per run: `COMMANDER_KEY_FILE=/tmp/dc-gpt-test/data/commander.key python3 desktop_executor.py <request> --out <result> --commander-base http://127.0.0.1:18099`
- The commander was killed after the run; final check:
  `port 18099 is free (nothing left listening)`. All scratch state
  under `/tmp` was discarded.

## (a) status — example_request.json → status ok

```
DONE examples/example_request.json -> a-status.json (status: ok)   exit=0
```
Result package (`examples/example_result.json` is this real output):
commander responded `{"ok": true, "name": "desktop-commander",
"version": "1.0.0", "hostname": "htch-runtime", "backends":
{"screenshot": null, "input": null, "chromium": null},
"ledger_entries": 0}`; result carried `ledger_entries: 0` and
`ledger_head_hash: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
(the chain's genesis hash — no actions yet), `unresolved: []`.

## (b) exec echo, properly authorized — test-exec.json → status ok

```
DONE examples/test-exec.json -> b-exec.json (status: ok)   exit=0
output: {"stdout": "gpt-desktop-roundtrip\n", "stderr": "",
         "exit_code": 0, "stdout_truncated": false,
         "stderr_truncated": false, "commander_response": null}
status: ok ledger_entries: 1
ledger_head_hash: ef82a807492e884bda7951fa4ca2837aed13651bea2e2827e149b5be5e1da77d
```

## (c) shot on the headless VM — test-shot.json → honest failed/501

```
DONE examples/test-shot.json -> c-shot.json (status: failed)   exit=0
status: failed
failures: [{"step": "POST /shot", "message": "HTTP 501: no screenshot
  backend on this host; looked for: grim, scrot, maim,
  gnome-screenshot, import (none on PATH; DISPLAY=unset)"}]
artifacts: []
```
No screenshot was faked and no artifact was claimed. This is the
expected truth on the VM (and on Windows until the Win32 backend
lands behind the same endpoint).

## (d) exec with NO authorization — test-exec-denied.json → denied, commander never called

```
ledger entries BEFORE denied request: 2
DENIED examples/test-exec-denied.json: no authorization.already_given
  entry names action type 'exec'; the commander was not contacted
result written to d-denied.json (status: denied)   exit=0
ledger entries AFTER denied request:  2
status: denied
performed: ['executor validated package: PASS',
            'no commander contact (denied at authorization check)']
ledger_entries in result: None
commander.py --verify: ledger OK: 2 entries, chain intact
```
The ledger count is identical before and after (2 = the (b) exec
entry + the (c) shot attempt entry) — the denial happened
entirely inside the executor, before any commander contact.

## (e) bad package — bad_request.json → validator rejects

```
FAIL examples/bad_request.json (desktop_request package): 9 problem(s)   exit=1
  - package: missing required field 'project_id'
  - package: missing required field 'conversation_reference'
  - package: missing required field 'timestamp'
  - package: missing required field 'stop_conditions'
  - package: missing required field 'success_criteria'
  - field 'host': 'moon' is not one of ['asus', 'vm'] (a label only — never an address)
  - field 'action_type': 'teleport' is not one of ['status', 'shot', 'exec', 'type', 'click', 'browser_render', 'file_read', 'file_write']
  - hard rule: permissions.credentials_in_packages must be false
  - hard rule: package.permissions.notes looks like it carries a credential (contains 'token'); credentials never travel in packages
result written to e-bad.json (status: failed)
```

## Verdict

All five behaviors as designed: authorized read and exec succeed
end-to-end through the real commander; a missing backend is an
honest 501 failure, not a fake success; a state-changing action
without Zachary's named authorization is denied with zero
commander contact (ledger-proven); and a credential-carrying
package is rejected before anything else happens. All JSON
packages and schemas parse as valid JSON.
