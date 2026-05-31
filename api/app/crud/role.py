"""Role CRUD helpers."""

from __future__ import annotations

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Role, RolePermission


async def get_by_id(db: AsyncSession, id: int) -> Role | None:
    return await db.get(Role, id)


async def get_by_code(db: AsyncSession, code: str) -> Role | None:
    stmt = select(Role).where(Role.code == code)
    return (await db.execute(stmt)).scalar_one_or_none()


async def add(db: AsyncSession, role: Role) -> Role:
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


async def update(db: AsyncSession, role: Role) -> bool:
    await db.commit()
    return True


async def delete(db: AsyncSession, id: int) -> bool:
    await db.execute(sql_delete(RolePermission).where(RolePermission.role_id == id))
    result = await db.execute(sql_delete(Role).where(Role.id == id))
    await db.commit()
    return result.rowcount > 0


async def count(db: AsyncSession, name: str | None = None, code: str | None = None) -> int:
    stmt = select(func.count()).select_from(Role)
    if name is not None:
        stmt = stmt.where(Role.name.like(f"%{name}%"))
    if code is not None:
        stmt = stmt.where(Role.code.like(f"%{code}%"))
    return (await db.execute(stmt)).scalar_one() or 0


async def list_roles(
    db: AsyncSession,
    name: str | None,
    code: str | None,
    offset: int,
    limit: int,
) -> list[Role]:
    stmt = select(Role)
    if name is not None:
        stmt = stmt.where(Role.name.like(f"%{name}%"))
    if code is not None:
        stmt = stmt.where(Role.code.like(f"%{code}%"))
    stmt = stmt.order_by(Role.id.asc()).offset(offset).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def list_permissions(db: AsyncSession, role_id: int) -> list[str]:
    stmt = select(RolePermission.permission_code).where(RolePermission.role_id == role_id)
    return list((await db.execute(stmt)).scalars().all())


async def replace_permissions(db: AsyncSession, role_id: int, permissions: list[str]) -> bool:
    await db.execute(sql_delete(RolePermission).where(RolePermission.role_id == role_id))
    for code in permissions:
        db.add(RolePermission(role_id=role_id, permission_code=code))
    await db.commit()
    return True
