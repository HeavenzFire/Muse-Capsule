# GATEWAY.md — architecture

## Why

The stack grew four separate loopback APIs (brain 18081, orchestrator
18082, node 18090/18091/18083/18088) plus direct web calls from workers
(Gemini, OpenAI-compat, DuckDuckGo, Wikipedia, GitHub API). Every one of
those is a surface "they" can meter, price, or cut. The gateway collapses
them into ONE surface with OUR keys and OUR audit — and puts every web
call behind an allow-list.

## Shape

```
phone / laptop / witness
        |  X-Gateway-Key (our keys, minted on his machine)
        v
  +-----------+  127.0.0.1:18080 (loopback default)
  |  GATEWAY  |-- audit.jsonl (hash-chained, every request)
  +-----+-----+
        |  loopback only, gateway is the sole client
   +----+----------------------------------+
   | brain 18081 | orch 18082 | node 1808x |
   +-------------+-------------------------+
        |
   /egress/* --> allow-list --> the web (logged, default-deny)
```

## Auth

- Keys: `sgw-` + 32 hex, minted by `--init` on first install, printed ONCE.
- Stored as salted sha256 in `data/keys.json`. Raw keys never touch disk
  or the audit log.
- Scopes: `phone`, `laptop`, `witness`. Only `laptop` mints/revokes.
- Revocation list is append-only.
- The gateway holds the brain's own `brain.key` and injects it as
  `X-API-Key` on `/brain/*` — the phone carries ONE key, not two.
  The gateway's key never leaks upstream (stripped at the proxy).

## Audit

`gateway/audit.py`: append-only JSONL. Chain rule matches the settlement
ledger convention (prev = sha256 of previous line's exact text, no
trailing newline). Bodies are stored as sha256 only — the log proves
what crossed without holding secrets. `verify()` detects any tamper.

Every request is logged: proxied calls, forge translations, egress
allow AND deny, key admin, even `/ping` and 401s.

## Egress

`gateway/allowlist.py` + `gateway/egress.py`:

- Default-deny. Loopback always allowed (our services, not the web).
- SSRF guard: resolved IPs must be public unless the host was literally
  loopback.
- Three sanctioned operations: `fetch` (page text), `search`
  (SearXNG-first, Wikipedia fallback), `relay` (generic API relay for
  GitHub/Gitea REST).
- Capability binding: a domain is allow-listed only for declared
  capabilities (`web.search`, `forge.repo.sync`, ...). Right domain,
  wrong capability → denied + logged.
- `egress.py` doubles as the worker migration shim.

## What the gateway does NOT do

- It does not replace the subsystems' own gates (brain API key,
  orchestrator gate union, approvals). It fronts them; defense in depth.
- It does not terminate TLS. Public bind is explicit opt-in and
  plaintext; TLS lives in front of it.
- It does not rewrite workers. The shim is the migration path
  (DECOUPLE.md row 8).
- It does not invent keys for the phone. The phone key is minted on his
  machine and he carries it to the app himself.
