"""定时任务 Schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseQuery, BaseVO, CamelModel
from app.schemas.testcase import RunParam


class ScheduleData(CamelModel):
    """调度配置数据。根据 scheduleType 不同，字段组合不同。"""

    time: str = ""  # "HH:mm" 或 "YYYY-MM-DD HH:mm:ss"（once 类型）
    days_of_week: list[int] | None = Field(default=None, alias="daysOfWeek")  # [1..7]，仅 weekly
    day_of_month: int | None = Field(default=None, alias="dayOfMonth")  # 1..31，仅 monthly


class ScheduledTaskParam(CamelModel):
    """创建/修改定时任务的请求参数"""

    test_case_id: int
    schedule_type: str = "once"  # once/daily/weekly/monthly
    schedule_data: ScheduleData = Field(default_factory=ScheduleData)
    run_param: RunParam = Field(default_factory=RunParam)


class ScheduledTaskVO(BaseVO):
    """定时任务响应 VO"""

    test_case_id: int = 0
    schedule_type: str = "once"
    schedule_data: str = "{}"
    run_param: str = "{}"
    enabled: int = 1
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None


class ScheduledTaskQuery(BaseQuery):
    """分页查询参数"""

    test_case_id: int | None = None
    enabled: int | None = None
