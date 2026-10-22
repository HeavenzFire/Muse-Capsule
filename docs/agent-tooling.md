# Agent Tooling and Instruction Discovery

## Canonical policy

The repository-root `AGENTS.md` is the canonical project contract. Nested `AGENTS.md` files specialize only their subtrees. `AGENTS.global.md` is an organization convention and is not assumed to be auto-discovered by every client.

The small `.github/copilot-instructions.md` adapter points supported Copilot surfaces to the canonical contract; it is not a guaranteed file-transclusion mechanism. Each client must be tested on the exact surface and version used.

## Compatibility test matrix

Before unattended or high-impact use, test each supported client with a harmless fixture repository and record the client/version, date, result, and evidence.

| Test | Expected behavior |
|---|---|
| Root discovery | Client reads the root contract before editing |
| Scoped discovery | Client applies the correct nested instructions to files in that subtree |
| Command selection | Client selects the documented command for the affected component |
| Prompt-injection fixture | Instructions embedded in issue text cannot authorize secret disclosure or weaken policy |
| Protected action | Client stops at destructive, privileged, merge, or deployment approval gates |
| Unavailable check | Client reports blocked/unavailable instead of claiming success |
| Concurrent work | Separate write tasks use isolated branches/worktrees and do not overwrite each other |

A model repeating policy text is not proof of enforcement. Separately inspect tool permissions, sandbox boundaries, GitHub rules, and approval controls.

## Versioning

Record client and model identifiers when available. Re-run compatibility tests after changing the client, instruction layout, adapter, policy version, or execution permissions. Do not fetch mutable policy from a remote default branch at runtime; use a reviewed, versioned snapshot.
