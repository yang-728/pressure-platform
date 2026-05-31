from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.main import app
from app.models.user import User
from app.services.user import ensure_admin_user


async def _login_client(
    db: AsyncSession,
    *,
    username: str,
    role_code: str,
    permissions: list[str],
) -> AsyncClient:
    role = Role(name=f"{username}角色", code=role_code, description="", builtin=0)
    db.add(role)
    await db.flush()
    for permission in permissions:
        db.add(RolePermission(role_id=role.id, permission_code=permission))
    now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    token = f"token-{username}"
    db.add(
        User(
            username=username,
            password=hash_password("Secret123"),
            real_name=username,
            token=token,
            effect_time=now,
            expire_time=now + timedelta(hours=12),
            role_id=role.id,
        )
    )
    await db.commit()
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"token": token},
    )


@pytest.mark.asyncio
async def test_non_admin_without_node_permission_cannot_open_node_list(db: AsyncSession) -> None:
    async with await _login_client(db, username="no_node", role_code="runner", permissions=["testcase"]) as client:
        resp = await client.get("/node/list?page=1&size=10")

    body = resp.json()
    assert body["code"] == -1
    assert "无权" in body["message"]


@pytest.mark.asyncio
async def test_non_admin_with_user_permission_can_open_user_list(db: AsyncSession) -> None:
    async with await _login_client(db, username="user_mgr", role_code="user_mgr", permissions=["user"]) as client:
        resp = await client.get("/user/list?page=1&size=10")

    assert resp.json()["code"] == 0


@pytest.mark.asyncio
async def test_public_runtime_options_still_available_to_logged_in_users(db: AsyncSession) -> None:
    async with await _login_client(db, username="runner", role_code="runner", permissions=["testcase"]) as client:
        node_resp = await client.get("/node/enableSlaveCount")
        config_resp = await client.get("/config/options/biz")

    assert node_resp.json()["code"] == 0
    assert config_resp.json()["code"] == 0


@pytest.mark.asyncio
async def test_current_user_returns_role_permissions(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/user/current")

    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["roleCode"] == "admin"
    assert "role" in body["data"]["permissions"]


@pytest.mark.asyncio
async def test_existing_non_admin_users_get_default_role_on_startup(db: AsyncSession) -> None:
    db.add(
        User(
            username="legacy_user",
            password=hash_password("Secret123"),
            real_name="旧用户",
            role_id=0,
        )
    )
    await db.commit()

    await ensure_admin_user(db)

    legacy_user = (await db.execute(select(User).where(User.username == "legacy_user"))).scalar_one()
    assert legacy_user.role_id > 0
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login_resp = await client.post("/user/login", json={"username": "legacy_user", "password": "Secret123"})
        token = login_resp.json()["data"]
        current_resp = await client.get("/user/current", headers={"token": token})
    assert login_resp.json()["code"] == 0
    assert "testcase" in current_resp.json()["data"]["permissions"]


@pytest.mark.asyncio
async def test_execution_permission_can_open_execution_queue_dependencies(db: AsyncSession) -> None:
    async with await _login_client(db, username="executor", role_code="executor", permissions=["execution"]) as client:
        report_resp = await client.get("/report/list?page=1&size=10")
        testcase_resp = await client.get("/testcase/list?page=1&size=10")
        scheduled_resp = await client.get("/scheduledTask/list?page=1&size=10")

    assert report_resp.json()["code"] == 0
    assert testcase_resp.json()["code"] == 0
    assert scheduled_resp.json()["code"] == 0


from app.models.role import Role, RolePermission  # noqa: E402
