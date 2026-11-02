from __future__ import annotations

from pydantic import BaseModel

from app.models.user import UserRole


class UserAdminUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
