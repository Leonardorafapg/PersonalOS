"""Password hashing (stdlib scrypt) and non-expiring JWTs.

Tokens deliberately carry no `exp`: they stay valid until the owner bumps `token_version`
(Settings > "Revogar todos os acessos") or changes the password.
"""

import base64
import hashlib
import hmac
import os
import time

import jwt

from app.core.config import get_settings

ALGO = "HS256"
_N, _R, _P = 2**14, 8, 1


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, dk = stored.split("$")
        if scheme != "scrypt":
            return False
        calc = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except Exception:  # noqa: BLE001
        return False


def create_token(user_id: int, token_version: int, typ: str = "access", **extra) -> str:
    claims = {"sub": str(user_id), "tv": token_version, "typ": typ, "iat": int(time.time()), **extra}
    return jwt.encode(claims, get_settings().jwt_secret, algorithm=ALGO)


def decode_token(token: str, *, expected_typ: str | None = "access") -> dict | None:
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[ALGO],
            options={"verify_exp": False, "require": ["sub", "tv", "typ"]},
        )
    except jwt.PyJWTError:
        return None
    if expected_typ and claims.get("typ") != expected_typ:
        return None
    return claims


def create_short_token(typ: str, ttl_seconds: int, **claims) -> str:
    """Short-lived signed blob (OAuth authorization codes, dynamic client ids)."""
    payload = {"typ": typ, "iat": int(time.time()), "exp": int(time.time()) + ttl_seconds, **claims}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=ALGO)


def decode_short_token(token: str, typ: str) -> dict | None:
    try:
        claims = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
    return claims if claims.get("typ") == typ else None
