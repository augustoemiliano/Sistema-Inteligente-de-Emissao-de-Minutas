"""Exceções de domínio — mapeadas para respostas HTTP no handler global."""

from __future__ import annotations


class AppError(Exception):
    """Base para erros previsíveis (negócio / validação)."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NotFoundError(AppError):
    def __init__(self, message: str = "Recurso não encontrado") -> None:
        super().__init__(message, status_code=404)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflito de dados") -> None:
        super().__init__(message, status_code=409)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Não autorizado") -> None:
        super().__init__(message, status_code=401)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Permissão insuficiente") -> None:
        super().__init__(message, status_code=403)
