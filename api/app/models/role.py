"""Role and role-permission ORM models."""

from __future__ import annotations

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import ID_TYPE, AuditMixin, Base


class Role(Base, AuditMixin):
    __tablename__ = "mysterious_role"
    __table_args__ = (UniqueConstraint("code", name="uk_mysterious_role_code"),)

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), default="", server_default="")
    code: Mapped[str] = mapped_column(String(64), default="", server_default="")
    description: Mapped[str] = mapped_column(String(255), default="", server_default="")
    builtin: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class RolePermission(Base):
    __tablename__ = "mysterious_role_permission"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ID_TYPE, default=0, server_default="0")
    permission_code: Mapped[str] = mapped_column(String(64), default="", server_default="")
