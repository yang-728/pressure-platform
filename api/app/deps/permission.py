"""Permission dependencies for menu-level RBAC."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.codes import Codes
from app.core.context import UserContext
from app.core.exceptions import MysteriousException
from app.core.permissions import ADMIN_ROLE_CODE
from app.crud import role as role_crud
from app.db.session import get_db
from app.deps.auth import get_current_user_dep


async def get_current_permissions(db: AsyncSession, current: UserContext) -> list[str]:
    if current.role_code == ADMIN_ROLE_CODE:
        from app.core.permissions import ALL_PERMISSION_CODES

        return ALL_PERMISSION_CODES
    if not current.role_id:
        return []
    return await role_crud.list_permissions(db, current.role_id)


def require_permission(permission: str):
    async def _dep(
        current: UserContext = Depends(get_current_user_dep),
        db: AsyncSession = Depends(get_db),
    ) -> UserContext:
        if current.role_code == ADMIN_ROLE_CODE:
            return current
        permissions = await get_current_permissions(db, current)
        if permission not in permissions:
            raise MysteriousException(Codes.FAIL, message="无权访问该模块")
        return current

    return _dep


def require_any_permission(*required_permissions: str):
    async def _dep(
        current: UserContext = Depends(get_current_user_dep),
        db: AsyncSession = Depends(get_db),
    ) -> UserContext:
        if current.role_code == ADMIN_ROLE_CODE:
            return current
        permissions = await get_current_permissions(db, current)
        if not any(permission in permissions for permission in required_permissions):
            raise MysteriousException(Codes.FAIL, message="无权访问该模块")
        return current

    return _dep
