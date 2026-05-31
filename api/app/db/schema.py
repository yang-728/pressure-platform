"""Small compatibility migrations for deployments without Alembic."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from app.db.session import async_engine

log = logging.getLogger(__name__)


async def ensure_ai_generation_tables() -> None:
    """Create AI generation task/artifact tables for upgraded deployments."""
    async with async_engine.begin() as conn:
        dialect = conn.dialect.name
        tables = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
        if "mysterious_ai_generation_task" in tables and "mysterious_ai_generation_artifact" in tables:
            return

        id_type = "bigint(20) NOT NULL AUTO_INCREMENT" if dialect == "mysql" else "INTEGER NOT NULL"
        dt_default = "datetime NOT NULL DEFAULT CURRENT_TIMESTAMP" if dialect == "mysql" else "DATETIME NOT NULL"

        if "mysterious_ai_generation_task" not in tables:
            task_ddl = f"""
            CREATE TABLE mysterious_ai_generation_task (
                id {id_type},
                task_name varchar(255) NOT NULL DEFAULT '',
                generation_type varchar(64) NOT NULL DEFAULT '',
                input_type varchar(32) NOT NULL DEFAULT '',
                input_filename varchar(255) NOT NULL DEFAULT '',
                input_path varchar(512) NOT NULL DEFAULT '',
                output_filename varchar(255) NOT NULL DEFAULT '',
                output_path varchar(512) NOT NULL DEFAULT '',
                work_dir varchar(512) NOT NULL DEFAULT '',
                status varchar(32) NOT NULL DEFAULT 'pending',
                params_json text NOT NULL,
                error_message text NOT NULL,
                generation_log text NOT NULL,
                creator_id varchar(32) NOT NULL DEFAULT '',
                creator varchar(32) NOT NULL DEFAULT '',
                modifier_id varchar(32) NOT NULL DEFAULT '',
                modifier varchar(32) NOT NULL DEFAULT '',
                create_time {dt_default},
                modify_time {dt_default},
                PRIMARY KEY (id)
            )
            """
            await conn.execute(text(task_ddl))
            if dialect == "mysql":
                await conn.execute(text("CREATE INDEX idx_ai_generation_task_status ON mysterious_ai_generation_task (status)"))
                await conn.execute(text("CREATE INDEX idx_ai_generation_task_type ON mysterious_ai_generation_task (generation_type)"))
            log.info("已创建 mysterious_ai_generation_task 表")

        if "mysterious_ai_generation_artifact" not in tables:
            artifact_ddl = f"""
            CREATE TABLE mysterious_ai_generation_artifact (
                id {id_type},
                task_id bigint NOT NULL DEFAULT 0,
                artifact_type varchar(32) NOT NULL DEFAULT '',
                filename varchar(255) NOT NULL DEFAULT '',
                file_path varchar(512) NOT NULL DEFAULT '',
                file_size int NOT NULL DEFAULT 0,
                creator_id varchar(32) NOT NULL DEFAULT '',
                creator varchar(32) NOT NULL DEFAULT '',
                modifier_id varchar(32) NOT NULL DEFAULT '',
                modifier varchar(32) NOT NULL DEFAULT '',
                create_time {dt_default},
                modify_time {dt_default},
                PRIMARY KEY (id)
            )
            """
            await conn.execute(text(artifact_ddl))
            if dialect == "mysql":
                await conn.execute(text("CREATE INDEX idx_ai_generation_artifact_task_id ON mysterious_ai_generation_artifact (task_id)"))
            log.info("已创建 mysterious_ai_generation_artifact 表")


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


_CSV_COLUMNS = {
    "distribution_strategy": {
        "mysql": "varchar(32) NOT NULL DEFAULT 'shared' COMMENT '分布式参数文件读取策略'",
        "default": "VARCHAR(32) NOT NULL DEFAULT 'shared'",
    },
}

_USER_ROLE_COLUMNS = {
    "role_id": {
        "mysql": "bigint NOT NULL DEFAULT 0 COMMENT '用户角色ID'",
        "default": "INTEGER NOT NULL DEFAULT 0",
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


async def ensure_csv_distribution_columns() -> None:
    """Add CSV distribution strategy column for existing databases."""
    async with async_engine.begin() as conn:
        dialect = conn.dialect.name
        columns = await conn.run_sync(
            lambda sync_conn: {
                col["name"] for col in inspect(sync_conn).get_columns("mysterious_csv")
            }
        )
        for name, definitions in _CSV_COLUMNS.items():
            if name in columns:
                continue
            ddl = definitions["mysql"] if dialect == "mysql" else definitions["default"]
            await conn.execute(text(f"ALTER TABLE mysterious_csv ADD COLUMN {name} {ddl}"))
            log.info("已补齐 mysterious_csv.%s 字段", name)


async def ensure_rbac_schema() -> None:
    """Create RBAC role tables and add user.role_id for upgraded deployments."""
    async with async_engine.begin() as conn:
        dialect = conn.dialect.name
        tables = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
        id_type = "bigint(20) NOT NULL AUTO_INCREMENT" if dialect == "mysql" else "INTEGER NOT NULL"
        dt_default = "datetime NOT NULL DEFAULT CURRENT_TIMESTAMP" if dialect == "mysql" else "DATETIME NOT NULL"

        if "mysterious_role" not in tables:
            await conn.execute(text(f"""
            CREATE TABLE mysterious_role (
                id {id_type},
                name varchar(128) NOT NULL DEFAULT '',
                code varchar(64) NOT NULL DEFAULT '',
                description varchar(255) NOT NULL DEFAULT '',
                builtin int NOT NULL DEFAULT 0,
                creator_id varchar(32) NOT NULL DEFAULT '',
                creator varchar(32) NOT NULL DEFAULT '',
                modifier_id varchar(32) NOT NULL DEFAULT '',
                modifier varchar(32) NOT NULL DEFAULT '',
                create_time {dt_default},
                modify_time {dt_default},
                PRIMARY KEY (id)
            )
            """))
            if dialect == "mysql":
                await conn.execute(text("CREATE UNIQUE INDEX uk_mysterious_role_code ON mysterious_role (code)"))
            log.info("已创建 mysterious_role 表")

        if "mysterious_role_permission" not in tables:
            await conn.execute(text(f"""
            CREATE TABLE mysterious_role_permission (
                id {id_type},
                role_id bigint NOT NULL DEFAULT 0,
                permission_code varchar(64) NOT NULL DEFAULT '',
                PRIMARY KEY (id)
            )
            """))
            if dialect == "mysql":
                await conn.execute(text("CREATE INDEX idx_role_permission_role_id ON mysterious_role_permission (role_id)"))
            log.info("已创建 mysterious_role_permission 表")

        user_columns = await conn.run_sync(
            lambda sync_conn: {
                col["name"] for col in inspect(sync_conn).get_columns("mysterious_user")
            }
        )
        for name, definitions in _USER_ROLE_COLUMNS.items():
            if name in user_columns:
                continue
            ddl = definitions["mysql"] if dialect == "mysql" else definitions["default"]
            await conn.execute(text(f"ALTER TABLE mysterious_user ADD COLUMN {name} {ddl}"))
            log.info("已补齐 mysterious_user.%s 字段", name)


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
