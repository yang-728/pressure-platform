"""AI generation API schemas."""

from __future__ import annotations

from app.schemas.base import BaseQuery, BaseVO, CamelModel


class AiGenerationQuery(BaseQuery):
    task_name: str | None = None
    generation_type: str | None = None
    status: str | None = None
    creator: str | None = None


class AiGenerationTaskVO(BaseVO):
    task_name: str = ""
    generation_type: str = ""
    input_type: str = ""
    input_filename: str = ""
    input_path: str = ""
    output_filename: str = ""
    output_path: str = ""
    work_dir: str = ""
    status: str = ""
    params_json: str = ""
    error_message: str = ""
    generation_log: str = ""
    artifact_count: int = 0


class AiGenerationArtifactVO(BaseVO):
    task_id: int = 0
    artifact_type: str = ""
    filename: str = ""
    file_path: str = ""
    file_size: int = 0


class AiGenerationArtifactDownloadRequest(CamelModel):
    artifact_ids: list[int] = []


class AiGenerationStatsVO(CamelModel):
    total: int = 0
    pending: int = 0
    running: int = 0
    success: int = 0
    failed: int = 0
