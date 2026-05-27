from __future__ import annotations

import asyncio
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_generation import AiGenerationTask
from app.models.config import Config
from app.services.ai_generation import _append_log, _build_functional_case_prompt, _build_jmx_prompt

pytestmark = pytest.mark.asyncio


VALID_JMX = """<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="AI Demo" enabled="true"/>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="线程组" enabled="true">
        <stringProp name="ThreadGroup.num_threads">30</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="登录" enabled="true">
          <stringProp name="HTTPSampler.domain">10.10.27.210</stringProp>
          <stringProp name="HTTPSampler.path">/login</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""


async def test_append_log_keeps_generation_log_within_mysql_text_byte_limit() -> None:
    task = AiGenerationTask()
    _append_log(task, "日志" * 40000)

    assert len((task.generation_log or "").encode("utf-8")) <= 50000
    assert task.generation_log.endswith("\n")


async def _insert_workdir_config(db: AsyncSession, path: Path) -> None:
    db.add(
        Config(
            config_key="AI_GENERATION_WORK_DIR",
            config_value=str(path),
            description="AI生成任务工作目录",
        )
    )
    await db.commit()


async def _wait_task_success(auth_client: AsyncClient, task_id: int) -> dict:
    last = None
    for _ in range(20):
        resp = await auth_client.get(f"/ai-generation/tasks/{task_id}")
        last = resp.json()["data"]
        if last["status"] in {"success", "failed"}:
            return last
        await asyncio.sleep(0.05)
    return last or {}


async def test_build_jmx_prompt_includes_custom_requirement() -> None:
    prompt = _build_jmx_prompt(
        input_path="/tmp/input.md",
        output_path="/tmp/output.jmx",
        params={
            "protocol": "https",
            "host": "api.example.com",
            "customRequirement": "登录接口需要提取 token，并在后续请求 Header 中使用。",
        },
    )

    assert "额外生成要求：" in prompt
    assert "登录接口需要提取 token，并在后续请求 Header 中使用。" in prompt


async def test_build_jmx_prompt_supports_split_output_mode() -> None:
    prompt = _build_jmx_prompt(
        input_path="/tmp/apis.md",
        output_path="/tmp/emm_api.jmx",
        params={
            "jmxOutputMode": "split",
            "customRequirement": "每个接口单独生成 JMX 文件。",
        },
    )

    assert "输出 JMX 目录：/tmp" in prompt
    assert "文件名前缀：emm_api" in prompt
    assert "每个接口单独生成一个 .jmx 文件" in prompt
    assert "不要只生成一个总 JMX 文件" in prompt


async def test_build_functional_case_prompt_includes_output_and_custom_requirement() -> None:
    prompt = _build_functional_case_prompt(
        input_path="/tmp/requirement.docx",
        output_path="/tmp/login_cases.xlsx",
        params={
            "designer": "张三",
            "splitByModule": True,
            "includeDetailScenarios": True,
            "outputFormats": "xlsx,xmind",
            "xmindOutputPath": "/tmp/login_cases.xmind",
            "customRequirement": "重点覆盖登录失败锁定和验证码过期场景。",
        },
    )

    assert "使用 testcase-generator skill" in prompt
    assert "输出 Excel 路径：/tmp/login_cases.xlsx" in prompt
    assert "输出 XMind 路径：/tmp/login_cases.xmind" in prompt
    assert "设计人：张三" in prompt
    assert "重点覆盖登录失败锁定和验证码过期场景。" in prompt


async def test_create_jmeter_jmx_task_generates_preview_download_and_log(
    auth_client: AsyncClient,
    db: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _insert_workdir_config(db, tmp_path / "ai-generation")

    async def fake_invoke_codex_cli(*, output_path: str, **_: object) -> str:
        Path(output_path).write_text(VALID_JMX, encoding="utf-8")
        return "codex generated jmx"

    monkeypatch.setattr(
        "app.services.ai_generation._invoke_codex_cli",
        fake_invoke_codex_cli,
    )

    resp = await auth_client.post(
        "/ai-generation/tasks",
        data={
            "taskName": "EMM登录压测脚本",
            "generationType": "jmeter_jmx",
            "outputFilename": "emm_login.jmx",
            "protocol": "http",
            "host": "10.10.27.210",
            "port": "8080",
            "threads": "30",
            "rampUp": "10",
            "loopCount": "1",
            "generateAssertion": "true",
            "generateCsvParam": "false",
        },
        files={"inputFile": ("login-api.md", b"## Login API\nPOST /login", "text/markdown")},
    )

    body = resp.json()
    assert body["code"] == 0
    task_id = body["data"]

    task = await _wait_task_success(auth_client, task_id)
    assert task["status"] == "success"
    assert task["taskName"] == "EMM登录压测脚本"
    assert task["generationType"] == "jmeter_jmx"
    assert task["artifactCount"] == 1

    list_resp = await auth_client.get("/ai-generation/tasks", params={"page": 1, "size": 10})
    page = list_resp.json()["data"]
    assert page["total"] == 1
    assert page["list"][0]["taskName"] == "EMM登录压测脚本"

    artifact_resp = await auth_client.get(f"/ai-generation/tasks/{task_id}/artifacts")
    artifacts = artifact_resp.json()["data"]
    assert len(artifacts) == 1
    assert artifacts[0]["filename"] == "emm_login.jmx"
    artifact_id = artifacts[0]["id"]

    view_resp = await auth_client.get(f"/ai-generation/artifacts/{artifact_id}/view")
    assert "<jmeterTestPlan" in view_resp.text
    assert "ThreadGroup.num_threads" in view_resp.text

    download_resp = await auth_client.get(f"/ai-generation/artifacts/{artifact_id}/download")
    assert download_resp.status_code == 200
    assert "attachment" in download_resp.headers["content-disposition"]
    assert download_resp.content.startswith(b"<?xml")

    log_resp = await auth_client.get(f"/ai-generation/tasks/{task_id}/log")
    assert "codex generated jmx" in log_resp.json()["data"]


async def test_create_jmeter_jmx_task_split_mode_generates_multiple_artifacts(
    auth_client: AsyncClient,
    db: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _insert_workdir_config(db, tmp_path / "ai-generation")

    async def fake_invoke_codex_cli(*, work_dir: str, **_: object) -> str:
        Path(work_dir, "emm_api_login.jmx").write_text(VALID_JMX, encoding="utf-8")
        Path(work_dir, "emm_api_logout.jmx").write_text(VALID_JMX, encoding="utf-8")
        return "codex generated split jmx"

    monkeypatch.setattr(
        "app.services.ai_generation._invoke_codex_cli",
        fake_invoke_codex_cli,
    )

    resp = await auth_client.post(
        "/ai-generation/tasks",
        data={
            "taskName": "EMM接口拆分脚本",
            "generationType": "jmeter_jmx",
            "outputFilename": "emm_api.jmx",
            "jmxOutputMode": "split",
        },
        files={"inputFile": ("apis.md", b"POST /login\nPOST /logout", "text/markdown")},
    )

    body = resp.json()
    assert body["code"] == 0
    task_id = body["data"]

    task = await _wait_task_success(auth_client, task_id)
    assert task["status"] == "success"
    assert task["artifactCount"] == 2

    artifact_resp = await auth_client.get(f"/ai-generation/tasks/{task_id}/artifacts")
    artifacts = artifact_resp.json()["data"]
    assert sorted(item["filename"] for item in artifacts) == [
        "emm_api_login.jmx",
        "emm_api_logout.jmx",
    ]
    assert {item["artifactType"] for item in artifacts} == {"jmx"}

    selected_ids = [item["id"] for item in artifacts]
    zip_resp = await auth_client.post(
        f"/ai-generation/tasks/{task_id}/artifacts/download",
        json={"artifactIds": selected_ids},
    )
    assert zip_resp.status_code == 200
    assert zip_resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(BytesIO(zip_resp.content)) as zf:
        assert sorted(zf.namelist()) == ["emm_api_login.jmx", "emm_api_logout.jmx"]


async def test_create_functional_case_task_generates_xlsx_artifact(
    auth_client: AsyncClient,
    db: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _insert_workdir_config(db, tmp_path / "ai-generation")

    async def fake_invoke_codex_cli(*, output_path: str, **_: object) -> str:
        Path(output_path).write_bytes(b"PK\x03\x04fake xlsx content")
        return "codex generated functional cases"

    monkeypatch.setattr(
        "app.services.ai_generation._invoke_codex_cli",
        fake_invoke_codex_cli,
    )

    resp = await auth_client.post(
        "/ai-generation/tasks",
        data={
            "taskName": "登录功能测试用例",
            "generationType": "functional_case",
            "outputFilename": "login_cases.xlsx",
            "designer": "张三",
            "splitByModule": "true",
            "includeDetailScenarios": "true",
            "customRequirement": "重点覆盖登录失败锁定和验证码过期场景。",
        },
        files={"inputFile": ("login-requirement.txt", b"login requirement", "text/plain")},
    )

    body = resp.json()
    assert body["code"] == 0
    task_id = body["data"]

    task = await _wait_task_success(auth_client, task_id)
    assert task["status"] == "success"
    assert task["generationType"] == "functional_case"
    assert task["artifactCount"] == 1

    artifact_resp = await auth_client.get(f"/ai-generation/tasks/{task_id}/artifacts")
    artifacts = artifact_resp.json()["data"]
    assert artifacts[0]["artifactType"] == "xlsx"
    assert artifacts[0]["filename"] == "login_cases.xlsx"
    artifact_id = artifacts[0]["id"]

    view_resp = await auth_client.get(f"/ai-generation/artifacts/{artifact_id}/view")
    assert "二进制文件不支持在线预览" in view_resp.text

    download_resp = await auth_client.get(f"/ai-generation/artifacts/{artifact_id}/download")
    assert download_resp.content.startswith(b"PK")

    log_resp = await auth_client.get(f"/ai-generation/tasks/{task_id}/log")
    assert "codex generated functional cases" in log_resp.json()["data"]


async def test_create_functional_case_task_generates_xlsx_and_xmind_artifacts(
    auth_client: AsyncClient,
    db: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _insert_workdir_config(db, tmp_path / "ai-generation")

    async def fake_invoke_codex_cli(*, output_path: str, **_: object) -> str:
        output = Path(output_path)
        output.write_bytes(b"PK\x03\x04fake xlsx content")
        output.with_suffix(".xmind").write_bytes(b"PK\x03\x04fake xmind content")
        return "codex generated functional cases with xmind"

    monkeypatch.setattr(
        "app.services.ai_generation._invoke_codex_cli",
        fake_invoke_codex_cli,
    )

    resp = await auth_client.post(
        "/ai-generation/tasks",
        data={
            "taskName": "登录功能测试用例双格式",
            "generationType": "functional_case",
            "outputFilename": "login_cases.xlsx",
            "outputFormats": "xlsx,xmind",
            "designer": "张三",
            "splitByModule": "true",
            "includeDetailScenarios": "true",
        },
        files={"inputFile": ("login-requirement.docx", b"fake docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    body = resp.json()
    assert body["code"] == 0
    task_id = body["data"]

    task = await _wait_task_success(auth_client, task_id)
    assert task["status"] == "success"
    assert task["artifactCount"] == 2

    artifact_resp = await auth_client.get(f"/ai-generation/tasks/{task_id}/artifacts")
    artifacts = artifact_resp.json()["data"]
    filenames_by_type = {item["artifactType"]: item["filename"] for item in artifacts}
    assert filenames_by_type == {
        "xlsx": "login_cases.xlsx",
        "xmind": "login_cases.xmind",
    }

    xmind_artifact = next(item for item in artifacts if item["artifactType"] == "xmind")
    view_resp = await auth_client.get(f"/ai-generation/artifacts/{xmind_artifact['id']}/view")
    assert "二进制文件不支持在线预览" in view_resp.text

    download_resp = await auth_client.get(f"/ai-generation/artifacts/{xmind_artifact['id']}/download")
    assert download_resp.content.startswith(b"PK")


async def test_invalid_generated_jmx_marks_task_failed_without_artifact(
    auth_client: AsyncClient,
    db: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _insert_workdir_config(db, tmp_path / "ai-generation")

    async def fake_invoke_codex_cli(*, output_path: str, **_: object) -> str:
        Path(output_path).write_text("not xml", encoding="utf-8")
        return "codex generated invalid content"

    monkeypatch.setattr(
        "app.services.ai_generation._invoke_codex_cli",
        fake_invoke_codex_cli,
    )

    resp = await auth_client.post(
        "/ai-generation/tasks",
        data={
            "taskName": "异常脚本",
            "generationType": "jmeter_jmx",
            "outputFilename": "bad.jmx",
        },
        files={"inputFile": ("bad.md", b"bad api", "text/markdown")},
    )

    task_id = resp.json()["data"]
    task = await _wait_task_success(auth_client, task_id)
    assert task["status"] == "failed"
    assert "JMX XML校验失败" in task["errorMessage"]

    artifact_resp = await auth_client.get(f"/ai-generation/tasks/{task_id}/artifacts")
    assert artifact_resp.json()["data"] == []


async def test_delete_generation_task_removes_task_and_files(
    auth_client: AsyncClient,
    db: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "ai-generation"
    await _insert_workdir_config(db, workdir)

    async def fake_invoke_codex_cli(*, output_path: str, **_: object) -> str:
        Path(output_path).write_text(VALID_JMX, encoding="utf-8")
        return "codex generated jmx"

    monkeypatch.setattr(
        "app.services.ai_generation._invoke_codex_cli",
        fake_invoke_codex_cli,
    )

    resp = await auth_client.post(
        "/ai-generation/tasks",
        data={
            "taskName": "删除任务",
            "generationType": "jmeter_jmx",
            "outputFilename": "delete_me.jmx",
        },
        files={"inputFile": ("delete.md", b"POST /delete", "text/markdown")},
    )
    task_id = resp.json()["data"]
    task = await _wait_task_success(auth_client, task_id)
    assert task["status"] == "success"

    task_dir = workdir / str(task_id)
    assert task_dir.exists()

    delete_resp = await auth_client.delete(f"/ai-generation/tasks/{task_id}")
    assert delete_resp.json()["code"] == 0
    assert delete_resp.json()["data"] is True
    assert not task_dir.exists()

    get_resp = await auth_client.get(f"/ai-generation/tasks/{task_id}")
    assert get_resp.json()["code"] != 0
