"""Tests for data_access/databricks.py using a mocked WorkspaceClient — no
real Databricks credentials/warehouse needed or used. Verifies the wiring
(validation before any network call, warehouse auto-selection preferring a
RUNNING one, params passed through as named statement parameters, pagination
across result chunks, and the truncated/failed/no-warehouse error paths).
"""

from unittest.mock import MagicMock, patch

import pytest
from databricks.sdk.service.sql import State, StatementState

from data_access import databricks


def _set_env(monkeypatch) -> None:
    monkeypatch.setenv("PM_DATABRICKS_HOST", "https://x.cloud.databricks.com")
    monkeypatch.setenv("PM_DATABRICKS_TOKEN", "tok")
    monkeypatch.setenv("PM_DATABRICKS_CATALOG", "cat")
    monkeypatch.setenv("PM_DATABRICKS_SCHEMA", "sch")
    monkeypatch.delenv("PM_DATABRICKS_WAREHOUSE_ID", raising=False)


def test_is_configured_requires_all_four_env_vars(monkeypatch) -> None:
    for var in ("PM_DATABRICKS_HOST", "PM_DATABRICKS_TOKEN", "PM_DATABRICKS_CATALOG", "PM_DATABRICKS_SCHEMA"):
        monkeypatch.delenv(var, raising=False)
    assert databricks.is_configured() is False

    monkeypatch.setenv("PM_DATABRICKS_HOST", "https://x.cloud.databricks.com")
    monkeypatch.setenv("PM_DATABRICKS_TOKEN", "tok")
    monkeypatch.setenv("PM_DATABRICKS_CATALOG", "cat")
    assert databricks.is_configured() is False  # schema still missing

    monkeypatch.setenv("PM_DATABRICKS_SCHEMA", "sch")
    assert databricks.is_configured() is True


def test_execute_template_rejects_invalid_params_before_connecting(monkeypatch) -> None:
    _set_env(monkeypatch)
    with patch("data_access.databricks._workspace_client") as mock_workspace_client:
        with pytest.raises(ValueError, match="required"):
            databricks.execute_template("segments_and_products_by_customer")
        mock_workspace_client.assert_not_called()


def _mock_warehouse(id_: str, state: State) -> MagicMock:
    w = MagicMock()
    w.id = id_
    w.state = state
    return w


def _mock_statement_response(columns, rows, *, state=StatementState.SUCCEEDED, truncated=False, next_chunk_index=None):
    response = MagicMock()
    response.statement_id = "stmt-1"
    response.status.state = state
    response.status.error = None
    response.manifest.truncated = truncated
    column_mocks = []
    for name in columns:
        column_mock = MagicMock()
        column_mock.name = name
        column_mocks.append(column_mock)
    response.manifest.schema.columns = column_mocks
    response.result.data_array = rows
    response.result.next_chunk_index = next_chunk_index
    return response


def test_execute_template_auto_picks_the_running_warehouse(monkeypatch) -> None:
    _set_env(monkeypatch)
    client = MagicMock()
    client.warehouses.list.return_value = [
        _mock_warehouse("stopped-1", State.STOPPED),
        _mock_warehouse("running-1", State.RUNNING),
    ]
    client.statement_execution.execute_statement.return_value = _mock_statement_response(
        ["client"], [["ACTURA"], ["SYMPHONIE"]]
    )

    with patch("data_access.databricks._workspace_client", return_value=client):
        rows = databricks.execute_template("distinct_customers")

    assert rows == [{"client": "ACTURA"}, {"client": "SYMPHONIE"}]
    _, kwargs = client.statement_execution.execute_statement.call_args
    assert kwargs["warehouse_id"] == "running-1"


def test_execute_template_binds_params_as_named_statement_parameters(monkeypatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.setenv("PM_DATABRICKS_WAREHOUSE_ID", "wh-explicit")
    client = MagicMock()
    client.statement_execution.execute_statement.return_value = _mock_statement_response(
        ["season", "revenue"], [["2026/2027", "100.0"]]
    )

    with patch("data_access.databricks._workspace_client", return_value=client):
        databricks.execute_template("revenue_by_season_for_customer", customer="ACTURA")

    client.warehouses.list.assert_not_called()
    _, kwargs = client.statement_execution.execute_statement.call_args
    assert kwargs["warehouse_id"] == "wh-explicit"
    [param] = kwargs["parameters"]
    assert param.name == "customer"
    assert param.value == "ACTURA"


def test_execute_template_raises_on_server_side_truncation(monkeypatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.setenv("PM_DATABRICKS_WAREHOUSE_ID", "wh-1")
    client = MagicMock()
    client.statement_execution.execute_statement.return_value = _mock_statement_response(
        ["client"], [["ACTURA"]], truncated=True
    )

    with patch("data_access.databricks._workspace_client", return_value=client):
        with pytest.raises(RuntimeError, match="truncated"):
            databricks.execute_template("distinct_customers")


def test_execute_template_raises_on_statement_failure(monkeypatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.setenv("PM_DATABRICKS_WAREHOUSE_ID", "wh-1")
    client = MagicMock()
    failed = _mock_statement_response(["client"], [], state=StatementState.FAILED)
    failed.status.error = "permission denied"
    client.statement_execution.execute_statement.return_value = failed

    with patch("data_access.databricks._workspace_client", return_value=client):
        with pytest.raises(RuntimeError, match="permission denied"):
            databricks.execute_template("distinct_customers")
