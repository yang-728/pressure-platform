"""Role service."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import stamp_create, stamp_modify
from app.core.codes import Codes
from app.core.context import UserContext
from app.core.exceptions import MysteriousException
from app.core.permissions import ADMIN_ROLE_CODE, ALL_PERMISSION_CODES, PERMISSION_CATALOG
from app.core.response import PageVO
from app.crud import role as role_crud
from app.crud import user as user_crud
from app.models.role import Role
from app.schemas.role import PermissionVO, RoleParam, RolePermissionParam, RoleQuery, RoleVO


def _check_param(param: RoleParam) -> None:
    if param is None:
        raise MysteriousException(Codes.PARAMS_EMPTY)
    if not param.name:
        raise MysteriousException(Codes.PARAM_MISSING)


def _normalize_permissions(permissions: list[str] | None) -> list[str]:
    normalized = sorted(set(permissions or []))
    invalid = [code for code in normalized if code not in ALL_PERMISSION_CODES]
    if invalid:
        raise MysteriousException(Codes.PARAM_WRONG, message=f"权限编码不存在: {','.join(invalid)}")
    return normalized


def _to_vo(role: Role, permissions: list[str] | None = None) -> RoleVO:
    return RoleVO.model_validate(role).model_copy(update={"permissions": permissions or []})


async def add_role(db: AsyncSession, param: RoleParam, user: UserContext) -> int:
    _check_param(param)
    code = (param.code or "").strip() or f"role_{uuid.uuid4().hex[:12]}"
    existing = await role_crud.get_by_code(db, code)
    if existing is not None:
        raise MysteriousException(Codes.FAIL, message="角色编码已存在")
    role = Role(name=param.name or "", code=code, description=param.description or "", builtin=0)
    stamp_create(role, user)
    await role_crud.add(db, role)
    if param.permissions is not None:
        await role_crud.replace_permissions(db, role.id, _normalize_permissions(param.permissions))
    return role.id


async def update_role(db: AsyncSession, id: int, param: RoleParam, user: UserContext) -> bool:
    role = await role_crud.get_by_id(db, id)
    if role is None:
        return False
    if role.code == ADMIN_ROLE_CODE:
        raise MysteriousException(Codes.FAIL, message="超级管理员角色不可修改")
    sent = param.model_dump(exclude_unset=True, exclude_none=True, by_alias=False)
    if "name" in sent:
        role.name = sent["name"]
    if "code" in sent:
        if sent["code"] != role.code and await role_crud.get_by_code(db, sent["code"]) is not None:
            raise MysteriousException(Codes.FAIL, message="角色编码已存在")
        role.code = sent["code"]
    if "description" in sent:
        role.description = sent["description"]
    if "permissions" in sent:
        await role_crud.replace_permissions(db, id, _normalize_permissions(sent["permissions"]))
    stamp_modify(role, user)
    return await role_crud.update(db, role)


async def delete_role(db: AsyncSession, id: int) -> bool:
    role = await role_crud.get_by_id(db, id)
    if role is None:
        return False
    if role.builtin or role.code == ADMIN_ROLE_CODE:
        raise MysteriousException(Codes.FAIL, message="内置角色不可删除")
    if await user_crud.count_by_role_id(db, id) > 0:
        raise MysteriousException(Codes.FAIL, message="该角色已有用户绑定，不可删除")
    return await role_crud.delete(db, id)


async def get_role(db: AsyncSession, id: int) -> RoleVO | None:
    role = await role_crud.get_by_id(db, id)
    if role is None:
        return None
    return _to_vo(role, await role_crud.list_permissions(db, role.id))


async def get_role_list(db: AsyncSession, query: RoleQuery) -> PageVO[RoleVO]:
    page_vo: PageVO[RoleVO] = PageVO(page=query.page, size=query.size, total=0, list=[])
    total = await role_crud.count(db, name=query.name, code=query.code)
    if total <= 0:
        return page_vo
    page_vo.total = total
    roles = await role_crud.list_roles(
        db,
        name=query.name,
        code=query.code,
        offset=PageVO.offset(query.page, query.size),
        limit=query.size,
    )
    page_vo.list = [_to_vo(role, await role_crud.list_permissions(db, role.id)) for role in roles]
    return page_vo


async def update_permissions(db: AsyncSession, id: int, param: RolePermissionParam) -> bool:
    role = await role_crud.get_by_id(db, id)
    if role is None:
        raise MysteriousException(Codes.FAIL, message="角色不存在")
    if role.code == ADMIN_ROLE_CODE:
        raise MysteriousException(Codes.FAIL, message="超级管理员角色默认拥有全部权限")
    return await role_crud.replace_permissions(db, id, _normalize_permissions(param.permissions))


async def get_permission_catalog() -> list[PermissionVO]:
    return [PermissionVO(**item) for item in PERMISSION_CATALOG]
