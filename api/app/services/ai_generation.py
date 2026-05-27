"""AI generation service.

The first supported generation type is `jmeter_jmx`. The module is deliberately
generic so future generation types can share task/artifact storage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import aiofiles
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import stamp_create, stamp_modify
from app.core.codes import Codes
from app.core.context import UserContext
from app.core.exceptions import MysteriousException
from app.core.response import PageVO
from app.crud import ai_generation as crud
from app.models.ai_generation import AiGenerationArtifact, AiGenerationTask
from app.schemas.ai_generation import (
    AiGenerationArtifactVO,
    AiGenerationQuery,
    AiGenerationStatsVO,
    AiGenerationTaskVO,
)
from app.services import config as config_service

log = logging.getLogger(__name__)

GEN_TYPE_JMETER_JMX = "jmeter_jmx"
GEN_TYPE_FUNCTIONAL_CASE = "functional_case"
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
FUNCTIONAL_OUTPUT_FORMATS = {"xlsx", "xmind"}
GENERATION_LOG_MAX_BYTES = 50000
JMX_OUTPUT_MODE_SINGLE = "single"
JMX_OUTPUT_MODE_SPLIT = "split"
JMX_OUTPUT_MODES = {JMX_OUTPUT_MODE_SINGLE, JMX_OUTPUT_MODE_SPLIT}


def _task_to_vo(obj: AiGenerationTask, artifact_count: int = 0) -> AiGenerationTaskVO:
    vo = AiGenerationTaskVO.model_validate(obj)
    vo.artifact_count = artifact_count
    return vo


def _artifact_to_vo(obj: AiGenerationArtifact) -> AiGenerationArtifactVO:
    return AiGenerationArtifactVO.model_validate(obj)


def _safe_filename(name: str, suffix: str | tuple[str, ...]) -> str:
    cleaned = os.path.basename(name or "").strip()
    suffixes = (suffix,) if isinstance(suffix, str) else suffix
    if not cleaned or " " in cleaned or not cleaned.endswith(suffixes):
        suffix_text = " / ".join(suffixes)
        raise MysteriousException(Codes.PARAM_WRONG, message=f"文件名称必须以 {suffix_text} 结尾且不能包含空格")
    return cleaned


def _trim_log_bytes(content: str, max_bytes: int = GENERATION_LOG_MAX_BYTES) -> str:
    encoded = content.encode("utf-8")
    if len(encoded) <= max_bytes:
        return content

    prefix = "[日志过长，仅保留最后部分]\n"
    prefix_bytes = prefix.encode("utf-8")
    tail_size = max(0, max_bytes - len(prefix_bytes))
    tail = encoded[-tail_size:].decode("utf-8", errors="ignore")
    return prefix + tail


def _append_log(task: AiGenerationTask, message: str) -> None:
    task.generation_log = _trim_log_bytes((task.generation_log or "") + message.rstrip() + "\n")


def _parse_functional_output_formats(params: dict[str, object]) -> list[str]:
    raw = params.get("outputFormats") or "xlsx"
    if isinstance(raw, str):
        parts = [item.strip().lower() for item in raw.split(",")]
    elif isinstance(raw, (list, tuple, set)):
        parts = [str(item).strip().lower() for item in raw]
    else:
        parts = ["xlsx"]

    result: list[str] = []
    for item in parts:
        if not item:
            continue
        if item not in FUNCTIONAL_OUTPUT_FORMATS:
            raise MysteriousException(Codes.PARAM_WRONG, message=f"不支持的输出格式: {item}")
        if item not in result:
            result.append(item)
    if not result:
        raise MysteriousException(Codes.PARAM_WRONG, message="请至少选择一种输出格式")
    return result


def _build_functional_artifact_specs(
    *,
    output_path: str,
    output_filename: str,
    formats: list[str],
) -> list[tuple[str, str, str]]:
    base_path = Path(output_path)
    base_name = Path(output_filename)
    specs: list[tuple[str, str, str]] = []
    for item in formats:
        if item == "xlsx":
            specs.append(("xlsx", base_name.name, str(base_path)))
        elif item == "xmind":
            specs.append(("xmind", base_name.with_suffix(".xmind").name, str(base_path.with_suffix(".xmind"))))
    return specs


def _parse_jmx_output_mode(params: dict[str, object]) -> str:
    mode = str(params.get("jmxOutputMode") or JMX_OUTPUT_MODE_SINGLE).strip().lower()
    if mode not in JMX_OUTPUT_MODES:
        raise MysteriousException(Codes.PARAM_WRONG, message=f"不支持的JMX输出模式: {mode}")
    return mode


async def _get_work_root(db: AsyncSession) -> str:
    return await config_service.get_value_or_default(
        db,
        "AI_GENERATION_WORK_DIR",
        "/root/PyProject/mysterious-data/ai-generation",
    )


async def _get_codex_bin(db: AsyncSession) -> str:
    return await config_service.get_value_or_default(db, "AI_CODEX_BIN", "codex")


async def _get_timeout(db: AsyncSession) -> int:
    raw = await config_service.get_value_or_default(db, "AI_GENERATION_TIMEOUT_SECONDS", "1800")
    try:
        return max(10, int(raw))
    except ValueError:
        return 1800


def _build_jmx_prompt(
    *,
    input_path: str,
    output_path: str,
    params: dict[str, object],
) -> str:
    custom_requirement = str(params.get("customRequirement") or "").strip()
    custom_requirement_block = (
        f"\n额外生成要求：\n{custom_requirement}\n"
        if custom_requirement
        else ""
    )
    output_mode = _parse_jmx_output_mode(params)
    output = Path(output_path)
    if output_mode == JMX_OUTPUT_MODE_SPLIT:
        output_dir = str(output.parent)
        filename_prefix = output.stem
        output_block = f"""输出 JMX 目录：{output_dir}
文件名前缀：{filename_prefix}"""
        output_requirements = f"""- 每个接口单独生成一个 .jmx 文件，不要只生成一个总 JMX 文件。
- 所有输出文件必须写入上面的输出 JMX 目录。
- 文件名使用 `{filename_prefix}_接口标识.jmx` 格式，接口标识使用接口名称、路径或方法提炼出的英文、数字、下划线。
- 每个 .jmx 文件都必须可被 JMeter 5.6+ 打开，并包含线程组和对应接口的 HTTP Sampler。"""
        completion_text = "生成完成后只需要简短说明输出目录和生成的 JMX 文件列表。"
    else:
        output_block = f"输出 JMX 路径：{output_path}"
        output_requirements = """- 只生成一个可被 JMeter 5.6+ 打开的 .jmx 文件。
- 输出文件必须写入上面的输出路径。"""
        completion_text = "生成完成后只需要简短说明输出文件路径。"
    return f"""使用 jmeter-generator skill，根据 Markdown 接口文档生成 JMeter JMX 文件。

输入文档路径：{input_path}
{output_block}

生成要求：
{output_requirements}
- 协议：{params.get("protocol") or "http"}
- Host/IP：{params.get("host") or "请优先从文档中识别"}
- 端口：{params.get("port") or "按协议默认或从文档识别"}
- 线程数：{params.get("threads") or 1}
- Ramp-up 秒：{params.get("rampUp") or 1}
- 循环次数：{params.get("loopCount") or 1}
- 生成基础断言：{params.get("generateAssertion")}
- 生成 CSV 参数化配置：{params.get("generateCsvParam")}
{custom_requirement_block}

不要修改项目代码，不要创建额外说明文件。{completion_text}
"""


def _build_functional_case_prompt(
    *,
    input_path: str,
    output_path: str,
    params: dict[str, object],
) -> str:
    custom_requirement = str(params.get("customRequirement") or "").strip()
    custom_requirement_block = (
        f"\n额外生成要求：\n{custom_requirement}\n"
        if custom_requirement
        else ""
    )
    designer = str(params.get("designer") or "").strip() or "留空"
    output_formats = _parse_functional_output_formats(params)
    output_lines = [f"输出 Excel 路径：{output_path}"] if "xlsx" in output_formats else []
    xmind_output_path = str(params.get("xmindOutputPath") or Path(output_path).with_suffix(".xmind"))
    if "xmind" in output_formats:
        output_lines.append(f"输出 XMind 路径：{xmind_output_path}")
    output_desc = "、".join(output_formats)
    xmind_requirement = (
        f"- 同时生成一个可被 XMind 打开的 .xmind 文件，并写入 XMind 输出路径：{xmind_output_path}。\n"
        if "xmind" in output_formats
        else ""
    )
    xlsx_requirement = (
        "- 最终必须生成一个 .xlsx 文件，并写入上面的输出 Excel 路径。\n"
        if "xlsx" in output_formats
        else ""
    )
    return f"""使用 testcase-generator skill，根据需求文档生成功能测试用例。

输入需求文档路径：{input_path}
{chr(10).join(output_lines)}

生成要求：
{xlsx_requirement}{xmind_requirement}- 输出格式：{output_desc}
- 使用固定列头：功能模块, 用例编号, 功能点, 用例标题, 优先级, 前置条件, 测试步骤, 预期结果, 设计人, 执行结果, 执行人, 备注。
- 先识别模块与功能点，再按模块生成测试用例。
- 覆盖正常场景、异常场景、边界值、权限、安全、状态流转、页面展示、跳转、下载、打印、新标签打开等适用场景。
- 设计人：{designer}
- 是否按模块拆分：{params.get("splitByModule")}
- 是否生成详细边界/异常/权限/状态场景：{params.get("includeDetailScenarios")}
{custom_requirement_block}

不要修改项目代码。可以创建生成所需的中间 JSON，但最终必须输出用户选择的产物文件。生成完成后只需要简短说明输出文件路径和用例数量。
"""


async def _invoke_codex_cli(
    *,
    codex_bin: str,
    prompt: str,
    work_dir: str,
    output_path: str,
    timeout: int,
) -> str:
    proc = await asyncio.create_subprocess_exec(
        codex_bin,
        "exec",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd",
        work_dir,
        prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"Codex生成超时（{timeout}秒）") from exc

    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    combined = (out + "\n" + err).strip()
    if proc.returncode != 0:
        raise RuntimeError(f"Codex生成失败: {combined}")
    return combined


def _validate_jmx(path: str) -> None:
    try:
        tree = ElementTree.parse(path)
    except Exception as exc:
        raise ValueError(f"JMX XML校验失败: {exc}") from exc

    root = tree.getroot()
    if root.tag != "jmeterTestPlan":
        raise ValueError("JMX XML校验失败: 根节点不是 jmeterTestPlan")

    has_thread_group = any(el.tag.endswith("ThreadGroup") or el.tag == "ThreadGroup" for el in root.iter())
    has_http_sampler = any(el.tag == "HTTPSamplerProxy" for el in root.iter())
    if not has_thread_group:
        raise ValueError("JMX XML校验失败: 未找到线程组")
    if not has_http_sampler:
        raise ValueError("JMX XML校验失败: 未找到 HTTP Sampler")


def _get_type_spec(generation_type: str) -> tuple[tuple[str, ...], str, str, str, str]:
    if generation_type == GEN_TYPE_JMETER_JMX:
        return (".md",), ".jmx", "md", "jmx", "JMX XML校验成功，生成任务完成"
    if generation_type == GEN_TYPE_FUNCTIONAL_CASE:
        return (".md", ".txt", ".docx"), ".xlsx", "requirement", "xlsx", "功能测试用例 Excel 生成完成"
    raise MysteriousException(Codes.PARAM_WRONG, message="当前仅支持 JMeter JMX 脚本生成和功能测试用例生成")


async def create_task(
    db: AsyncSession,
    *,
    task_name: str,
    generation_type: str,
    output_filename: str,
    input_file: UploadFile,
    user: UserContext,
    params: dict[str, object],
) -> int:
    if not task_name.strip():
        raise MysteriousException(Codes.PARAMS_EMPTY, message="任务名称不能为空")

    input_suffixes, output_suffix, input_type, _artifact_type, _success_log = _get_type_spec(generation_type)
    input_filename = _safe_filename(input_file.filename or "", input_suffixes)
    output_name = _safe_filename(output_filename, output_suffix)
    if generation_type == GEN_TYPE_FUNCTIONAL_CASE:
        params = dict(params)
        params["outputFormats"] = ",".join(_parse_functional_output_formats(params))
    if generation_type == GEN_TYPE_JMETER_JMX:
        params = dict(params)
        params["jmxOutputMode"] = _parse_jmx_output_mode(params)
    work_root = await _get_work_root(db)
    Path(work_root).mkdir(parents=True, exist_ok=True)

    task = AiGenerationTask(
        task_name=task_name.strip(),
        generation_type=generation_type,
        input_type=input_type,
        input_filename=input_filename,
        output_filename=output_name,
        status=STATUS_PENDING,
        params_json=json.dumps(params, ensure_ascii=False),
    )
    stamp_create(task, user)
    task = await crud.add_task(db, task)

    task_dir = Path(work_root) / str(task.id)
    task_dir.mkdir(parents=True, exist_ok=True)
    input_path = task_dir / input_filename
    output_path = task_dir / output_name

    content = await input_file.read()
    async with aiofiles.open(input_path, "wb") as f:
        await f.write(content)

    task.work_dir = str(task_dir)
    task.input_path = str(input_path)
    task.output_path = str(output_path)
    _append_log(task, f"保存输入文件: {input_filename}")
    stamp_modify(task, user)
    await crud.update_task(db, task)
    return int(task.id)


async def run_generation_task(task_id: int) -> None:
    from app.db import session as session_module

    async with session_module.AsyncSessionLocal() as db:
        task = await crud.get_task(db, task_id)
        if task is None:
            return

        task.status = STATUS_RUNNING
        _append_log(task, f"开始调用 Codex 生成任务: {task.generation_type}")
        await crud.update_task(db, task)

        try:
            params = json.loads(task.params_json or "{}")
            codex_bin = await _get_codex_bin(db)
            timeout = await _get_timeout(db)
            _input_suffixes, _output_suffix, _input_type, artifact_type, success_log = _get_type_spec(task.generation_type)
            if task.generation_type == GEN_TYPE_JMETER_JMX:
                prompt = _build_jmx_prompt(
                    input_path=task.input_path,
                    output_path=task.output_path,
                    params=params,
                )
            else:
                output_formats = _parse_functional_output_formats(params)
                artifact_specs = _build_functional_artifact_specs(
                    output_path=task.output_path,
                    output_filename=task.output_filename,
                    formats=output_formats,
                )
                prompt_params = dict(params)
                prompt_params["outputFormats"] = ",".join(output_formats)
                for fmt, _filename, file_path in artifact_specs:
                    if fmt == "xmind":
                        prompt_params["xmindOutputPath"] = file_path
                prompt = _build_functional_case_prompt(
                    input_path=task.input_path,
                    output_path=task.output_path,
                    params=prompt_params,
                )
            codex_log = await _invoke_codex_cli(
                codex_bin=codex_bin,
                prompt=prompt,
                work_dir=task.work_dir,
                output_path=task.output_path,
                timeout=timeout,
            )
            if codex_log:
                _append_log(task, codex_log)

            if task.generation_type == GEN_TYPE_JMETER_JMX:
                jmx_output_mode = _parse_jmx_output_mode(params)
                if jmx_output_mode == JMX_OUTPUT_MODE_SPLIT:
                    jmx_paths = sorted(Path(task.work_dir).glob("*.jmx"))
                    if not jmx_paths:
                        raise ValueError("生成失败: 未生成JMX输出文件")
                    artifact_specs = []
                    for jmx_path in jmx_paths:
                        _validate_jmx(str(jmx_path))
                        artifact_specs.append((artifact_type, jmx_path.name, str(jmx_path)))
                    success_log = f"JMX XML校验成功，生成任务完成: {len(artifact_specs)} 个文件"
                else:
                    if not Path(task.output_path).is_file():
                        raise ValueError("生成失败: 未生成输出文件")
                    _validate_jmx(task.output_path)
                    artifact_specs = [(artifact_type, task.output_filename, task.output_path)]
            else:
                output_formats = _parse_functional_output_formats(params)
                artifact_specs = _build_functional_artifact_specs(
                    output_path=task.output_path,
                    output_filename=task.output_filename,
                    formats=output_formats,
                )
                success_log = f"功能测试用例生成完成: {'、'.join(output_formats)}"

            for item_artifact_type, filename, file_path in artifact_specs:
                path = Path(file_path)
                if not path.is_file():
                    raise ValueError(f"生成失败: 未生成输出文件 {filename}")
                if path.stat().st_size <= 0:
                    raise ValueError(f"生成失败: 输出文件为空 {filename}")
                artifact = AiGenerationArtifact(
                    task_id=task.id,
                    artifact_type=item_artifact_type,
                    filename=filename,
                    file_path=file_path,
                    file_size=path.stat().st_size,
                )
                stamp_create(artifact, UserContext(id=0, username="system", real_name="system"))
                await crud.add_artifact(db, artifact)

            task.status = STATUS_SUCCESS
            task.error_message = ""
            _append_log(task, success_log)
            await crud.update_task(db, task)
        except Exception as exc:
            log.warning("AI生成任务失败 id=%s", task_id, exc_info=True)
            await db.rollback()
            task = await crud.get_task(db, task_id)
            if task is None:
                return
            task.status = STATUS_FAILED
            task.error_message = str(exc)
            _append_log(task, str(exc))
            await crud.update_task(db, task)


async def get_task_list(db: AsyncSession, query: AiGenerationQuery) -> PageVO[AiGenerationTaskVO]:
    page: PageVO[AiGenerationTaskVO] = PageVO(page=query.page, size=query.size, total=0, list=[])
    total = await crud.count_tasks(
        db,
        task_name=query.task_name,
        generation_type=query.generation_type,
        status=query.status,
        creator=query.creator,
    )
    page.total = total
    if total <= 0:
        return page
    items = await crud.list_tasks(
        db,
        task_name=query.task_name,
        generation_type=query.generation_type,
        status=query.status,
        creator=query.creator,
        offset=PageVO.offset(query.page, query.size),
        limit=query.size,
    )
    result: list[AiGenerationTaskVO] = []
    for item in items:
        result.append(_task_to_vo(item, await crud.count_artifacts(db, item.id)))
    page.list = result
    return page


async def get_stats(db: AsyncSession) -> AiGenerationStatsVO:
    return AiGenerationStatsVO(
        total=await crud.count_tasks(db),
        pending=await crud.count_tasks(db, status=STATUS_PENDING),
        running=await crud.count_tasks(db, status=STATUS_RUNNING),
        success=await crud.count_tasks(db, status=STATUS_SUCCESS),
        failed=await crud.count_tasks(db, status=STATUS_FAILED),
    )


async def get_task_vo(db: AsyncSession, id: int) -> AiGenerationTaskVO:
    task = await crud.get_task(db, id)
    if task is None:
        raise MysteriousException(Codes.FILE_NOT_EXIST, message="生成任务不存在")
    return _task_to_vo(task, await crud.count_artifacts(db, id))


async def get_log(db: AsyncSession, id: int) -> str:
    task = await crud.get_task(db, id)
    if task is None:
        raise MysteriousException(Codes.FILE_NOT_EXIST, message="生成任务不存在")
    return task.generation_log or ""


async def list_artifacts(db: AsyncSession, task_id: int) -> list[AiGenerationArtifactVO]:
    task = await crud.get_task(db, task_id)
    if task is None:
        raise MysteriousException(Codes.FILE_NOT_EXIST, message="生成任务不存在")
    return [_artifact_to_vo(item) for item in await crud.list_artifacts(db, task_id)]


async def list_download_artifacts(
    db: AsyncSession,
    *,
    task_id: int,
    artifact_ids: list[int],
) -> list[AiGenerationArtifactVO]:
    task = await crud.get_task(db, task_id)
    if task is None:
        raise MysteriousException(Codes.FILE_NOT_EXIST, message="生成任务不存在")
    unique_ids = list(dict.fromkeys(artifact_ids))
    if not unique_ids:
        raise MysteriousException(Codes.PARAMS_EMPTY, message="请选择要下载的产物")
    items = await crud.list_artifacts_by_ids(db, task_id=task_id, artifact_ids=unique_ids)
    if len(items) != len(unique_ids):
        raise MysteriousException(Codes.FILE_NOT_EXIST, message="部分产物不存在或不属于当前任务")
    for item in items:
        if not os.path.exists(item.file_path):
            raise MysteriousException(Codes.FILE_NOT_EXIST, message=f"产物文件不存在: {item.filename}")
    return [_artifact_to_vo(item) for item in items]


def build_artifacts_zip(artifacts: list[AiGenerationArtifactVO], zip_path: str) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        used_names: set[str] = set()
        for artifact in artifacts:
            arcname = artifact.filename
            if arcname in used_names:
                path = Path(artifact.filename)
                arcname = f"{path.stem}_{artifact.id}{path.suffix}"
            used_names.add(arcname)
            zf.write(artifact.file_path, arcname)


async def get_artifact(db: AsyncSession, id: int) -> AiGenerationArtifactVO:
    artifact = await crud.get_artifact(db, id)
    if artifact is None:
        raise MysteriousException(Codes.FILE_NOT_EXIST, message="生成产物不存在")
    return _artifact_to_vo(artifact)


async def delete_task(db: AsyncSession, id: int) -> bool:
    task = await crud.get_task(db, id)
    if task is None:
        raise MysteriousException(Codes.FILE_NOT_EXIST, message="生成任务不存在")
    if task.work_dir and Path(task.work_dir).exists():
        shutil.rmtree(task.work_dir, ignore_errors=True)
    await crud.delete_artifacts_by_task(db, id)
    return await crud.delete_task(db, id)
