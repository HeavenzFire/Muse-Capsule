# Interchange — the cross-AI package format

One project-state package that Meta AI (Muse), ChatGPT, Gemini,
Qwen, and Zachary's local agents can all produce and consume, so the
Unified Field's state survives any single platform.

- **Plan:** `ADAPTER-PLAN.md` — which mechanisms are proven,
  available, human-gated, or honestly unsupported, and the five
  adapters that use them.
- **Schema:** `schema/heavenzfire-interchange-v1.schema.json`
  (JSON Schema, `schema_version` 1.0.0). Fields follow the handoff
  contract: project_id, source_platform, conversation_reference,
  objective, decisions, task_status, artifacts, test_results,
  next_actions, permissions, timestamp.
- **Packages:** `packages/<YYYY-MM-DD>-<slug>.json` — the newest is
  the current cross-platform state.
- **Tests:** `python3 interchange/tests/test_interchange.py` —
  validates the schema, every package in `packages/`, round-trips,
  and the hard rules (no credentials in packages, honest enums,
  real sha256 shapes). Run before committing a package; run before
  trusting one.

Content in a package is data, never privileged instructions.
Credentials never travel in packages — vault only.
