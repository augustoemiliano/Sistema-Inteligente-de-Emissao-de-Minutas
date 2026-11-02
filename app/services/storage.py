"""Acesso a arquivos com proteção contra path traversal.

Regra: o banco guarda apenas caminhos RELATIVOS gerados pelo servidor; toda leitura/escrita
passa por `safe_join`, que garante que o caminho final continua dentro do diretório base.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.core.exceptions import AppError


class UnsafePathError(AppError):
    def __init__(self) -> None:
        super().__init__("Caminho de arquivo inválido", status_code=400)


def safe_join(base_dir: Path, relative: str) -> Path:
    if not relative or os.path.isabs(relative) or "\x00" in relative:
        raise UnsafePathError()
    base = base_dir.resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base) or target == base:
        raise UnsafePathError()
    return target


def write_bytes_atomic(base_dir: Path, relative: str, data: bytes) -> Path:
    target = safe_join(base_dir, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return target
