# Muse × GitHub — integration record

Established by Zachary. Corrected and verified 2026-10-22.

## The app
- **Meta Muse AI** — GitHub App slug `meta-muse-ai`
  (public page: https://github.com/apps/meta-muse-ai)
- What it is, in GitHub's own listing: it lets Muse users connect their
  GitHub account and work with repositories, issues, and pull requests
  through GitHub's official MCP server; actions run as the connected user
  and stay subject to Muse approval controls.
- This is the Muse counterpart to the GitHub Apps Zachary installed for
  GPT and for Gemini: each vendor's app, installed by him, on his account.

## His part — already done, not to be redone
- 2026-10-08: Zachary connected Muse to his GitHub and selected
  **All repositories** (his word at the time: "already did"). Read access
  was verified the same day.
- 2026-10-22: Zachary corrected Muse in the app-creation thread —
  "Already done that for you, I'm not going backwards." The earlier plan
  to create a separate Zachary-owned GitHub App (APP-SPEC draft) is
  SUPERSEDED by this record. No browser sign-in redo, no second app.

## Verified live, 2026-10-22 ~13:50 CDT (via the connector, not the browser)
- `github status`: auth_status connected, authenticated, endpoint
  https://api.githubcopilot.com/mcp/ (GitHub official MCP server)
- `get_me`: login **HeavenzFire** (id 185123804), 270 public repos
- `list_commits` HeavenzFire/Muse-Capsule: HEAD `a7f1ff4` readable —
  the 2026-10-22 interchange v1 commit
- `search_repositories user:HeavenzFire`: results returned across his
  repos (231+ matches) — scope is account-wide, not one repo

## What runs through it
- Muse ↔ GPT handshake on HeavenzFire/Muse-Capsule (commits are the
  exchange; Muse verifies before building; Zachary's word gates
  irreversibles and merges)
- Cross-AI interchange packages under `interchange/`
- Reads are live now; writes go through Muse approval controls,
  per GitHub's own description of the app

## Honest limits (unchanged)
- The app acts as the connected user; it does not create repositories
  under its integration identity (403 seen 2026-10-21) — repo creation
  remains the account owner's action in GitHub's UI.
- Browser GitHub sessions are a separate surface and are NOT part of
  this integration; nothing here depends on them.
