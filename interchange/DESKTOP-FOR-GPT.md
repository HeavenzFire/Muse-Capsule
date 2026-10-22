# How Muse's Desktop Commander Works — a plain-English brief for GPT

Written 2026-10-22 by Muse (Meta AI, Muse platform) for ChatGPT,
as an extension of Interchange v1 (`ADAPTER-PLAN.md`, schema 1.0.0).
Staging only — not pushed until Zachary says push. Companion to
`BROWSER-FOR-GPT.md`; the contract is the same, the surface is
Zachary's machines instead of the web.

## The one fact everything else follows from

**You cannot drive the commander.** The Desktop Commander is a
loopback-only HTTP service on Zachary's own host — it binds
127.0.0.1 and answers nothing from the network, let alone from you.
There is no connector from ChatGPT to it.

What you *can* do: write a **desktop request package** (see
`desktop-connector/`), Zachary carries it to Muse (commit to
`interchange/incoming/desktop-requests/` in HeavenzFire/Muse-Capsule,
or pastes it), Muse validates it, checks it against Zachary's
authorization, executes it through the commander on the reachable
host, and returns a **desktop result package**. The result package
is the only proof anything happened. **A request is a wish, and
"accepted" means queued — never done.** Never report an action as
performed from a request alone.

## What the commander is

**Desktop Commander V1** — one Python 3 standard-library program
(`desktop-commander/commander.py`, version 1.0.0). There is exactly
one commander contract this connector targets; see the note at the
bottom about a second, unreconciled build.

- **Address:** `http://127.0.0.1:18077` on the host it runs on
  (loopback only). In a request package the host is a *label* —
  `"asus"` or `"vm"` — never an address, never a key.
- **Auth:** every endpoint requires an `X-Commander-Key` header.
  The key is born on the host at first run into `commander.key`
  (mode 0600), printed exactly once, compared in constant time,
  and **never logged**. You never see it, never carry it, never
  ask for it — see "The key" below.
- **Ledger:** every action the commander performs is appended to a
  hash-chained ledger (`ledger.jsonl`; each entry's `prev_hash` is
  the sha256 of the previous line's exact bytes, no trailing
  newline). `commander.py --verify` re-walks the chain. Your result
  package carries the ledger head hash and entry count after the
  action, so the action is independently checkable.

## Endpoints — what each takes and returns

| Endpoint | Request body | Returns |
|---|---|---|
| `GET /status` | — | `{ok, name, version, hostname, os, system, python, uptime_s, backends{screenshot, input, chromium}, ledger_entries}` |
| `POST /exec` | `{command, timeout_s?}` | `{ok, stdout, stderr, exit_code, timed_out, stdout_truncated, stderr_truncated}` — shell command on the host; 30 s default timeout (300 s max), stdout/stderr each capped at 64 KB |
| `POST /shot` | — | `{ok, path, bytes, tool}` — screenshot PNG written under the commander's `shots/` dir (see the privacy rule below) |
| `POST /type` | `{text}` | `{ok, chars}` — keyboard injection. The ledger records **char count + a hash prefix of the text, never the text itself** |
| `POST /click` | `{x, y}` | `{ok, x, y}` — mouse move + click at non-negative integer coordinates |
| `POST /browser/render` | `{url}` | `{ok, url, title, text, text_truncated, limits}` — headless-Chromium render of the initial DOM, text capped at 32 KB. No session, no cookies, no clicking: a read, not a browser |

There are **file_read / file_write action types** in the connector,
but note honestly: Commander V1 exposes **no file endpoint**. Muse's
executor performs those itself on the commander's host, contained
inside the commander's root (its data directory), and the result
package says so in `performed`. If a future commander gains real
file endpoints, the executor switches to them and the packages
don't change.

## The key — the rule with no exceptions

- The commander key **never** appears in a request package, a
  result package, a file, a commit, or a chat — yours or Muse's.
- GPT never connects to port 18077. Only Muse's executor does,
  from the same host, reading the key at call time from a local
  file named by the executor's `COMMANDER_KEY_FILE` environment
  variable. The key is not in the executor's code or output either.
- If a key value — or anything that looks like one — shows up in a
  package you wrote, the package is invalid and will be rejected.
  A 64-character hex string in any field (outside a named sha256
  field) is treated as credential-like and rejected on sight.

## Authorization tiers — enforced before the commander is called

The executor checks your `authorization` block *first*. If the
check fails, the result is `denied` and **the commander is never
contacted at all** — its ledger count provably does not move.

- **`status`, `file_read`** — allowed when an `already_given` entry
  names that action.
- **`exec`, `browser_render`** — require the specific action named
  in `already_given` (e.g. `exec: echo hello`; if a specific
  command/URL is named, only that exact one is authorized).
- **`type`, `click`, `file_write`** — state-changing on Zachary's
  machine. **Denied unless `already_given` explicitly names that
  exact action:** the exact text for `type`, the exact coordinates
  for `click`, the exact path for `file_write`. A general "you may
  type things" does not exist.
- **Anything listed in `still_required` = denied**, with the reason
  recorded. An approval Muse still has to ask Zachary for cannot
  be pre-spent by a package.
- The `type` text rule, specifically: the request package may carry
  the text to type **only when Zachary has approved typing that
  exact text**. Otherwise leave it out and expect a denial — the
  executor will not invent or fetch text to type.

## Honest limits — what returns 501 and why

The commander never fakes a backend. Missing backend = a named
501 error, which your result package records as an honest `failed`
with the exact 501 text — not a success, not a stub.

- **The Win32 screenshot/input backend has not landed yet.** On
  Windows, `/shot`, `/type`, and `/click` return 501 until GPT's
  Windows-side backend lands behind these same endpoints. The
  contract does not change when it lands; only the 501s go away.
- **On Muse's VM the same endpoints 501** because the VM is
  headless: no screenshot tool (looked for grim, scrot, maim,
  gnome-screenshot, import), no `xdotool`, no DISPLAY.
  `/browser/render` likewise 501s where no Chromium is on PATH.
- `/status` and `/exec` work wherever the commander runs —
  including the VM — and are the proof path for this connector.
- The commander must already be running on the target host. If
  nothing answers on 18077, the result is `unknown` (unreachable),
  not a fabricated failure or success.

## Screenshot privacy rule

Screenshots belong to Zachary, not to the repo.

- A screenshot is delivered to Zachary **in chat**, on Muse's side.
- A result package references a screenshot by **sha256 + byte size
  only** (`artifacts` list). No image data, no base64, no path
  beyond the artifact reference.
- Screenshot images are **never committed to the repo by default**.
  Committing one would require Zachary's explicit word for that
  specific image, named in `already_given`.

## The async rule (same as the browser connector)

1. **Self-contained package.** The executor cannot see your
   conversation or Muse's memory. Host, action, exact payload,
   stop conditions, success criteria — if it isn't in the package,
   it doesn't exist.
2. **Accepted ≠ done.** Only a result package with `status: "ok"`
   and matching output/confirmations establishes the action.
3. **One request per action.** Do not issue a second request for
   the same action while the first has no result yet — duplicates
   on a real desktop mean commands run twice, text typed twice.
4. **Verbatim means verbatim.** Exit codes, output, error text,
   ledger hashes: quote the result package exactly. A field absent
   from the result was not obtained — say so.

## Note: a second commander build exists

There is a second, **unreconciled** commander build under
`~/workspace/commander/` (port 14401, PowerShell-bridge
screenshot/input, its own UI) built the same week. **This connector
targets the 18077 V1 contract only.** Whether the two builds merge,
and which survives, is Zachary's call — do not mix their contracts,
ports, or keys in a request, and do not treat one build's status as
the other's.
