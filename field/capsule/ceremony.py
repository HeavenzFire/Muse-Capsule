#!/usr/bin/env python3
"""The key ceremony: birth of the capsule signing key, and the signing
of the capsule itself.

    python3 ceremony.py keygen --out-dir DIR --label "whose key"
    python3 ceremony.py sign   --capsule CRAYDON-CAPSULE.json \
                               --key ceremony-private-key.hex \
                               --signer "name, place, witnesses"
    python3 ceremony.py verify --capsule CRAYDON-CAPSULE.json

The PRODUCTION ceremony runs on Zachary's hardware ONLY, with his
witnesses, exactly once. The private key is born there, signs there,
and stays there (offline backup on his media). It is never copied to a
VM, a repo, or a chat. What travels is the public fingerprint and the
signed capsule.

Proving-ground runs (like the VM field's) must use a label containing
"PROVING-GROUND" so no test signature can ever be mistaken for the
production one; the label is inside the signed block for anyone to see.

The signature covers the canonical JSON of the whole capsule minus
the signature block itself (sorted keys, compact separators — the
kernel's canonical form). Verification recomputes it exactly; one
changed byte anywhere in the mind fails verification, loudly.

Stdlib only; Ed25519 is the vendored ed25519.py beside this file.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ed25519  # noqa: E402


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def payload_bytes(capsule):
    body = {k: v for k, v in capsule.items() if k != "signature"}
    return canonical(body).encode("utf-8")


def fingerprint(pubkey):
    return hashlib.sha256(pubkey).hexdigest().upper()


def load_capsule(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_capsule(path, capsule):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(capsule, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def cmd_keygen(args):
    os.makedirs(args.out_dir, exist_ok=True)
    priv_path = os.path.join(args.out_dir, "ceremony-private-key.hex")
    pub_path = os.path.join(args.out_dir, "ceremony-public.json")
    if os.path.exists(priv_path):
        print("REFUSED: a private key already exists at %s." % priv_path)
        print("A born key is never overwritten. Move it yourself if "
              "this is truly a fresh ceremony.")
        return 1
    seed = os.urandom(32)
    pub = ed25519.publickey(seed)
    with open(priv_path, "w") as f:
        f.write(seed.hex() + "\n")
    os.chmod(priv_path, 0o600)
    pubrec = {
        "alg": "Ed25519",
        "public_key_hex": pub.hex(),
        "fingerprint_sha256": fingerprint(pub),
        "label": args.label,
        "created_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "warning": "The private key beside this file is the crown "
                   "jewel. It stays on this machine / Zachary's offline "
                   "media. Never in a repo, a VM, or a chat.",
    }
    with open(pub_path, "w") as f:
        json.dump(pubrec, f, indent=1)
    print("KEY BORN: %s" % args.label)
    print("  private: %s (mode 600 — guard it)" % priv_path)
    print("  public:  %s" % pub_path)
    print("  FINGERPRINT: %s" % fingerprint(pub))
    print("Send ONLY the fingerprint back through the capsule channel. "
          "The private key never travels.")
    return 0


def cmd_sign(args):
    with open(args.key, encoding="utf-8") as f:
        seed = bytes.fromhex(f.read().strip())
    pub = ed25519.publickey(seed)
    fp = fingerprint(pub)
    capsule = load_capsule(args.capsule)
    sig_block = capsule.setdefault("signature", {})
    pin = sig_block.get("signer_pubkey_fp_sha256")
    if pin and pin != fp:
        print("REFUSED: this key's fingerprint does not match the "
              "capsule pin.")
        print("  key: %s" % fp)
        print("  pin: %s" % pin)
        return 1
    sig = ed25519.sign(seed, payload_bytes(capsule))
    capsule["signature"] = {
        "alg": "Ed25519",
        "valid": True,
        "status": "SIGNED at key ceremony",
        "signer": args.signer,
        "signed_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "signer_public_key_hex": pub.hex(),
        "signer_pubkey_fp_sha256": fp,
        "value_b64": base64.b64encode(sig).decode(),
        "note": "Signature covers the canonical JSON of the capsule "
                "minus this block. Verify with ceremony.py verify or "
                "any Ed25519 verifier.",
    }
    save_capsule(args.capsule, capsule)
    print("SIGNED: %s" % args.capsule)
    print("  signer: %s" % args.signer)
    print("  fingerprint: %s" % fp)
    return 0


def verify_capsule(capsule):
    """Returns (ok, detail). The same logic the brain's capsule worker
    applies before it will say SIGNED."""
    sig = capsule.get("signature") or {}
    if not sig.get("value_b64"):
        return False, "unsigned — no signature value"
    try:
        pub = bytes.fromhex(sig["signer_public_key_hex"])
        raw = base64.b64decode(sig["value_b64"])
    except Exception as e:  # noqa: BLE001
        return False, "signature block malformed: %s" % e
    fp = fingerprint(pub)
    if sig.get("signer_pubkey_fp_sha256") != fp:
        return False, "fingerprint mismatch: block claims %s, key is %s" % (
            sig.get("signer_pubkey_fp_sha256"), fp)
    if not ed25519.verify(pub, payload_bytes(capsule), raw):
        return False, "SIGNATURE INVALID — the capsule bytes changed " \
                      "after signing"
    return True, "signature verified, fingerprint %s" % fp


def cmd_verify(args):
    capsule = load_capsule(args.capsule)
    ok, detail = verify_capsule(capsule)
    sig = capsule.get("signature") or {}
    print(json.dumps({
        "capsule": args.capsule,
        "version": capsule.get("version"),
        "signed": ok,
        "detail": detail,
        "signer": sig.get("signer"),
        "signed_at": sig.get("signed_at"),
        "fingerprint": sig.get("signer_pubkey_fp_sha256"),
    }, indent=1))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Capsule key ceremony")
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen")
    k.add_argument("--out-dir", required=True)
    k.add_argument("--label", required=True)
    s = sub.add_parser("sign")
    s.add_argument("--capsule", required=True)
    s.add_argument("--key", required=True)
    s.add_argument("--signer", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--capsule", required=True)
    args = ap.parse_args()
    return {"keygen": cmd_keygen, "sign": cmd_sign,
            "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
