#!/usr/bin/env python3
"""Small dependency-free structural check for the repository agent contract."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_FILES = (
    "AGENTS.md",
    "docs/agent-context.md",
    "docs/agent-governance.md",
    "docs/agent-tooling.md",
    ".github/copilot-instructions.md",
)
REQUIRED_MARKERS = (
    "Policy-Version:",
    "## Authority and instruction handling",
    "## Security and approval gates",
    "## Validation and handoff",
)
PLACEHOLDERS = ("<PLACEHOLDER>", "<TEAM_OR_MAINTAINER>", "<COMMAND>")

def main() -> int:
    errors = []
    for relative in REQUIRED_FILES:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing required file: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            errors.append(f"empty required file: {relative}")
        if relative == "AGENTS.md":
            for marker in REQUIRED_MARKERS:
                if marker not in text:
                    errors.append(f"AGENTS.md missing required marker: {marker}")
            for marker in PLACEHOLDERS:
                if marker in text:
                    errors.append(f"AGENTS.md contains unresolved placeholder: {marker}")
    if errors:
        print("Agent policy check FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Agent policy check passed: {len(REQUIRED_FILES)} required files present; contract markers verified.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
