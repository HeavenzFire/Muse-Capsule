# Unified Field Prototype Instructions

Scope: `field/**`. Root `AGENTS.md` security and approval gates remain mandatory.

- Treat the field as a prototype until the relevant service or UI has been launched and behavior verified in its intended environment.
- Inspect the manifest and the affected component before changing orchestration contracts.
- Keep component health, launch success, and task completion as distinct states; never report ALIVE based only on a file's existence or a process launch attempt.
- Do not launch services, modify machine configuration, install packages, change firewall/network settings, or execute privileged PowerShell as a side effect of code review.
- Infrastructure, credential, deployment, and destructive actions require explicit owner approval.
- Add tests for state transitions, timeout/failure reporting, and approval boundaries when changing orchestration behavior.
- Do not modify generated capsule artifacts manually; update their source and document the regeneration command.
