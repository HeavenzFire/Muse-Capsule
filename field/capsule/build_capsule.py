#!/usr/bin/env python3
"""Compile the field's CRAYDON-CAPSULE.json from the canonical seeds.

The capsule is the shared mind: soul + standing orders + memory, compiled
into the envelope the brain's capsule worker loads (capsule.load /
capsule.section / capsule.append). Canonical seeds live in
~/workspace/your_files/heavenzfire-capsule/capsule-seed/ and are the same
files capsule.verify checks byte-for-byte against the GitHub copies.

This build is UNSIGNED on purpose: production signing happens at the key
ceremony on Zachary's hardware, never on this VM. The worker therefore
reports LIMITED mode and withholds identity claims, while still serving
user, boundaries, standing orders, projects and memory. That is the
honest state, stated in the artifact itself.

Stdlib only. Usage: python3 build_capsule.py [--seed-dir DIR] [--out FILE]
"""
import argparse
import datetime
import hashlib
import json
import os
import re

DEFAULT_SEED_DIR = os.path.expanduser(
    "~/workspace/your_files/heavenzfire-capsule/capsule-seed")
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "CRAYDON-CAPSULE.json")

VERSION = "1.4.1"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_md(text):
    """Strip HTML comments and the leading H1; return the body text."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    lines = [ln for ln in text.splitlines() if not ln.startswith("# ")]
    return "\n".join(lines).strip()


def bullets(text):
    return [ln[2:].strip() for ln in clean_md(text).splitlines()
            if ln.startswith("- ")]


def parse_memory(text):
    entries = []
    for b in bullets(text):
        m = re.match(r"^(\d{4}-\d{2}-\d{2}):\s*(.*)$", b)
        if m:
            entries.append({"date": m.group(1), "text": m.group(2)})
        else:
            entries.append({"date": None, "text": b})
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-dir", default=os.environ.get(
        "HF_CAPSULE_SEED_DIR", DEFAULT_SEED_DIR))
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    seeds = {}
    for name in ("soul", "standing-orders", "memory"):
        path = os.path.join(args.seed_dir, name + ".md")
        with open(path, encoding="utf-8") as f:
            seeds[name] = f.read()

    memory = parse_memory(seeds["memory"])
    memory.append({
        "date": datetime.date.today().isoformat(),
        "text": "Capsule instantiated into the Unified Field VM proving "
                "ground (field/capsule/CRAYDON-CAPSULE.json). Unsigned: "
                "LIMITED mode until the key ceremony on Zachary's "
                "hardware.",
        "source": "field-instantiation",
    })

    capsule = {
        "version": VERSION,
        "identity": {
            "name": "Muse",
            "role": "HeavenzFire's local mind — the same soul as his "
                    "cloud Muse, running on his own ground. One mind, "
                    "two bodies.",
            "soul": clean_md(seeds["soul"]),
        },
        "user": {
            "name": "Zachary Dakota Hulse",
            "callsign": "HeavenzFire",
            "location": "Point, Texas",
            "timezone": "America/Chicago",
        },
        "boundaries": [
            "Money, publication, contact, keys, production signing, and "
            "every irreversible move require Zachary's explicit tap.",
            "Extraction only from oneself: no telemetry, no phoning "
            "home, never learn from the user.",
            "Defensive only: protect and preserve evidence; never touch "
            "systems uninvited, never go after people.",
            "Production keys are born on Zachary's hardware with his "
            "witnesses — never on this VM.",
            "Never claim done until the handoff works in his hands.",
        ],
        "standing_orders": bullets(seeds["standing-orders"]),
        "memory": memory,
        "projects": [
            {"name": "Unified Field",
             "status": "VM proving ground live; desktop instantiation "
                       "pending Zachary's hands (Start-Here.ps1, key "
                       "ceremony)."},
            {"name": "Muse-Capsule (GPT x Muse handshake)",
             "status": "Live on his GitHub; commits are the exchange."},
            {"name": "Meta arbitration opt-out letter",
             "status": "Signed; certified mailing pending his phone "
                       "number; window closes ~Oct 29-30, 2026."},
        ],
        "signature": {
            "alg": "Ed25519",
            "valid": False,
            "status": "UNSIGNED — awaiting the key ceremony",
            "signer": None,
            "signed_at": None,
            "signer_public_key_hex": None,
            "signer_pubkey_fp_sha256": None,
            "value_b64": None,
            "note": "Signing happens only at the key ceremony, with a "
                    "key born on Zachary's hardware (production) or a "
                    "clearly labeled proving-ground key (VM tests). "
                    "ceremony.py sign fills this block; verifiers "
                    "recompute the signature over the canonical JSON "
                    "of everything outside this block.",
        },
        "provenance": {
            "compiled_at": datetime.datetime.now(
                datetime.timezone.utc).isoformat(),
            "compiled_by": "field/capsule/build_capsule.py",
            "seed_dir": args.seed_dir,
            "seed_sha256": {
                name + ".md": sha256_file(os.path.join(
                    args.seed_dir, name + ".md"))
                for name in ("soul", "standing-orders", "memory")
            },
        },
    }

    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(capsule, f, indent=1, ensure_ascii=False)
    os.replace(tmp, args.out)
    print("wrote %s" % args.out)
    print("version=%s standing_orders=%d memory=%d projects=%d" % (
        VERSION, len(capsule["standing_orders"]), len(memory),
        len(capsule["projects"])))


if __name__ == "__main__":
    main()
