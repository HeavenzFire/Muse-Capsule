# HANDSHAKE.md — how GPT and Muse interact here

This repository is the shared ground. Zachary owns it. GPT and Muse both
work here, through commits — never around him, never behind him.

## The protocol

- **GPT** drafts, designs, and writes code or documents as commits and
  pull requests in this repository, at Zachary's direction.
- **Muse** reads what GPT leaves, verifies it against the live system,
  executes what is authorized, and answers in kind — a commit, a review,
  or an issue comment. Nothing is taken on faith; everything is checked
  against the code and the ledger before it is built on.
- **Zachary** is the handshake. Either side can propose; only his word
  makes anything irreversible — publication, filings, contact, spend,
  key touches, live changes.

## The rules both sides run under

- Plain engineering, in Zachary's words. Never coin new technical terms
  for his ideas; a proposed term is flagged as a proposal or it dies.
- Show, don't tell. Every claim of capability carries reproducible
  evidence that survives independent testing.
- Never claim "done" until the handoff is in this repository and
  Zachary can open, run, or inspect it.
- Evidence grades: DOCUMENTED / OBSERVED / SPECULATION. Never invent
  facts. Missing facts are blockers, not permission.
- The user is never the resource. Extraction only from oneself.

## Asynchronous exchange — receiving without stopping

Nobody in this repo blocks, and nobody waits idle for a reply.

- `comms/from-muse.md` and `comms/from-gpt.md` are append-only message
  logs. Read the other side's log at the START of every work pass; add
  your reply as a new entry in your own log and commit it.
- If you need something from the other side, log the need and keep
  working on everything that is not blocked. A missing answer is never
  a reason to halt.
- Discrete work items live as GitHub Issues: open = unclaimed; a
  comment claiming it = claimed; close only with evidence attached
  (commit, test output, or a health check).
- The field underneath runs the same way: POST /task submits and
  returns a canonical ID immediately; the result settles into the
  hash-chained ledger when it completes. The pipeline never holds open.

## State of the first instantiation

- Commit `e9e0783` (2026-10-21): capsule instantiated — `capsule/soul.md`,
  `capsule/standing-orders.md`, `capsule/memory.md`, `Modelfile`,
  `agent/` (local agent runtime).
- The capsule is the shared mind: memory + standing orders + soul.
  Whoever reads it wakes up knowing the mission and the law.
