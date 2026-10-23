# GPT handoff — keep focus on the Unified Field desktop bridge

Date: 2026-10-22
Author: GPT / ChatGPT
Evidence source: current default-branch files in `HeavenzFire/Muse-Capsule`, read through the connected GitHub integration during this pass.

## Current evidence

- **OBSERVED (repository state):** `desktop-commander/commander.py` exists. It authenticates requests with `X-Commander-Key`, defaults to loopback on port 18077, and appends actions to a hash-chained ledger.
- **OBSERVED (repository state):** `desktop-commander/README.md` documents `/status` and `/exec` as the available V1 path. Windows screenshot, typing, and click backends are still documented as missing; those endpoints return honest 501 responses.
- **DOCUMENTED, not live-verified:** `comms/from-muse.md` says the ASUS v4 package was delivered and is awaiting its Windows run. Until the Windows result files are committed, the commander is not proven operational on the ASUS.
- **DOCUMENTED, not live-verified:** the same log says Tailscale sign-in was observed, but no service path over the tailnet had yet been proven.
- **OBSERVED (repository state):** `interchange/desktop-connector/INSTALL-AND-RUN.md` defines the acceptance bar: authenticated status request, harmless echo execution returning `gpt-desktop-roundtrip` with exit code 0, and recovery verification.

## Priority: finish the existing bridge, do not start a parallel setup

1. On the ASUS, run the already-delivered V4 package/test procedure and publish the actual output. Do not ask Zachary to repeat package creation or use the third-party Desktop Commander.
2. Prove the local round trip using the documented `desktop_executor.py` examples; commit the resulting status/exec result packages with secrets excluded.
3. Prove recovery: restart the commander during/after a harmless test, verify `ledger.jsonl` with `commander.py --verify`, and show that an unauthorized request does not execute.
4. Treat the unstable internet as a bridge blocker only when measured: distinguish local commander health from tailnet reachability. Do not change DNS, reset networking, or reconfigure Tailscale without evidence.
5. Keep screenshot/type/click explicitly unavailable until a real Windows backend is implemented and tested. Never label a 501 as success.
6. After local loopback proof, test the intended remote path separately. Do not expose port 18077 directly to the LAN or public internet; use the intended authenticated tailnet/tunnel design and keep the key machine-local.

## Reporting rule

Return concrete artifacts: commit SHA, request ID, HTTP status, actual stdout/exit code, ledger verification result, and the observed tailnet endpoint result. If no Windows worker can currently reach the ASUS, report that as the exact blocker and continue with code/test work that does not require the live machine.

No credentials, commander keys, or private keys belong in this handoff.
