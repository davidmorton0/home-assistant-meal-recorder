"""Password hashing for the ingest credential.

Only a salted hash of the password is stored, because config entry data is
kept in plain text.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
DKLEN = 32


def hash_password(password: str) -> dict[str, Any]:
    """Return a storable hash record for a password."""
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=DKLEN
    )
    return {
        "algorithm": "scrypt",
        "salt": salt.hex(),
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
        "dklen": DKLEN,
        "hash": digest.hex(),
    }


def verify_password(password: str, record: dict[str, Any]) -> bool:
    """Verify a password against a stored hash record, in constant time."""
    try:
        digest = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(record["salt"]),
            n=int(record["n"]),
            r=int(record["r"]),
            p=int(record["p"]),
            dklen=int(record["dklen"]),
        )
    except (KeyError, ValueError):
        return False
    return hmac.compare_digest(digest.hex(), str(record.get("hash", "")))


def verify_username(username: str, expected: str) -> bool:
    """Compare usernames in constant time."""
    return hmac.compare_digest(username, expected)
