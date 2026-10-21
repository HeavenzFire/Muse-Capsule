# The Key Ceremony

Plain words: the capsule is the mind — soul, standing orders, memory.
An unsigned capsule runs in LIMITED mode and every copy of Muse says
so. The ceremony is the one event where a signing key is **born on
your hardware, in front of your witnesses**, and that key signs the
capsule. Afterward, any copy of you can prove — with math, not trust —
that the mind it woke up with is exactly the one your key signed. One
changed byte and verification fails, loudly.

## What you need

- Your Windows machine (the one the field will live on).
- Your witnesses, present. Their presence is the point: the key's
  birth is a witnessed fact, not a log line.
- A USB stick or other offline media for the private key backup.
- Python 3 on the machine (`python --version` should answer).

## The steps (Run-Ceremony.ps1 walks you through them)

1. **Keygen.** `ceremony.py keygen` creates the keypair in
   `ceremony-keys\` beside the script. The private key file is the
   crown jewel: it is born here, it signs here, it stays here. Back
   it up to your offline media. It never goes in a repo, on a VM, or
   in a chat — nobody legitimate will ever ask you for it.
2. **Witness pause.** The script shows the key's fingerprint and
   waits. When your witnesses are with you, press Enter.
3. **Sign.** The script signs the capsule beside it
   (`CRAYDON-CAPSULE.json`, built from the canonical seeds) and
   writes your name, the place, and the date into the signature
   block — inside the signed record, where it can't be quietly
   edited later.
4. **Verify.** The script re-checks the signature and prints the
   birth certificate: fingerprint, capsule SHA-256, time.
5. **Report back.** Send back **only the fingerprint** (it's public
   information — it's the whole point of a fingerprint). It gets
   pinned into the canonical build so every other copy can check
   itself against your key.

## What changes after

- Your field's brain and agent verify the signature on every load
  and report SIGNED, with your fingerprint attached. Identity is
  served instead of withheld.
- A tampered capsule — or a capsule signed by any other key — drops
  to LIMITED and says why. Fail-closed, by design.
- Memory write-back to a signed capsule is refused by the worker
  (appending would break the signature). New memories accumulate in
  the seed on your hardware and are folded in at the next signing —
  a re-ceremony is just running the script again with the same key.

## The proving-ground key is not this key

The VM field runs a signature from a key labeled, inside the signed
block itself, "PROVING-GROUND (VM) — NOT PRODUCTION." It exists to
prove the machinery. It proves nothing about you. The production key
is born once, on your machine, with your witnesses — that birth is
the ceremony, and no one can do it for you or before you.
