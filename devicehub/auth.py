"""Password e sessioni, solo con la libreria standard.

Niente segreto hardcoded (il difetto del vecchio codice): la chiave di firma
arriva da `DEVICEHUB_SESSION_SECRET`, altrimenti viene generata a runtime e le
sessioni decadono al riavvio.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

COOKIE_NAME = "dh_session"
PBKDF2_ROUNDS = 240_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def sign_session(payload: dict, secret: str, ttl_seconds: int) -> str:
    body = dict(payload, exp=int(time.time()) + ttl_seconds)
    raw = _b64(json.dumps(body, separators=(",", ":")).encode())
    mac = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{mac}"


def read_session(token: str, secret: str) -> dict | None:
    try:
        raw, mac = token.split(".", 1)
        expected = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            return None
        data = json.loads(_unb64(raw))
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        return data
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def random_secret() -> str:
    return secrets.token_urlsafe(32)
