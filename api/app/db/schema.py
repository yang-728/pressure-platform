"""Small compatibility migrations for deployments without Alembic."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from app.db.session import async_engine

log = logging.getLogger(__name__)


_REPORT_COLUMNS = {
    "region": {
        "mysql": "varchar(255) NOT NULL DEFAULT '' COMMENT '执行区域快照'",
        "default": "VARCHAR(255) NOT NULL DEFAULT ''",
    },
    "service_name": {
        "mysql": "varchar(128) NOT NULL DEFAULT '' COMMENT '执行时服务名快照'",
        "default": "VARCHAR(128) NOT NULL DEFAULT ''",
    },
    "total_threads": {
        "mysql": "int NOT NULL DEFAULT 0 COMMENT '执行时总线程数快照'",
        "default": "INTEGER NOT NULL DEFAULT 0",
    },
    "slave_count": {
        "mysql": "int NOT NULL DEFAULT 0 COMMENT '执行时压力机数快照'",
        "default": "INTEGER NOT NULL DEFAULT 0",
    },
    "grafana_instance": {
        "mysql": "varchar(255) NOT NULL DEFAULT '' COMMENT '执行时Grafana instance快照'",
        "default": "VARCHAR(255) NOT NULL DEFAULT ''",
    },
    "artifact_dir": {
        "mysql": "varchar(255) NOT NULL DEFAULT '' COMMENT '执行产物目录快照'",
        "default": "VARCHAR(255) NOT NULL DEFAULT ''",
    },
}


async def ensure_report_snapshot_columns() -> None:
    """Add report snapshot columns for existing databases.

    The project currently uses docker/init.sql instead of Alembic. This keeps
    upgraded deployments from failing when the ORM starts selecting new columns.
    """
    async with async_engine.begin() as conn:
        dialect = conn.dialect.name
        columns = await conn.run_sync(
            lambda sync_conn: {
                col["name"] for col in inspect(sync_conn).get_columns("mysterious_report")
            }
        )
        for name, definitions in _REPORT_COLUMNS.items():
            if name in columns:
                continue
            ddl = definitions["mysql"] if dialect == "mysql" else definitions["default"]
            await conn.execute(text(f"ALTER TABLE mysterious_report ADD COLUMN {name} {ddl}"))
            log.info("已补齐 mysterious_report.%s 字段", name)


async def ensure_scheduled_task_log_table() -> None:
    """Create scheduled task execution log table for upgraded deployments."""
    async with async_engine.begin() as conn:
        dialect = conn.dialect.name
        tables = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
        if "mysterious_scheduled_task_log" in tables:
            return
        id_type = "bigint(20) NOT NULL AUTO_INCREMENT" if dialect == "mysql" else "INTEGER NOT NULL"
        dt_default = "datetime NOT NULL DEFAULT CURRENT_TIMESTAMP" if dialect == "mysql" else "DATETIME NOT NULL"
        ddl = f"""
        CREATE TABLE mysterious_scheduled_task_log (
            id {id_type},
            scheduled_task_id bigint NOT NULL DEFAULT 0,
            test_case_id bigint NOT NULL DEFAULT 0,
            trigger_type varchar(16) NOT NULL DEFAULT '',
            status varchar(16) NOT NULL DEFAULT '',
            reason text NOT NULL,
            message text NOT NULL,
            region varchar(255) NOT NULL DEFAULT '',
            requested_slave_count int NOT NULL DEFAULT 0,
            available_slave_count int NOT NULL DEFAULT 0,
            allocated_slave_count int NOT NULL DEFAULT 0,
            slave_hosts text NOT NULL,
            run_param text NOT NULL,
            trigger_time datetime NOT NULL,
            next_run_at datetime NULL,
            create_time {dt_default},
            PRIMARY KEY (id)
        )
        """
        await conn.execute(text(ddl))
        if dialect == "mysql":
            await conn.execute(text("CREATE INDEX idx_scheduled_task_log_task_id ON mysterious_scheduled_task_log (scheduled_task_id)"))
            await conn.execute(text("CREATE INDEX idx_scheduled_task_log_test_case_id ON mysterious_scheduled_task_log (test_case_id)"))
        log.info("已创建 mysterious_scheduled_task_log 表")
