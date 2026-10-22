#!/usr/bin/env python3
"""Validate a browser-connector package against its schema's required fields.

Stdlib only. This is a required-fields + enums + hard-rules check, not a
full JSON Schema engine: it loads the sibling schema JSON, enforces its
`required` list (top level and one level into `authorization`,
`permissions`, and `target`), checks the enum/const fields the connector
depends on, and enforces the hard rules (no credentials in packages,
irreversibles require Zachary's word, no credential-like account_hint).

Usage:
    python3 validate.py request <package.json>
    python3 validate.py result  <package.json>

Exit code 0 = PASS, 1 = FAIL (every problem printed), 2 = usage/IO error.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMAS = {
    "request": os.path.join(HERE, "browser_request.schema.json"),
    "result": os.path.join(HERE, "browser_result.schema.json"),
}
EXPECTED_KIND = {"request": "browser_request", "result": "browser_result"}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_required(obj, required, where, errors):
    if not isinstance(obj, dict):
        errors.append("%s: expected an object" % where)
        return
    for field in required:
        if field not in obj:
            errors.append("%s: missing required field '%s'" % (where, field))


def check_enum(schema_props, field, value, errors):
    spec = schema_props.get(field, {})
    if "enum" in spec and value not in spec["enum"]:
        errors.append("field '%s': %r is not one of %s" % (field, value, spec["enum"]))
    if "const" in spec and value != spec["const"]:
        errors.append("field '%s': must be %r, got %r" % (field, spec["const"], value))


def validate(kind, pkg):
    errors = []
    schema = load_json(SCHEMAS[kind])
    props = schema.get("properties", {})

    check_required(pkg, schema.get("required", []), "package", errors)
    if not isinstance(pkg, dict):
        return errors

    # kind must match the file's declared purpose
    if pkg.get("kind") != EXPECTED_KIND[kind]:
        errors.append("field 'kind': must be %r for a %s package, got %r"
                      % (EXPECTED_KIND[kind], kind, pkg.get("kind")))

    # enum / const checks on the fields the connector depends on
    for field in ("schema_version", "source_platform", "action_type", "status"):
        if field in pkg and field in props:
            check_enum(props, field, pkg[field], errors)

    # nested required blocks
    for block in ("authorization", "permissions", "target",
                  "conversation_reference"):
        if block in pkg and block in props:
            sub_required = props[block].get("required", [])
            if sub_required:
                check_required(pkg.get(block), sub_required,
                               "block '%s'" % block, errors)

    # permissions hard consts (checked even if the block shape is odd)
    perms = pkg.get("permissions")
    if isinstance(perms, dict):
        if perms.get("credentials_in_packages") is not False:
            errors.append("hard rule: permissions.credentials_in_packages must be false")
        if perms.get("irreversibles_require_user_word") is not True:
            errors.append("hard rule: permissions.irreversibles_require_user_word must be true")
    if pkg.get("credentials_in_packages") is not None \
            and pkg.get("credentials_in_packages") is not False:
        errors.append("hard rule: top-level credentials_in_packages must be false if present")

    # account_hint is an identifier only — flag credential-like content
    hint = pkg.get("account_hint")
    if isinstance(hint, str):
        lowered = hint.lower()
        for marker in ("password", "passwd", "secret", "token", "otp", "code:"):
            if marker in lowered:
                errors.append("hard rule: account_hint looks like it carries a "
                              "credential (contains %r); identifiers only" % marker)
                break

    # result packages: a 'completed' send/purchase-style claim needs confirmations
    if kind == "result" and pkg.get("status") == "completed":
        if not pkg.get("confirmations"):
            errors.append("result with status 'completed' must carry at least one "
                          "confirmation (an empty list establishes nothing)")

    return errors


def main(argv):
    if len(argv) != 3 or argv[1] not in SCHEMAS:
        print("usage: validate.py request|result <package.json>")
        return 2
    kind, path = argv[1], argv[2]
    try:
        pkg = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        print("FAIL %s: cannot read package: %s" % (path, exc))
        return 2
    errors = validate(kind, pkg)
    if errors:
        print("FAIL %s (%s package): %d problem(s)" % (path, kind, len(errors)))
        for err in errors:
            print("  - %s" % err)
        return 1
    print("PASS %s (%s package): required fields, enums, and hard rules OK"
          % (path, kind))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
