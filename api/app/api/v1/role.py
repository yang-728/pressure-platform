"""Role management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.core.permissions import PERMISSION_ROLE
from app.core.response import PageVO, Response, success
from app.db.session import get_db
from app.deps.auth import get_current_user_dep
from app.deps.permission import require_permission
from app.schemas.role import PermissionVO, RoleParam, RolePermissionParam, RoleQuery, RoleVO
from app.services import role as service

router = APIRouter(
    prefix="/role",
    tags=["role"],
    dependencies=[Depends(get_current_user_dep), Depends(require_permission(PERMISSION_ROLE))],
)


@router.post("/add", summary="新增角色", response_model=Response[int], response_model_by_alias=True)
async def add_role(
    param: RoleParam,
    current: UserContext = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
) -> Response[int]:
    return success(await service.add_role(db, param, current))


@router.post("/update/{id}", summary="修改角色", response_model=Response[bool], response_model_by_alias=True)
async def update_role(
    id: int,
    param: RoleParam,
    current: UserContext = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
) -> Response[bool]:
    return success(await service.update_role(db, id, param, current))


@router.get("/delete/{id}", summary="删除角色", response_model=Response[bool], response_model_by_alias=True)
async def delete_role(id: int, db: AsyncSession = Depends(get_db)) -> Response[bool]:
    return success(await service.delete_role(db, id))


@router.get("/getById/{id}", summary="角色详情", response_model=Response[RoleVO | None], response_model_by_alias=True)
async def get_role(id: int, db: AsyncSession = Depends(get_db)) -> Response[RoleVO | None]:
    return success(await service.get_role(db, id))


@router.get("/list", summary="角色列表", response_model=Response[PageVO[RoleVO]], response_model_by_alias=True)
async def list_roles(
    query: RoleQuery = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Response[PageVO[RoleVO]]:
    return success(await service.get_role_list(db, query))


@router.post(
    "/updatePermissions/{id}",
    summary="修改角色权限",
    response_model=Response[bool],
    response_model_by_alias=True,
)
async def update_permissions(
    id: int,
    param: RolePermissionParam,
    db: AsyncSession = Depends(get_db),
) -> Response[bool]:
    return success(await service.update_permissions(db, id, param))


@router.get(
    "/permissions",
    summary="权限目录",
    response_model=Response[list[PermissionVO]],
    response_model_by_alias=True,
)
async def permission_catalog() -> Response[list[PermissionVO]]:
    return success(await service.get_permission_catalog())
