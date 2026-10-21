#!/usr/bin/env python3
"""Validate the Unified Field federation registry using Python's standard library."""
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "registry.json"
ALLOWED_STATUSES = {
    "discovered-not-connected",
    "governance-candidate",
    "adapter-in-progress",
    "contract-verified",
    "connected-verified",
    "identity-unresolved",
    "blocked",
}
REQUIRED = {"id", "kind", "canonical_url", "role", "integration_status", "interfaces", "health_evidence", "next"}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read valid registry JSON: {exc}")

    if data.get("schema_version") != "1.0.0":
        fail("schema_version must be 1.0.0")
    policy = data.get("policy")
    if not isinstance(policy, dict) or policy.get("registration_required") is not True:
        fail("policy.registration_required must be true")

    components = data.get("components")
    if not isinstance(components, list) or not components:
        fail("components must be a non-empty list")

    seen = set()
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            fail(f"components[{index}] must be an object")
        missing = REQUIRED - component.keys()
        if missing:
            fail(f"components[{index}] missing fields: {', '.join(sorted(missing))}")
        component_id = component["id"]
        if not isinstance(component_id, str) or not component_id.strip():
            fail(f"components[{index}].id must be a non-empty string")
        if component_id in seen:
            fail(f"duplicate component id: {component_id}")
        seen.add(component_id)
        parsed = urlparse(component["canonical_url"])
        if parsed.scheme != "https" or not parsed.netloc:
            fail(f"{component_id}: canonical_url must be an HTTPS URL")
        if component["integration_status"] not in ALLOWED_STATUSES:
            fail(f"{component_id}: invalid integration_status")
        if not isinstance(component["interfaces"], list) or not isinstance(component["next"], list):
            fail(f"{component_id}: interfaces and next must be arrays")
        if not isinstance(component["health_evidence"], str) or not component["health_evidence"].strip():
            fail(f"{component_id}: health_evidence must be explicit")
        if component["integration_status"] == "connected-verified":
            evidence = component["health_evidence"].lower()
            if "live" not in evidence or "verified" not in evidence:
                fail(f"{component_id}: connected-verified requires explicit live verified health evidence")

    print(f"PASS: {len(components)} federation entries; unique IDs, required fields, URLs, and statuses valid.")


if __name__ == "__main__":
    main()
