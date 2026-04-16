from __future__ import annotations

import hashlib
import secrets
import uuid


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        120_000,
    )
    return digest.hex(), salt


def verify_password(password: str, expected_hash: str, salt: str) -> bool:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        120_000,
    )
    return secrets.compare_digest(digest.hex(), expected_hash)


def new_session_token() -> str:
    return uuid.uuid4().hex
