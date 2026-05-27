"""AI generation routes."""

from __future__ import annotations

import os
import tempfile
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.codes import Codes
from app.core.context import UserContext
from app.core.exceptions import MysteriousException
from app.core.response import PageVO, Response, success
from app.db.session import get_db
from app.deps.auth import get_current_user_dep
from app.schemas.ai_generation import (
    AiGenerationArtifactDownloadRequest,
    AiGenerationArtifactVO,
    AiGenerationQuery,
    AiGenerationStatsVO,
    AiGenerationTaskVO,
)
from app.services import ai_generation as service

router = APIRouter(
    prefix="/ai-generation",
    tags=["ai-generation"],
    dependencies=[Depends(get_current_user_dep)],
)


@router.post(
    "/tasks",
    summary="创建AI用例生成任务",
    response_model=Response[int],
    response_model_by_alias=True,
)
async def create_generation_task(
    background_tasks: BackgroundTasks,
    taskName: str = Form(...),
    generationType: str = Form("jmeter_jmx"),
    outputFilename: str = Form(...),
    protocol: str = Form("http"),
    host: str = Form(""),
    port: str = Form(""),
    threads: int = Form(1),
    rampUp: int = Form(1),
    loopCount: int = Form(1),
    jmxOutputMode: str = Form("single"),
    generateAssertion: bool = Form(False),
    generateCsvParam: bool = Form(False),
    customRequirement: str = Form(""),
    outputFormats: str = Form("xlsx"),
    designer: str = Form(""),
    splitByModule: bool = Form(True),
    includeDetailScenarios: bool = Form(True),
    inputFile: UploadFile = File(...),
    current: UserContext = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
) -> Response[int]:
    params = {
        "protocol": protocol,
        "host": host,
        "port": port,
        "threads": threads,
        "rampUp": rampUp,
        "loopCount": loopCount,
        "jmxOutputMode": jmxOutputMode,
        "generateAssertion": generateAssertion,
        "generateCsvParam": generateCsvParam,
        "customRequirement": customRequirement,
        "outputFormats": outputFormats,
        "designer": designer,
        "splitByModule": splitByModule,
        "includeDetailScenarios": includeDetailScenarios,
    }
    task_id = await service.create_task(
        db,
        task_name=taskName,
        generation_type=generationType,
        output_filename=outputFilename,
        input_file=inputFile,
        user=current,
        params=params,
    )
    background_tasks.add_task(service.run_generation_task, task_id)
    return success(task_id)


@router.get(
    "/tasks",
    summary="分页查询AI生成任务",
    response_model=Response[PageVO[AiGenerationTaskVO]],
    response_model_by_alias=True,
)
async def list_generation_tasks(
    query: AiGenerationQuery = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Response[PageVO[AiGenerationTaskVO]]:
    return success(await service.get_task_list(db, query))


@router.get(
    "/stats",
    summary="AI生成任务统计",
    response_model=Response[AiGenerationStatsVO],
    response_model_by_alias=True,
)
async def generation_stats(db: AsyncSession = Depends(get_db)) -> Response[AiGenerationStatsVO]:
    return success(await service.get_stats(db))


@router.get(
    "/tasks/{id}",
    summary="AI生成任务详情",
    response_model=Response[AiGenerationTaskVO],
    response_model_by_alias=True,
)
async def get_generation_task(id: int, db: AsyncSession = Depends(get_db)) -> Response[AiGenerationTaskVO]:
    return success(await service.get_task_vo(db, id))


@router.get(
    "/tasks/{id}/log",
    summary="AI生成任务日志",
    response_model=Response[str],
    response_model_by_alias=True,
)
async def get_generation_log(id: int, db: AsyncSession = Depends(get_db)) -> Response[str]:
    return success(await service.get_log(db, id))


@router.get(
    "/tasks/{id}/artifacts",
    summary="AI生成产物列表",
    response_model=Response[list[AiGenerationArtifactVO]],
    response_model_by_alias=True,
)
async def list_generation_artifacts(
    id: int,
    db: AsyncSession = Depends(get_db),
) -> Response[list[AiGenerationArtifactVO]]:
    return success(await service.list_artifacts(db, id))


@router.get("/artifacts/{id}/view", summary="AI生成产物预览")
async def view_generation_artifact(id: int, db: AsyncSession = Depends(get_db)) -> PlainTextResponse:
    artifact = await service.get_artifact(db, id)
    if not os.path.exists(artifact.file_path):
        raise MysteriousException(Codes.FILE_NOT_EXIST)
    if not artifact.filename.endswith((".jmx", ".md", ".txt", ".json", ".csv", ".dat", ".log")):
        return PlainTextResponse("该产物为二进制文件不支持在线预览，请下载后查看。")
    with open(artifact.file_path, encoding="utf-8") as f:
        return PlainTextResponse(f.read())


@router.get("/artifacts/{id}/download", summary="AI生成产物下载")
async def download_generation_artifact(id: int, db: AsyncSession = Depends(get_db)) -> FileResponse:
    artifact = await service.get_artifact(db, id)
    if not os.path.exists(artifact.file_path):
        raise MysteriousException(Codes.FILE_NOT_EXIST)
    return FileResponse(
        artifact.file_path,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{quote(artifact.filename)}"'},
    )


@router.post("/tasks/{id}/artifacts/download", summary="批量下载AI生成产物")
async def download_generation_artifacts(
    id: int,
    body: AiGenerationArtifactDownloadRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    artifacts = await service.list_download_artifacts(db, task_id=id, artifact_ids=body.artifact_ids)
    zip_file = tempfile.NamedTemporaryFile(prefix=f"ai-generation-{id}-", suffix=".zip", delete=False)
    zip_path = zip_file.name
    zip_file.close()
    service.build_artifacts_zip(artifacts, zip_path)
    background_tasks.add_task(os.remove, zip_path)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{quote(f"ai-generation-{id}-artifacts.zip")}"'},
    )


@router.delete(
    "/tasks/{id}",
    summary="删除AI生成任务",
    response_model=Response[bool],
    response_model_by_alias=True,
)
async def delete_generation_task(id: int, db: AsyncSession = Depends(get_db)) -> Response[bool]:
    return success(await service.delete_task(db, id))
