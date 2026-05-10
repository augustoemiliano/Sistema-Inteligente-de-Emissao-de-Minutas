"""JWT (access) + tokens opacos para refresh — revogação simples no banco."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import Settings, get_settings


def normalize_password_plain(password: str) -> str:
    """Alinha cadastro e login — copiar/colar costuma incluir \\r\\n ou BOM no campo."""
    return password.removeprefix("\ufeff").strip("\r\n")


def hash_password(password: str) -> str:
    password = normalize_password_plain(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    h = hashed.strip()
    if not h.startswith("$2"):
        return False
    normalized = normalize_password_plain(plain)
    candidates = [normalized]
    if plain != normalized:
        candidates.append(plain)
    for candidate in candidates:
        try:
            if bcrypt.checkpw(candidate.encode("utf-8"), h.encode("utf-8")):
                return True
        except ValueError:
            continue
    return False


def generate_refresh_token_value() -> str:
    # Token opaco: cliente só manda de volta; persistimos só o hash
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(
    subject: str | UUID,
    settings: Settings | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = settings or get_settings()
    expire = _now() + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": "access",
        "exp": expire,
        "iat": _now(),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Token inválido") from exc
    if data.get("type") != "access":
        raise ValueError("Token inválido")
    return data
