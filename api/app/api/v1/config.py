"""/config/* 路由。所有端点要求登录。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.core.permissions import PERMISSION_CONFIG
from app.core.response import PageVO, Response, success
from app.db.session import get_db
from app.deps.auth import get_current_user_dep
from app.deps.permission import require_permission
from app.schemas.config import ConfigCategoryVO, ConfigParam, ConfigQuery, ConfigVO
from app.services import config as service

router = APIRouter(
    prefix="/config",
    tags=["config"],
    dependencies=[Depends(get_current_user_dep)],
)


@router.post(
    "/add",
    summary="新增配置",
    response_model=Response[int],
    response_model_by_alias=True,
)
async def add_config(
    param: ConfigParam,
    current: UserContext = Depends(require_permission(PERMISSION_CONFIG)),
    db: AsyncSession = Depends(get_db),
) -> Response[int]:
    id = await service.add_config(db, param, current)
    return success(id)


@router.post(
    "/update/{id}",
    summary="修改配置",
    response_model=Response[bool],
    response_model_by_alias=True,
)
async def update_config(
    id: int,
    param: ConfigParam,
    current: UserContext = Depends(require_permission(PERMISSION_CONFIG)),
    db: AsyncSession = Depends(get_db),
) -> Response[bool]:
    ok = await service.update_config(db, id, param, current)
    return success(ok)


@router.get(
    "/delete/{id}",
    summary="删除配置",
    response_model=Response[bool],
    response_model_by_alias=True,
)
async def delete_config(
    id: int,
    current: UserContext = Depends(require_permission(PERMISSION_CONFIG)),
    db: AsyncSession = Depends(get_db),
) -> Response[bool]:
    ok = await service.delete_config(db, id)
    return success(ok)


@router.get(
    "/list",
    summary="分页查询配置",
    response_model=Response[PageVO[ConfigVO]],
    response_model_by_alias=True,
)
async def list_configs(
    query: ConfigQuery = Depends(),
    current: UserContext = Depends(require_permission(PERMISSION_CONFIG)),
    db: AsyncSession = Depends(get_db),
) -> Response[PageVO[ConfigVO]]:
    page = await service.get_config_list(db, query)
    return success(page)


@router.get(
    "/categories",
    summary="获取配置分类列表",
    response_model=Response[list[ConfigCategoryVO]],
    response_model_by_alias=True,
)
async def list_categories(
    current: UserContext = Depends(require_permission(PERMISSION_CONFIG)),
) -> Response[list[ConfigCategoryVO]]:
    categories = await service.get_categories()
    return success(categories)


@router.get(
    "/options/{type}",
    summary="获取业务选项列表",
    response_model=Response[list[str]],
    response_model_by_alias=True,
)
async def get_options(
    type: str,
    db: AsyncSession = Depends(get_db),
) -> Response[list[str]]:
    options = await service.get_options(db, type)
    return success(options)
