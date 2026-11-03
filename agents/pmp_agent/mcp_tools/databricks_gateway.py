"""Real Databricks access for data_access/__init__.py's dispatch layer.

Runs each approved `sql_registry.py` template's resolved SQL directly against
a real SQL warehouse via the Databricks SDK's Statement Execution API
(`WorkspaceClient.statement_execution`), using server-side named-parameter
binding (`StatementParameterListItem`) for the template's `:param_name`
placeholders — never string-formatted into the SQL text.

Direct by design (2026-11-02 decision): the first version of this module
tried Databricks' Unity Catalog **Functions** MCP server
(`{host}/api/2.0/mcp/functions/{catalog}/{schema}`), matching each
approved template to a same-named Unity Catalog function. Verified live
against the real `venus_gold_prod.cp_sales_overview` catalog.schema: auth
and the MCP handshake both worked, but that schema holds plain tables, not
registered UC functions — `list_tools()` always came back empty, so there
was nothing to call. The project wants direct query execution against the
real tables instead (SQL templates stay the reviewed/typed-parameter source
of truth; they are just no longer expected to have a matching UC function),
so this module now calls the Statement Execution API directly.

This is a real workspace PAT token (`PM_DATABRICKS_TOKEN`), not a per-rep
on-behalf-of identity — unlike the originally-sanctioned MCP Gateway path,
every query here runs as whichever identity the token belongs to, same
caveat the old direct `databricks-sql-connector` module carried (see
`sql_registry.py`'s module docstring).

Configuration (`example.env` at the repo root):
    PM_DATABRICKS_HOST       workspace URL, e.g. https://xxx.cloud.databricks.com
    PM_DATABRICKS_TOKEN      a personal access token
    PM_DATABRICKS_CATALOG    default catalog for unqualified names (templates
                              fully qualify their own tables, so this mostly
                              just sets the session's default context)
    PM_DATABRICKS_SCHEMA     default schema, same caveat as catalog above
    PM_DATABRICKS_WAREHOUSE_ID   optional — pins which SQL warehouse to use.
                              Unset: auto-picks the first RUNNING warehouse
                              visible to the token, else the first warehouse
                              in the list (Databricks auto-starts a stopped
                              warehouse on first query; polling below waits
                              out that cold-start).

is_configured() gates every call, same as before: unset env vars mean
data_access/__init__.py falls back to the local CSV sample, never a silent
guess about which backend answered.
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

_EXECUTE_WAIT_TIMEOUT = "50s"  # Statement Execution API's own max synchronous wait
_POLL_INTERVAL_SECONDS = 2
_POLL_TIMEOUT_SECONDS = 240  # covers a cold warehouse start, not just query time


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
    """`execute_statement`'s own `wait_timeout` caps synchronous waiting at
    50s — a cold-starting (STOPPED) warehouse can take longer than that to
    come up, so poll `get_statement` the rest of the way rather than
    treating a still-PENDING/RUNNING result as done.
    """
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
    invalid params (validated locally first — nothing is sent over the wire
    without passing it), and RuntimeError for a failed/truncated statement or
    an unresolvable warehouse (not swallowed, same reasoning as the
    direct-connector module this replaces).
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
