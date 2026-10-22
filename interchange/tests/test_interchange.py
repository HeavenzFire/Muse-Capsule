#!/usr/bin/env python3
"""Executable tests for the HeavenzFire cross-AI interchange format.

Stdlib only. Validates:
  1. the v1 schema is well-formed and carries every contract field;
  2. every package in ../packages validates against the schema
     (subset validator below: type, required, properties, items,
     enum, const, pattern, format date-time);
  3. serialize -> parse round-trip preserves a package exactly;
  4. the hard rules fail loudly: a missing contract field, an
     unknown task state, a malformed sha256, a bad timestamp, and
     credentials_in_packages flipped to true are all rejected.

Run:  python3 test_interchange.py        (exit 0 = all green)
"""
import copy
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCHEMA_PATH = ROOT / "schema" / "heavenzfire-interchange-v1.schema.json"
PACKAGES_DIR = ROOT / "packages"

CONTRACT_FIELDS = [
    "project_id", "source_platform", "conversation_reference",
    "objective", "decisions", "task_status", "artifacts",
    "test_results", "next_actions", "permissions", "timestamp",
]

DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


def validate(instance, schema, path="$"):
    """Return a list of errors (empty = valid) for the schema subset
    this format uses."""
    errors = []
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']}")
    t = schema.get("type")
    if t == "object":
        if not isinstance(instance, dict):
            return [f"{path}: expected object, got {type(instance).__name__}"]
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required field {key!r}")
        for key, sub in schema.get("properties", {}).items():
            if key in instance:
                errors += validate(instance[key], sub, f"{path}.{key}")
    elif t == "array":
        if not isinstance(instance, list):
            return [f"{path}: expected array, got {type(instance).__name__}"]
        sub = schema.get("items")
        if sub:
            for i, item in enumerate(instance):
                errors += validate(item, sub, f"{path}[{i}]")
    elif t == "string":
        if not isinstance(instance, str):
            return [f"{path}: expected string, got {type(instance).__name__}"]
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "pattern" in schema and not re.match(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} fails pattern {schema['pattern']}")
        if schema.get("format") == "date-time" and not DATETIME_RE.match(instance):
            errors.append(f"{path}: {instance!r} is not an ISO-8601 date-time")
    elif t == "integer":
        if not isinstance(instance, int) or isinstance(instance, bool):
            return [f"{path}: expected integer, got {type(instance).__name__}"]
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
    elif t == "boolean":
        if not isinstance(instance, bool):
            return [f"{path}: expected boolean, got {type(instance).__name__}"]
    elif isinstance(t, list):  # e.g. ["string", "null"]
        if instance is None:
            if "null" not in t:
                errors.append(f"{path}: null not allowed")
        elif "string" in t:
            errors += validate(instance, {"type": "string",
                                           **{k: v for k, v in schema.items()
                                              if k in ("pattern", "minLength")}},
                                 path)
    return errors


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class InterchangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load(SCHEMA_PATH)
        cls.package_files = sorted(PACKAGES_DIR.glob("*.json"))
        cls.packages = [load(p) for p in cls.package_files]

    def test_schema_declares_every_contract_field(self):
        required = set(self.schema.get("required", []))
        for field in CONTRACT_FIELDS:
            self.assertIn(field, required, f"schema missing contract field {field}")
        self.assertIn("schema_version", required)

    def test_at_least_one_package_exists(self):
        self.assertTrue(self.package_files, "no packages in packages/ to validate")

    def test_every_package_validates(self):
        for path, pkg in zip(self.package_files, self.packages):
            errors = validate(pkg, self.schema)
            self.assertEqual(errors, [], f"{path.name}: {errors}")

    def test_round_trip_preserves_package(self):
        for pkg in self.packages:
            again = json.loads(json.dumps(pkg))
            self.assertEqual(again, pkg)
            self.assertEqual(validate(again, self.schema), [])

    def test_missing_contract_field_is_rejected(self):
        bad = copy.deepcopy(self.packages[0])
        del bad["project_id"]
        self.assertTrue(validate(bad, self.schema))

    def test_unknown_task_state_is_rejected(self):
        bad = copy.deepcopy(self.packages[0])
        bad["task_status"]["items"].append(
            {"id": "x", "title": "x", "state": "totally_done_probably"})
        self.assertTrue(validate(bad, self.schema))

    def test_malformed_sha256_is_rejected(self):
        bad = copy.deepcopy(self.packages[0])
        bad["artifacts"].append(
            {"id": "x", "name": "x", "location": "x", "sha256": "not-a-hash"})
        self.assertTrue(validate(bad, self.schema))

    def test_bad_timestamp_is_rejected(self):
        bad = copy.deepcopy(self.packages[0])
        bad["timestamp"] = "last Tuesday-ish"
        self.assertTrue(validate(bad, self.schema))

    def test_credentials_in_packages_is_rejected(self):
        bad = copy.deepcopy(self.packages[0])
        bad["permissions"]["credentials_in_packages"] = True
        self.assertTrue(validate(bad, self.schema),
                        "the no-credentials rule must be schema-enforced")

    def test_share_reference_cannot_claim_api_access(self):
        # conversation_reference.access has no value that grants
        # anything: every enum member is a label, and 'login-walled'
        # and 'unknown' must remain expressible.
        access_enum = (self.schema["properties"]["conversation_reference"]
                       ["properties"]["access"]["enum"])
        self.assertIn("login-walled", access_enum)
        self.assertIn("unknown", access_enum)
        self.assertNotIn("api", access_enum)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
