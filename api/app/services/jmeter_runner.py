"""JMeter 子进程异步执行 + 完成回调。

对齐 Java JmxService.runJmx / debugJmx / stopJmx + DebugResultHandler / ExecuteResultHandler /
StopResultHandler 三个回调里的状态机和日志/JTL 解析。

事件流：
1) route → debug/run_testcase()：建报告 + testcase.status=RUN_ING → 调 launch_jmeter()
2) launch_jmeter() 立即返回，asyncio.Task 后台跑子进程
3) 子进程完成 → callback 解析 stdout / jmeter.log / jtl → 写 testcase.status + report.status + report.response_data

测试入口：`await wait_for_completion(report_id)` 同步等待。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from asyncio.subprocess import PIPE, Process

from lxml import etree
from sqlalchemy import select

from app.core.enums import ExecType, TestCaseStatus
from app.db import session as session_module
from app.models.report import Report
from app.models.testcase import TestCase

log = logging.getLogger(__name__)

# 内存登记后台子进程，按 report_id 索引，支持按执行独立 stop
_running_processes: dict[int, Process] = {}

_SUMMARY_ERROR_RE = re.compile(r"summary\s+=\s+0\s+in.*")
_RESULT_ERROR_RE = re.compile(r".*Err:\s+([1-9][0-9]*)\s+\(.*%\)")
_RUN_ERROR_RE = re.compile(r".*Error.*Exception")
_LOG_BEANSHELL_RE = re.compile(r".*Error invoking bsh method|.*NoClassDefFoundError")


def _check_output_failed(out: str) -> bool:
    """对齐 Java ResultHandler.checkResult 的三类 fail-patterns。"""
    return bool(
        _SUMMARY_ERROR_RE.search(out)
        or _RESULT_ERROR_RE.search(out)
        or _RUN_ERROR_RE.search(out)
    )


def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _log_has_error(path: str) -> bool:
    """对齐 Java DebugResultHandler.checkJMeterLog：jmeter.log 里若有 beanshell/NoClassDef 报错 → 失败。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if _LOG_BEANSHELL_RE.search(line):
                    return True
    except OSError:
        pass
    return False


def _parse_debug_response_data(xml_path: str) -> str:
    """对齐 Java DebugResultHandler.getResponseData：
    优先 <assertionResult>/<failureMessage>；否则 <responseData class="java.lang.String">；
    最大 500 字符。"""
    try:
        tree = etree.parse(xml_path)
    except Exception:
        return ""
    for sample in tree.iter():
        if sample.tag in ("httpSample", "sample"):
            for child in sample:
                if child.tag == "assertionResult":
                    for grand in child:
                        if grand.tag == "failureMessage" and grand.text:
                            return grand.text[:500]
            for child in sample:
                if child.tag == "responseData" and child.get("class") == "java.lang.String":
                    return (child.text or "")[:500]
    return ""


async def launch_jmeter(
    cmd: list[str],
    *,
    testcase_id: int,
    report_id: int,
    exec_type: int,
    jtl_path: str | None,
    log_file_path: str,
) -> asyncio.Task:
    """启动 JMeter 子进程（fire-and-forget）。按 report_id 注册，支持独立 kill。

    返回 asyncio.Task；调用方通常忽略。测试用 `wait_for_completion(report_id)` 同步等待。
    """
    task = asyncio.create_task(
        _run_and_callback(cmd, testcase_id, report_id, exec_type, jtl_path, log_file_path)
    )
    return task


async def launch_stop(report_id: int) -> bool:
    """按 report_id 停止指定执行：直接 kill 子进程 + 更新 DB 状态。

    返回 True 表示找到了进程并 kill；False 表示未找到（已结束或从未启动）。
    """
    proc = _running_processes.get(report_id)
    if proc is None:
        log.info("stop: report_id=%s 未找到运行中的进程", report_id)
        return False
    try:
        proc.kill()
    except Exception:
        log.exception("kill 子进程失败 report_id=%s", report_id)
        return False
    # DB 状态由 _run_and_callback 的 finally 块负责更新（process killed → proc.communicate 返回 → 走正常完成路径）
    return True


async def wait_for_completion(report_id: int, timeout: float = 30.0) -> None:
    """测试用：等指定报告的后台 task 跑完。"""
    proc = _running_processes.get(report_id)
    if proc is None:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except (TimeoutError, asyncio.TimeoutError):
        log.warning("wait_for_completion 超时 report_id=%s", report_id)


async def _run_and_callback(
    cmd: list[str],
    testcase_id: int,
    report_id: int,
    exec_type: int,
    jtl_path: str | None,
    log_file_path: str,
) -> None:
    out_str = ""
    exit_code = -1
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
        _running_processes[report_id] = proc
        stdout_bytes, _ = await proc.communicate()
        exit_code = proc.returncode or 0
        out_str = stdout_bytes.decode("utf-8", errors="replace")
    except Exception:
        log.exception("JMeter 启动失败 cmd=%s", cmd)
        try:
            await _update_testcase_and_report(testcase_id, report_id, TestCaseStatus.RUN_FAILED, None)
        finally:
            _running_processes.pop(report_id, None)
        return

    # proc.kill() 会导致进程被杀→ returncode < 0，视为失败
    if exit_code < 0:
        final_status = TestCaseStatus.RUN_FAILED
        response_data = None
    else:
        failed = _check_output_failed(out_str) or exit_code != 0
        final_status = TestCaseStatus.RUN_FAILED if failed else TestCaseStatus.RUN_SUCCESS

        response_data: str | None = None
        if exec_type == ExecType.DEBUG.value:
            if _file_size(log_file_path) >= 1024 * 1024:
                response_data = "调试日志过大, 请确认"
            elif final_status == TestCaseStatus.RUN_SUCCESS and jtl_path:
                response_data = _parse_debug_response_data(jtl_path)
            if _log_has_error(log_file_path):
                final_status = TestCaseStatus.RUN_FAILED

    try:
        await _update_testcase_and_report(testcase_id, report_id, final_status, response_data)
    finally:
        _running_processes.pop(report_id, None)


async def _update_testcase_and_report(
    testcase_id: int,
    report_id: int,
    status: TestCaseStatus,
    response_data: str | None,
) -> None:
    async with session_module.AsyncSessionLocal() as db:
        tc = (
            await db.execute(select(TestCase).where(TestCase.id == testcase_id))
        ).scalar_one_or_none()
        if tc is not None:
            tc.status = status.value
        rpt = await db.get(Report, report_id)
        if rpt is not None:
            rpt.status = status.value
            if response_data is not None:
                rpt.response_data = response_data
        await db.commit()
