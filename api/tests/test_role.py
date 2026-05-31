from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest.mark.asyncio
async def test_role_crud_and_permission_update(auth_client: AsyncClient) -> None:
    add_resp = await auth_client.post(
        "/role/add",
        json={"name": "用户管理员", "code": "user_manager", "description": "管理用户"},
    )
    assert add_resp.json()["code"] == 0
    role_id = add_resp.json()["data"]

    update_perm = await auth_client.post(
        f"/role/updatePermissions/{role_id}",
        json={"permissions": ["user", "role"]},
    )
    assert update_perm.json()["code"] == 0

    detail = await auth_client.get(f"/role/getById/{role_id}")
    data = detail.json()["data"]
    assert data["name"] == "用户管理员"
    assert data["code"] == "user_manager"
    assert data["permissions"] == ["role", "user"]

    list_resp = await auth_client.get("/role/list?page=1&size=10")
    assert list_resp.json()["data"]["total"] >= 1

    delete_resp = await auth_client.get(f"/role/delete/{role_id}")
    assert delete_resp.json()["data"] is True


@pytest.mark.asyncio
async def test_add_role_without_code_generates_internal_code(auth_client: AsyncClient) -> None:
    add_resp = await auth_client.post(
        "/role/add",
        json={"name": "测试执行人员", "description": "不需要手填编码", "permissions": ["execution"]},
    )
    body = add_resp.json()
    assert body["code"] == 0
    role_id = body["data"]

    detail = await auth_client.get(f"/role/getById/{role_id}")
    data = detail.json()["data"]
    assert data["name"] == "测试执行人员"
    assert data["code"].startswith("role_")
    assert data["permissions"] == ["execution"]


@pytest.mark.asyncio
async def test_update_role_payload_can_update_permissions(auth_client: AsyncClient) -> None:
    add_resp = await auth_client.post(
        "/role/add",
        json={"name": "执行观察员", "permissions": ["execution"]},
    )
    role_id = add_resp.json()["data"]

    update_resp = await auth_client.post(
        f"/role/update/{role_id}",
        json={"name": "报告观察员", "description": "查看报告", "permissions": ["report"]},
    )
    assert update_resp.json()["code"] == 0

    detail = await auth_client.get(f"/role/getById/{role_id}")
    data = detail.json()["data"]
    assert data["name"] == "报告观察员"
    assert data["description"] == "查看报告"
    assert data["permissions"] == ["report"]


@pytest.mark.asyncio
async def test_delete_role_bound_to_user_is_blocked(auth_client: AsyncClient, db: AsyncSession) -> None:
    add_resp = await auth_client.post(
        "/role/add",
        json={"name": "业务用户", "code": "biz_user", "description": "绑定用户的角色"},
    )
    assert add_resp.json()["code"] == 0
    role_id = add_resp.json()["data"]
    db.add(User(username="bound_user", password="x", real_name="绑定用户", role_id=role_id))
    await db.commit()

    delete_resp = await auth_client.get(f"/role/delete/{role_id}")

    body = delete_resp.json()
    assert body["code"] != 0
    assert "已有用户" in body["message"]


@pytest.mark.asyncio
async def test_admin_role_permissions_cannot_be_modified(auth_client: AsyncClient) -> None:
    roles = await auth_client.get("/role/list?page=1&size=20&code=admin")
    admin_id = roles.json()["data"]["list"][0]["id"]

    resp = await auth_client.post(
        f"/role/updatePermissions/{admin_id}",
        json={"permissions": ["testcase"]},
    )

    assert resp.json()["code"] == -1
    assert "超级管理员" in resp.json()["message"]


@pytest.mark.asyncio
async def test_permission_catalog(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/role/permissions")

    body = resp.json()
    assert body["code"] == 0
    codes = {item["code"] for item in body["data"]}
    assert {"testcase", "user", "role", "audit"}.issubset(codes)
