"""Config 相关 Pydantic schemas，对齐 Java ConfigParam / ConfigVO / ConfigQuery。"""

from __future__ import annotations

from app.schemas.base import BaseQuery, BaseVO, CamelModel


class ConfigParam(CamelModel):
    config_key: str | None = None
    config_value: str | None = None
    description: str | None = None


class ConfigVO(BaseVO):
    config_key: str = ""
    config_value: str = ""
    description: str = ""
    category: str = ""
    category_name: str = ""
    display_name: str = ""
    value_type: str = "text"
    sort: int = 0


class ConfigQuery(BaseQuery):
    config_key: str | None = None
    category: str | None = None


class ConfigCategoryVO(CamelModel):
    key: str
    name: str
    sort: int
