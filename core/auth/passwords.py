"""scrypt password hashes, from the standard library. Format: scrypt$n$r$p$salt_hex$hash_hex."""

import hashlib
import hmac
import secrets

N, R, P = 2**14, 8, 1
DKLEN = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=DKLEN)
    return f"scrypt${N}${R}${P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    actual = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(digest) // 2
    )
    return hmac.compare_digest(actual.hex(), digest)
