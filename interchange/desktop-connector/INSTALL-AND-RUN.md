# Install and run — GPT desktop commander connector, in one go

Written 2026-10-22. One sitting, top to bottom. Everything here is
stdlib-only Python 3 — no pip installs, no new accounts, no keys
created anywhere except the commander's own key, born on the
Windows machine itself at first start and never copied anywhere.

## What you end up with

GPT writes a `desktop_request` package → Muse runs
`desktop_executor.py` against the Desktop Commander V1 already
installed on the ASUS → GPT gets a `desktop_result` package with
the real output, exit code, and ledger head hash. GPT never sees
the commander key and never connects to the commander directly.

## Step 1 — Commander on the ASUS (skip if already installed)

Use the ASUS package already delivered in chat
(`heavenzfire-commander-asus-v1.zip`). Unzip it and run
`Install-Commander.ps1`. It installs to
`%USERPROFILE%\HeavenzFire\commander`, re-runs the test suite on
the installed copy (expect 20/20 PASS), and births the key on a
brief first start. Re-running the installer is safe: it backs up
replaced files and NEVER re-births an existing `commander.key`.

## Step 2 — Start the commander (one PowerShell window, leave it open)

```powershell
cd $env:USERPROFILE\HeavenzFire\commander
python commander.py --host 127.0.0.1 --port 18077
```

Expect a LISTENING line on 127.0.0.1:18077. Loopback only — it is
not reachable from the network, by design. The key file is
`commander.key` in that same folder.

## Step 3 — Get the connector

Pull this repo on the machine that will run the executor (the
ASUS for Windows tasks):

```powershell
git clone https://github.com/HeavenzFire/Muse-Capsule.git
cd Muse-Capsule\interchange\desktop-connector
```

(Already cloned? `git pull` — the connector landed in the
"Browser connector" + "Desktop connector" commits on main.)

## Step 4 — Prove the chain with the harmless test (do this first)

In a second PowerShell window:

```powershell
$env:COMMANDER_KEY_FILE = "$env:USERPROFILE\HeavenzFire\commander\commander.key"
python desktop_executor.py examples\example_request.json --out result-status.json
python desktop_executor.py examples\test-exec.json --out result-exec.json
```

Read the two result files. PASS means:
- `result-status.json`: `"status": "ok"` and a `ledger_head_hash`.
- `result-exec.json`: `"status": "ok"`, stdout is
  `gpt-desktop-roundtrip`, `"exit_code": 0`.

Then verify the commander's ledger itself:

```powershell
python $env:USERPROFILE\HeavenzFire\commander\commander.py --verify
```

Expect `ledger OK … chain intact`.

## Step 5 — Normal operation

1. GPT commits a request to `interchange/incoming/desktop-requests/`
   in this repo (schema: `desktop_request.schema.json`).
2. Muse validates it. Authorization tiers are enforced before
   any commander contact: status/file_read need a named entry in
   `authorization.already_given`; exec/browser_render need the
   specific action named; type/click/file_write are DENIED unless
   the exact text/coordinates/path was approved by Zachary.
3. Muse runs:
   `COMMANDER_KEY_FILE=<key path> python desktop_executor.py <request> --out <result>`
   (add `--commander-base http://127.0.0.1:18077` if not default).
4. Muse commits the result package. The result package is the
   only proof anything ran — GPT must quote output, exit codes,
   and IDs from it verbatim.

## The three verification tests (GPT's list, 2026-10-22)

1. **Connection** — Step 4 status result: authenticated session to
   the intended endpoint, or it does not count.
2. **Execution** — Step 4 exec result: the echo task reached the
   Windows machine, ran, and returned its actual output + exit
   code. Until this passes ON THE ASUS, the bridge is "built and
   VM-tested", NOT operational.
3. **Recovery** — stop the commander mid-flow and restart it; the
   ledger must still verify (`--verify`), a denied/unauthorized
   request must still never reach it (ledger count unchanged),
   and no request may execute twice: one request_id, one result.

## Honest limits

- Screenshots, typing, and clicks return a named 501 until the
  Win32 backend lands behind the same endpoints. A 501 in a result
  package is the truth, not a failure of this connector.
- Screenshots are delivered to Zachary in chat; result packages
  carry only their sha256 + byte size. Images are never committed.
- If the commander is not running, every request fails closed
  with the connection error in the result package. Nothing queues
  silently and nothing retries on its own.
