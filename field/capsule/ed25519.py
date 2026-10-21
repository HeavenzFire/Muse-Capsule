"""Pure-Python Ed25519 (RFC 8032) — sign and verify, stdlib only.

Vendored into the field so the key ceremony runs identically everywhere
Zachary's systems run: this VM (proving ground), his Windows machine
(production ceremony), the local agent. No pip, no openssl dependency,
no version drift between sign-time and verify-time — the same file
does both, forever.

Point arithmetic uses extended coordinates (Hisil et al.), one
inversion per encode/decode. Verification takes well under a second.
This is ceremony-grade code: it signs one capsule and verifies on
load. It is NOT constant-time and must never be used where timing
side channels matter — the private key never lives on a server; it is
born on Zachary's hardware, used once per ceremony, and kept offline.

API:
    publickey(seed32) -> pubkey32
    sign(seed32, msg_bytes) -> sig64
    verify(pubkey32, msg_bytes, sig64) -> bool
"""
import hashlib

q = 2 ** 255 - 19
l = 2 ** 252 + 27742317777372353535851937790883648493


def _sha512(m):
    return hashlib.sha512(m).digest()


def _inv(x):
    return pow(x, q - 2, q)


_d = (-121665 * _inv(121666)) % q
_I = pow(2, (q - 1) // 4, q)  # sqrt(-1) mod q


def _xrecover(y):
    xx = (y * y - 1) * _inv(_d * y * y + 1) % q
    x = pow(xx, (q + 3) // 8, q)
    if (x * x - xx) % q != 0:
        x = (x * _I) % q
    if x & 1:
        x = q - x
    return x


# Base point, extended coordinates (X, Y, Z, T).
_By = (4 * _inv(5)) % q
_Bx = _xrecover(_By)
B = (_Bx, _By, 1, (_Bx * _By) % q)
_IDENTITY = (0, 1, 1, 0)


def _point_add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % q
    Bv = (P[1] + P[0]) * (Q[1] + Q[0]) % q
    C = 2 * _d * P[3] * Q[3] % q
    D = 2 * P[2] * Q[2] % q
    E = (Bv - A) % q
    F = (D - C) % q
    G = (D + C) % q
    H = (Bv + A) % q
    return (E * F % q, G * H % q, F * G % q, E * H % q)


def _point_double(P):
    A = P[0] * P[0] % q
    Bv = P[1] * P[1] % q
    C = 2 * P[2] * P[2] % q
    D = (-A) % q
    E = ((P[0] + P[1]) ** 2 - A - Bv) % q
    G = (D + Bv) % q
    F = (G - C) % q
    H = (D - Bv) % q
    return (E * F % q, G * H % q, F * G % q, E * H % q)


def _scalarmult(P, e):
    Q = _IDENTITY
    bits = bin(e)[2:][::-1]
    cur = P
    for bit in bits:
        if bit == "1":
            Q = _point_add(Q, cur)
        cur = _point_double(cur)
    return Q


def _encode_point(P):
    zinv = _inv(P[2])
    x = P[0] * zinv % q
    y = P[1] * zinv % q
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _decode_point(s):
    if len(s) != 32:
        raise ValueError("bad point length")
    bits = int.from_bytes(s, "little")
    y = bits & ((1 << 255) - 1)
    sign = (bits >> 255) & 1
    if y >= q:
        raise ValueError("point y out of range")
    x = _xrecover(y)
    if (x & 1) != sign:
        x = q - x
    return (x, y, 1, x * y % q)


def _hint(m):
    return int.from_bytes(_sha512(m), "little")


def _prune(h32):
    a = bytearray(h32)
    a[0] &= 248
    a[31] &= 63
    a[31] |= 64
    return int.from_bytes(a, "little")


def publickey(seed):
    if len(seed) != 32:
        raise ValueError("seed must be 32 bytes")
    h = _sha512(seed)
    a = _prune(h[:32])
    return _encode_point(_scalarmult(B, a))


def sign(seed, msg):
    if len(seed) != 32:
        raise ValueError("seed must be 32 bytes")
    h = _sha512(seed)
    a = _prune(h[:32])
    prefix = h[32:]
    A = _encode_point(_scalarmult(B, a))
    r = _hint(prefix + msg) % l
    R = _encode_point(_scalarmult(B, r))
    k = _hint(R + A + msg) % l
    S = (r + k * a) % l
    return R + S.to_bytes(32, "little")


def verify(pubkey, msg, sig):
    if len(pubkey) != 32 or len(sig) != 64:
        return False
    try:
        A = _decode_point(pubkey)
        R = _decode_point(sig[:32])
    except ValueError:
        return False
    S = int.from_bytes(sig[32:], "little")
    if S >= l:
        return False
    k = _hint(sig[:32] + pubkey + msg) % l
    # Equation: [S]B == R + [k]A — compared by encoding.
    left = _encode_point(_scalarmult(B, S))
    right = _encode_point(_point_add(R, _scalarmult(A, k)))
    return left == right
