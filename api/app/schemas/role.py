"""Role schemas."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import BaseQuery, BaseVO, CamelModel


class RoleParam(CamelModel):
    name: str | None = None
    code: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


class RoleQuery(BaseQuery):
    name: str | None = None
    code: str | None = None


class RoleVO(BaseVO):
    name: str = ""
    code: str = ""
    description: str = ""
    builtin: int = 0
    permissions: list[str] = Field(default_factory=list)


class RolePermissionParam(CamelModel):
    permissions: list[str] = Field(default_factory=list)


class PermissionVO(CamelModel):
    code: str
    name: str
    group: str
    sort: int
