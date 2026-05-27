"""AI generation task and artifact ORM models."""

from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import ID_TYPE, AuditMixin, Base


class AiGenerationTask(Base, AuditMixin):
    __tablename__ = "mysterious_ai_generation_task"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(String(255), default="", server_default="")
    generation_type: Mapped[str] = mapped_column(String(64), default="", server_default="")
    input_type: Mapped[str] = mapped_column(String(32), default="", server_default="")
    input_filename: Mapped[str] = mapped_column(String(255), default="", server_default="")
    input_path: Mapped[str] = mapped_column(String(512), default="", server_default="")
    output_filename: Mapped[str] = mapped_column(String(255), default="", server_default="")
    output_path: Mapped[str] = mapped_column(String(512), default="", server_default="")
    work_dir: Mapped[str] = mapped_column(String(512), default="", server_default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending")
    params_json: Mapped[str] = mapped_column(Text, default="", server_default="")
    error_message: Mapped[str] = mapped_column(Text, default="", server_default="")
    generation_log: Mapped[str] = mapped_column(Text, default="", server_default="")


class AiGenerationArtifact(Base, AuditMixin):
    __tablename__ = "mysterious_ai_generation_artifact"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    artifact_type: Mapped[str] = mapped_column(String(32), default="", server_default="")
    filename: Mapped[str] = mapped_column(String(255), default="", server_default="")
    file_path: Mapped[str] = mapped_column(String(512), default="", server_default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
