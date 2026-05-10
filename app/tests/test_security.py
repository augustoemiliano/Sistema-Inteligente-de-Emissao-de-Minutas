from __future__ import annotations

import bcrypt

from app.core.security import hash_password, verify_password


def test_password_roundtrip() -> None:
    hashed = hash_password("senha-forte-123")
    assert verify_password("senha-forte-123", hashed) is True
    assert verify_password("outra", hashed) is False


def test_password_copy_paste_newline_matches_login_without() -> None:
    """Registro com \\n final (comum ao colar senha) deve autenticar sem o \\n no login."""
    hashed = hash_password("SenhaForte8!\n")
    assert verify_password("SenhaForte8!", hashed) is True


def test_password_bom_prefix_stripped() -> None:
    hashed = hash_password("\ufeffsecretpass12")
    assert verify_password("secretpass12", hashed) is True


def test_legacy_hash_with_newline_login_with_same_string() -> None:
    """Hashes antigos gerados com \\n no texto bruto ainda autenticam se o cliente enviar igual."""
    raw = "SenhaForte8!\n"
    legacy = bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt(rounds=4)).decode("utf-8")
    assert verify_password(raw, legacy) is True
