"""ScheduledTask CRUD 操作。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduled_task import ScheduledTask


async def get_by_id(db: AsyncSession, id: int) -> ScheduledTask | None:
    return await db.get(ScheduledTask, id)


async def get_due_tasks(db: AsyncSession, now: datetime) -> list[ScheduledTask]:
    stmt = (
        select(ScheduledTask)
        .where(ScheduledTask.next_run_at <= now, ScheduledTask.enabled == 1)
        .order_by(ScheduledTask.next_run_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def add(db: AsyncSession, obj: ScheduledTask) -> ScheduledTask:
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def update(db: AsyncSession, obj: ScheduledTask) -> bool:
    await db.commit()
    return True


async def delete(db: AsyncSession, id: int) -> bool:
    obj = await db.get(ScheduledTask, id)
    if obj is None:
        return False
    await db.delete(obj)
    await db.commit()
    return True


async def list_tasks(
    db: AsyncSession,
    test_case_id: int | None = None,
    enabled: int | None = None,
    offset: int = 0,
    limit: int = 10,
) -> list[ScheduledTask]:
    stmt = select(ScheduledTask)
    if test_case_id is not None:
        stmt = stmt.where(ScheduledTask.test_case_id == test_case_id)
    if enabled is not None:
        stmt = stmt.where(ScheduledTask.enabled == enabled)
    stmt = stmt.order_by(ScheduledTask.id.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count(
    db: AsyncSession,
    test_case_id: int | None = None,
    enabled: int | None = None,
) -> int:
    stmt = select(func.count()).select_from(ScheduledTask)
    if test_case_id is not None:
        stmt = stmt.where(ScheduledTask.test_case_id == test_case_id)
    if enabled is not None:
        stmt = stmt.where(ScheduledTask.enabled == enabled)
    result = await db.execute(stmt)
    return result.scalar_one() or 0


async def get_by_test_case_id(db: AsyncSession, test_case_id: int) -> list[ScheduledTask]:
    stmt = (
        select(ScheduledTask)
        .where(ScheduledTask.test_case_id == test_case_id)
        .order_by(ScheduledTask.id.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
