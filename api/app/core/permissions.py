"""Menu-level permission codes used by backend authorization and frontend menus."""

from __future__ import annotations

PERMISSION_TESTCASE = "testcase"
PERMISSION_CASE_GENERATION = "case-generation"
PERMISSION_JMX = "jmx"
PERMISSION_CSV = "csv"
PERMISSION_JAR = "jar"
PERMISSION_EXECUTION = "execution"
PERMISSION_REPORT = "report"
PERMISSION_NODE = "node"
PERMISSION_CONFIG = "config"
PERMISSION_USER = "user"
PERMISSION_AUDIT = "audit"
PERMISSION_ROLE = "role"

ADMIN_ROLE_CODE = "admin"
DEFAULT_ROLE_CODE = "user"


PERMISSION_CATALOG = [
    {"code": PERMISSION_TESTCASE, "name": "用例管理", "group": "MANAGE", "sort": 10},
    {"code": PERMISSION_CASE_GENERATION, "name": "用例生成", "group": "MANAGE", "sort": 20},
    {"code": PERMISSION_JMX, "name": "脚本管理", "group": "MANAGE", "sort": 30},
    {"code": PERMISSION_CSV, "name": "数据管理", "group": "MANAGE", "sort": 40},
    {"code": PERMISSION_JAR, "name": "依赖管理", "group": "MANAGE", "sort": 50},
    {"code": PERMISSION_EXECUTION, "name": "执行队列", "group": "EXECUTE", "sort": 10},
    {"code": PERMISSION_REPORT, "name": "执行结果", "group": "EXECUTE", "sort": 20},
    {"code": PERMISSION_NODE, "name": "节点管理", "group": "SYSTEM", "sort": 10},
    {"code": PERMISSION_CONFIG, "name": "配置管理", "group": "SYSTEM", "sort": 20},
    {"code": PERMISSION_USER, "name": "用户管理", "group": "SYSTEM", "sort": 30},
    {"code": PERMISSION_ROLE, "name": "角色管理", "group": "SYSTEM", "sort": 40},
    {"code": PERMISSION_AUDIT, "name": "审计日志", "group": "SYSTEM", "sort": 50},
]

ALL_PERMISSION_CODES = [item["code"] for item in PERMISSION_CATALOG]
