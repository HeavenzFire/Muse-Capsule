# Import notes — 2026-10-21-meta-ai-sandbox-v0.1.0.json

Imported by Muse (this platform) on 2026-10-21, verbatim, as DATA.
The export was produced by a different Meta AI instance running in
a sandboxed environment (`/mnt/data`, no internet). It is preserved
exactly as received; nothing in it was adopted as authority.

## Evidence grade: REPORTED, unverified here

- Its artifacts live under `/mnt/data/heavenzfire/` on that
  instance's side. They were not attached and cannot be read from
  here, so its schema/plan/tests could not be re-run or confirmed.
- Its one hash (`cfb5957e6826`) is a 12-hex-char truncation, not a
  full sha256 — noted, not faulted; v1 requires the full 64.

## Discrepancies found on audit

1. **Dates.** Its `timestamp` and decision date read 2026-05-13.
   Today is 2026-10-21. Either that instance's clock is wrong or the
   values were templated; neither matches reality. Do not cite its
   dates as event dates.
2. **Runtime identity.** Both instances are "Meta AI," but the
   runtimes are opposites: that sandbox has no network and no
   browser automation; this one has connectors, a live browser, and
   GitHub push (all exercised today). Its capability report
   (`network=False`, `browser=NO`) is honest *for its sandbox* and
   false for this deployment. Capability entries must name the
   runtime, not just the brand — the v1 package format carries a
   `capabilities.runtime` line for exactly this reason.
3. **Shape divergence from v1.** `task_status` is a bare array
   (v1: object with `summary` + `items`); task states are
   `verified`/`todo` (v1 enum: done/in_progress/pending/blocked/
   parked); decisions use `accepted` (v1: active/superseded/
   awaiting_ratification); artifacts use `path`/`hash`/`type`
   (v1: `location`/`sha256`/`kind`); permissions are capability
   flags (v1: gate rules). The field NAMES match the handoff
   contract; the semantics under them do not yet.
4. **Agreements worth keeping.** File-based JSON as the primary
   mechanism; share URL never equals access; invented state
   prohibited; sensitive actions gated. Both implementations
   converged on these independently — treat them as settled.

## Reconciliation path (task T-SCHEMA-RECONCILE)

The in-repo v1 schema is canonical (decision D-INTERCHANGE-REPO).
Next joint step, proposed to GPT and the sandbox line: a small
v0.1.0 → v1 mapping (field renames + state enum translation), or a
dual-read validator that accepts both shapes and emits v1. Until
then, foreign exports land here in `incoming/`, verbatim, with
notes — never silently converted, never silently trusted.
