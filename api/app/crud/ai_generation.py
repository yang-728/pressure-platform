"""CRUD helpers for AI generation tasks and artifacts."""

from __future__ import annotations

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_generation import AiGenerationArtifact, AiGenerationTask


async def add_task(db: AsyncSession, obj: AiGenerationTask) -> AiGenerationTask:
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def update_task(db: AsyncSession, obj: AiGenerationTask) -> bool:
    await db.commit()
    await db.refresh(obj)
    return True


async def get_task(db: AsyncSession, id: int) -> AiGenerationTask | None:
    return await db.get(AiGenerationTask, id)


def _apply_task_filters(
    stmt,
    *,
    task_name: str | None = None,
    generation_type: str | None = None,
    status: str | None = None,
    creator: str | None = None,
):
    if task_name:
        stmt = stmt.where(AiGenerationTask.task_name.like(f"%{task_name}%"))
    if generation_type:
        stmt = stmt.where(AiGenerationTask.generation_type == generation_type)
    if status:
        stmt = stmt.where(AiGenerationTask.status == status)
    if creator:
        stmt = stmt.where(AiGenerationTask.creator.like(f"%{creator}%"))
    return stmt


async def count_tasks(
    db: AsyncSession,
    *,
    task_name: str | None = None,
    generation_type: str | None = None,
    status: str | None = None,
    creator: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(AiGenerationTask)
    stmt = _apply_task_filters(
        stmt,
        task_name=task_name,
        generation_type=generation_type,
        status=status,
        creator=creator,
    )
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def list_tasks(
    db: AsyncSession,
    *,
    task_name: str | None = None,
    generation_type: str | None = None,
    status: str | None = None,
    creator: str | None = None,
    offset: int = 0,
    limit: int = 10,
) -> list[AiGenerationTask]:
    stmt = select(AiGenerationTask)
    stmt = _apply_task_filters(
        stmt,
        task_name=task_name,
        generation_type=generation_type,
        status=status,
        creator=creator,
    )
    stmt = stmt.order_by(AiGenerationTask.create_time.desc(), AiGenerationTask.id.desc())
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def add_artifact(db: AsyncSession, obj: AiGenerationArtifact) -> AiGenerationArtifact:
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def list_artifacts(db: AsyncSession, task_id: int) -> list[AiGenerationArtifact]:
    stmt = (
        select(AiGenerationArtifact)
        .where(AiGenerationArtifact.task_id == task_id)
        .order_by(AiGenerationArtifact.id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_artifacts_by_ids(
    db: AsyncSession,
    *,
    task_id: int,
    artifact_ids: list[int],
) -> list[AiGenerationArtifact]:
    if not artifact_ids:
        return []
    stmt = (
        select(AiGenerationArtifact)
        .where(AiGenerationArtifact.task_id == task_id)
        .where(AiGenerationArtifact.id.in_(artifact_ids))
        .order_by(AiGenerationArtifact.id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_artifacts(db: AsyncSession, task_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(AiGenerationArtifact).where(AiGenerationArtifact.task_id == task_id)
    )
    return int(result.scalar_one())


async def get_artifact(db: AsyncSession, id: int) -> AiGenerationArtifact | None:
    return await db.get(AiGenerationArtifact, id)


async def delete_artifacts_by_task(db: AsyncSession, task_id: int) -> None:
    await db.execute(sql_delete(AiGenerationArtifact).where(AiGenerationArtifact.task_id == task_id))
    await db.commit()


async def delete_task(db: AsyncSession, id: int) -> bool:
    result = await db.execute(sql_delete(AiGenerationTask).where(AiGenerationTask.id == id))
    await db.commit()
    return result.rowcount > 0
