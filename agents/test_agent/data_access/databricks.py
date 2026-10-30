"""Direct Databricks SQL execution for the approved templates in utils/sql_registry.py.

A pragmatic local-dev/testing shortcut, NOT the platform's sanctioned
production path — see sql_registry.py's module docstring: the AI Foundry
docs say Databricks should be reached through the MCP Gateway (which gives
AgentCore Identity's per-user on-behalf-of token for row-level security),
not a direct driver connection like this one. This module has no identity
propagation — it authenticates as whatever `DATABRICKS_TOKEN` is configured
with, not as the calling rep. Fine for getting real numbers into local
development; not fine to ship as-is.

Configuration (env vars, read at call time so changes don't need a restart
mid-session, matching this repo's `OFFLINE_PROMPTS`-style explicit-opt-in
pattern):
    DATABRICKS_SERVER_HOSTNAME
    DATABRICKS_HTTP_PATH       (the SQL warehouse's HTTP path)
    DATABRICKS_TOKEN           (a personal access token)

is_configured() is how callers (data_access/__init__.py) decide whether to
use this or fall back to the local sample — never silently guessed.
"""

from __future__ import annotations

import os

from utils import sql_registry

_HOSTNAME_VAR = "DATABRICKS_SERVER_HOSTNAME"
_HTTP_PATH_VAR = "DATABRICKS_HTTP_PATH"
_TOKEN_VAR = "DATABRICKS_TOKEN"


def is_configured() -> bool:
    return bool(os.environ.get(_HOSTNAME_VAR) and os.environ.get(_HTTP_PATH_VAR) and os.environ.get(_TOKEN_VAR))


def execute_template(template_id: str, **params: object) -> list[dict]:
    """Run an approved template against the real warehouse. Raises ValueError
    for an unknown template or invalid params (same validation as
    sql_registry — nothing runs without passing it), and whatever
    databricks-sql-connector raises for connection/auth/query failures
    (deliberately not swallowed — a configured-but-failing connection should
    be visible, not silently masked by a fallback).
    """
    template = sql_registry.get_template(template_id)
    errors = template.validate_params(params)
    if errors:
        raise ValueError(f"Invalid params for template '{template_id}': {'; '.join(errors)}")

    from databricks import sql as databricks_sql

    with databricks_sql.connect(
        server_hostname=os.environ[_HOSTNAME_VAR],
        http_path=os.environ[_HTTP_PATH_VAR],
        access_token=os.environ[_TOKEN_VAR],
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(template.executable_sql, parameters=params)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
