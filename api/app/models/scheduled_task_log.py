"""Scheduled task execution log ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import ID_TYPE, Base


class ScheduledTaskLog(Base):
    __tablename__ = "mysterious_scheduled_task_log"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    scheduled_task_id: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    test_case_id: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    trigger_type: Mapped[str] = mapped_column(String(16), default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default="", server_default="")
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    message: Mapped[str] = mapped_column(Text, default="", server_default="")
    region: Mapped[str] = mapped_column(String(255), default="", server_default="")
    requested_slave_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    available_slave_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    allocated_slave_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    slave_hosts: Mapped[str] = mapped_column(Text, default="", server_default="")
    run_param: Mapped[str] = mapped_column(Text, default="", server_default="")
    trigger_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
