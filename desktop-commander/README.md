# Desktop Commander V1

Zachary's own combined agent — **desktop commander + remote desktop +
browser control in one Python program** — built to replace the
"his hands only" bottleneck on his machines: one authenticated local
service that can run commands, see the screen, drive keyboard/mouse,
and render web pages, with every action written to a tamper-evident
ledger.

This is the **proving-ground V1**, built and tested on the Linux VM.
The same file runs on Windows under Python 3.9+; per-OS screenshot /
input backends are the V2 step (see *Windows notes*).

Pure Python 3 standard library. No pip installs, no dependencies.

## Run it

```sh
python3 commander.py            # first run generates the key and prints it ONCE
python3 commander.py --verify   # check ledger.jsonl's hash chain and exit
```

Options: `--host`, `--port` (default 18077; `0` = ephemeral),
`--data-dir` (default: this script's directory). Defaults also come
from `commander.json` in the data dir:

```json
{ "host": "127.0.0.1", "port": 18077 }
```

Everything the service writes lives in the data dir:
`commander.key`, `ledger.jsonl`, `shots/`.

## Security model

- **Loopback by default.** Binds `127.0.0.1` unless you change it.
  There is no TLS — the key is the boundary, so do not expose the port
  beyond a trusted network/VPN without a tunnel in front of it.
- **Every endpoint requires auth.** Send the key as the
  `X-Commander-Key` header. Comparison is constant-time
  (`hmac.compare_digest`). No key, wrong key → `401`, no exceptions,
  not even for `/status`.
- **The key** is 64 hex chars, generated on first run into
  `commander.key` with file mode `0600`, printed to the console
  **exactly once** (the run that creates it), and **never logged** —
  not in the ledger, not in server logs.
- **Hash-chained ledger.** Every action (exec, shot, type, click,
  browser render — success or honest failure) appends one line to
  `ledger.jsonl`. Each entry's `prev_hash` is the sha256 of the exact
  previous line's text with **no trailing newline**; the first entry
  links to the sha256 of the empty string. `python3 commander.py
  --verify` re-walks the chain and names the first broken entry.
- **`/type` privacy:** the ledger records that typing happened (char
  count + a truncated sha256 of the text), never the typed text
  itself — typed content may be a password.

## Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/status` | — | hostname, OS, python, server uptime, version, which backends exist, ledger size |
| POST | `/exec` | `{command, timeout_s?}` | `{stdout, stderr, exit_code, timed_out, *_truncated}` — output capped at 64 KB per stream, timeout default 30 s, max 300 s |
| POST | `/shot` | — | `{path, bytes, tool}` — PNG saved under `shots/` |
| POST | `/type` | `{text}` | types the text via the input backend |
| POST | `/click` | `{x, y}` | moves the mouse and clicks |
| POST | `/browser/render` | `{url}` | rendered page `{title, text}` from headless Chromium |

Backend-missing answers are **honest errors**, never fakes:
`501` with a message naming every tool that was looked for.

## Backends (probed at call time, first match wins)

- **Screenshot:** `grim`, `scrot`, `maim`, `gnome-screenshot`,
  ImageMagick `import`. Tool present but failing (e.g. no display)
  → `502` with the tool's own stderr.
- **Input:** `xdotool` (`type --`, `mousemove … click 1`).
- **Browser:** `chromium`, `chromium-browser`, `google-chrome`,
  `google-chrome-stable`, run as `--headless=new --dump-dom`.
  Returns the rendered DOM's title and visible text (32 KB cap).

## What works on this VM (measured, 2026-10-21)

Probed before writing a line of code: **no** Chromium of any name,
**no** xdotool, **no** screenshot tool (scrot/maim/grim/
gnome-screenshot/import all absent), and `DISPLAY` is unset — this
VM is headless.

| Capability | On this VM | Why |
|---|---|---|
| `/status`, auth | **Works** | pure stdlib |
| `/exec` | **Works** | subprocess |
| Ledger + `--verify` | **Works** | tested end-to-end |
| `/shot` | Honest `501` | no screenshot tool exists here |
| `/type`, `/click` | Honest `501` | no xdotool, no display |
| `/browser/render` | Honest `501` | no Chromium binary here |

On any host that *has* those tools on PATH, the same file uses them
with no code change. `test_commander.py` accepts either a real `200`
or a named honest error for the backend endpoints — it fails only on
a fake or a crash.

## Honest limits of V1

- **Browser control is render-only.** Headless dump of the initial
  rendered DOM: no session, no cookies, no login state, no clicking,
  no form-filling. Interactive browser driving is a V2 backend
  decision, not something V1 pretends to do.
- **`/exec` is a real shell** (`shell=True`) behind the key. That is
  the product — remote command execution — and also why the key and
  the loopback default are non-negotiable.
- **Timeout semantics:** on timeout the direct child is killed and
  partial output returned; a command that spawns detached
  grandchildren can outlive its timeout.
- **Ledger growth** is unbounded in V1; rotation is a V2 concern.
  The chain makes tampering evident, not impossible for someone who
  can rewrite the whole file and recompute every link.
- **No TLS, no multi-user keys, no rate limiting** in V1.

## Windows notes

- Same `commander.py`, Python 3.9+ (developed/tested on 3.12).
  `commander.key`'s `0600` is POSIX; on Windows rely on the file
  living in the user's own profile directory and its ACLs.
- `/exec` runs through `cmd.exe` (the stdlib `shell=True` behavior).
- Screenshot/input on Windows need real backends — PowerShell /
  Win32 capture and `SendInput` — deliberately **not** emulated in
  V1. On the ASUS today, `/status`, `/exec`, the ledger, and (with a
  Chrome/Chromium install) `/browser/render` work; `/shot`, `/type`,
  `/click` answer honest `501`s until the V2 Windows backend lands.
  V1 does not bind port 18077 anywhere until Zachary starts it there
  himself.

## Tests

```sh
python3 test_commander.py
```

Boots the server on an ephemeral port with a throwaway key and
ledger, checks: key printed once + file mode `0600`; `/status` 401
without key, 401 with wrong key, 200 with key; `/exec` echo
round-trip, exit-code propagation, timeout enforcement, 401 without
key; each backend endpoint answering honestly; the ledger chain
recomputed independently in the test **and** via `--verify`; and a
clean shutdown. **20/20 passing** on this VM (2026-10-21).
