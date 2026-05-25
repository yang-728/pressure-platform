"""Scheduled task execution log CRUD."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduled_task_log import ScheduledTaskLog


async def add(db: AsyncSession, obj: ScheduledTaskLog) -> ScheduledTaskLog:
    db.add(obj)
    await db.flush()
    return obj


async def list_logs(
    db: AsyncSession,
    scheduled_task_id: int | None,
    test_case_id: int | None,
    status: str | None,
    offset: int,
    limit: int,
) -> list[ScheduledTaskLog]:
    stmt = select(ScheduledTaskLog)
    if scheduled_task_id is not None:
        stmt = stmt.where(ScheduledTaskLog.scheduled_task_id == scheduled_task_id)
    if test_case_id is not None:
        stmt = stmt.where(ScheduledTaskLog.test_case_id == test_case_id)
    if status:
        stmt = stmt.where(ScheduledTaskLog.status == status)
    stmt = stmt.order_by(ScheduledTaskLog.trigger_time.desc(), ScheduledTaskLog.id.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count(
    db: AsyncSession,
    scheduled_task_id: int | None,
    test_case_id: int | None,
    status: str | None,
) -> int:
    stmt = select(func.count()).select_from(ScheduledTaskLog)
    if scheduled_task_id is not None:
        stmt = stmt.where(ScheduledTaskLog.scheduled_task_id == scheduled_task_id)
    if test_case_id is not None:
        stmt = stmt.where(ScheduledTaskLog.test_case_id == test_case_id)
    if status:
        stmt = stmt.where(ScheduledTaskLog.status == status)
    result = await db.execute(stmt)
    return result.scalar_one() or 0
