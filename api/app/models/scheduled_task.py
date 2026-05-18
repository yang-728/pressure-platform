"""ScheduledTask ORM 模型。映射 mysterious_scheduled_task 表。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import ID_TYPE, AuditMixin, Base


class ScheduledTask(Base, AuditMixin):
    __tablename__ = "mysterious_scheduled_task"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    test_case_id: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    schedule_type: Mapped[str] = mapped_column(String(16), default="once", server_default="once")
    schedule_data: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    run_param: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    enabled: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
