"""Real Databricks access for the approved templates in utils/sql_registry.py.

Runs each template's resolved SQL directly against a real SQL warehouse via
the Databricks SDK's Statement Execution API, with server-side named-
parameter binding for the template's `:param_name` placeholders (never
string-formatted into the SQL text). Same mechanism, same env vars
(`PM_DATABRICKS_HOST`/`TOKEN`/`CATALOG`/`SCHEMA`, optionally
`PM_DATABRICKS_WAREHOUSE_ID`) as agents/pmp_agent/mcp_tools/
databricks_gateway.py — see that module's docstring for the full design
rationale (why direct SQL rather than Unity Catalog Functions MCP, warehouse
auto-discovery, pagination).

A real workspace PAT token, not per-rep identity — the platform's sanctioned
production path is the AI Foundry MCP Gateway, which this is NOT; fine for
local dev/testing, not for shipping as-is.

is_configured() is how callers (data_access/__init__.py) decide whether to
use this or fall back to the local sample — never silently guessed.
"""

from __future__ import annotations

import os
import time

from utils import sql_registry

_HOST_VAR = "PM_DATABRICKS_HOST"
_TOKEN_VAR = "PM_DATABRICKS_TOKEN"
_CATALOG_VAR = "PM_DATABRICKS_CATALOG"
_SCHEMA_VAR = "PM_DATABRICKS_SCHEMA"
_WAREHOUSE_ID_VAR = "PM_DATABRICKS_WAREHOUSE_ID"

_EXECUTE_WAIT_TIMEOUT = "50s"
_POLL_INTERVAL_SECONDS = 2
_POLL_TIMEOUT_SECONDS = 240


def is_configured() -> bool:
    return bool(
        os.environ.get(_HOST_VAR)
        and os.environ.get(_TOKEN_VAR)
        and os.environ.get(_CATALOG_VAR)
        and os.environ.get(_SCHEMA_VAR)
    )


def _workspace_client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(host=os.environ[_HOST_VAR], token=os.environ[_TOKEN_VAR])


def _resolve_warehouse_id(workspace_client) -> str:
    explicit = os.environ.get(_WAREHOUSE_ID_VAR)
    if explicit:
        return explicit

    from databricks.sdk.service.sql import State

    warehouses = list(workspace_client.warehouses.list())
    if not warehouses:
        raise RuntimeError(
            f"No SQL warehouses visible to this Databricks token; set {_WAREHOUSE_ID_VAR} explicitly."
        )
    running = next((w for w in warehouses if w.state == State.RUNNING), None)
    return (running or warehouses[0]).id


def _wait_for_completion(workspace_client, response):
    from databricks.sdk.service.sql import StatementState

    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    while response.status.state in (StatementState.PENDING, StatementState.RUNNING):
        if time.monotonic() > deadline:
            raise RuntimeError(
                f"Statement {response.statement_id} did not complete within {_POLL_TIMEOUT_SECONDS}s "
                f"(last state: {response.status.state})"
            )
        time.sleep(_POLL_INTERVAL_SECONDS)
        response = workspace_client.statement_execution.get_statement(response.statement_id)

    if response.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"Statement {response.statement_id} failed: {response.status.state} — {response.status.error}")
    return response


def _rows_from_response(workspace_client, response) -> list[dict]:
    if response.manifest is None or response.manifest.schema is None:
        return []
    columns = [c.name for c in response.manifest.schema.columns]
    if response.manifest.truncated:
        raise RuntimeError(
            f"Statement {response.statement_id}'s result was server-side truncated — "
            "narrow the query or raise its row/byte limit rather than silently losing rows."
        )

    rows: list[dict] = []
    result = response.result
    while result is not None:
        for raw_row in result.data_array or []:
            rows.append(dict(zip(columns, raw_row)))
        if result.next_chunk_index is None:
            break
        result = workspace_client.statement_execution.get_statement_result_chunk_n(
            response.statement_id, result.next_chunk_index
        )
    return rows


def execute_template(template_id: str, **params: object) -> list[dict]:
    """Run an approved template's resolved SQL directly against the
    configured warehouse. Raises ValueError for an unknown template or
    invalid params (validated locally first), and RuntimeError for a
    failed/truncated statement or an unresolvable warehouse.
    """
    template = sql_registry.get_template(template_id)
    errors = template.validate_params(params)
    if errors:
        raise ValueError(f"Invalid params for template '{template_id}': {'; '.join(errors)}")

    from databricks.sdk.service.sql import StatementParameterListItem

    workspace_client = _workspace_client()
    warehouse_id = _resolve_warehouse_id(workspace_client)
    parameters = [
        StatementParameterListItem(name=name, value=None if value is None else str(value))
        for name, value in params.items()
    ]

    response = workspace_client.statement_execution.execute_statement(
        statement=template.executable_sql,
        warehouse_id=warehouse_id,
        catalog=os.environ[_CATALOG_VAR],
        schema=os.environ[_SCHEMA_VAR],
        parameters=parameters or None,
        wait_timeout=_EXECUTE_WAIT_TIMEOUT,
    )
    response = _wait_for_completion(workspace_client, response)
    return _rows_from_response(workspace_client, response)
