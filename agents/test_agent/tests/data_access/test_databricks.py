"""Tests for databricks_executor.py using a mocked connector — no real
Databricks credentials needed or used. Verifies the wiring (validation,
executable_sql passed through, params passed through, results shaped into
dicts) without ever making a network call.
"""

from unittest.mock import MagicMock, patch

import pytest

from data_access import databricks as databricks_executor


def test_is_configured_requires_all_three_env_vars(monkeypatch) -> None:
    monkeypatch.delenv("DATABRICKS_SERVER_HOSTNAME", raising=False)
    monkeypatch.delenv("DATABRICKS_HTTP_PATH", raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    assert databricks_executor.is_configured() is False

    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", "x")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "y")
    assert databricks_executor.is_configured() is False  # token still missing

    monkeypatch.setenv("DATABRICKS_TOKEN", "z")
    assert databricks_executor.is_configured() is True


def test_execute_template_rejects_invalid_params_before_connecting(monkeypatch) -> None:
    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", "x")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "y")
    monkeypatch.setenv("DATABRICKS_TOKEN", "z")

    with patch("databricks.sql.connect") as mock_connect:
        with pytest.raises(ValueError, match="required"):
            databricks_executor.execute_template("segments_and_products_by_customer")
        mock_connect.assert_not_called()  # no network call for a rejected plan


def test_execute_template_passes_executable_sql_and_params(monkeypatch) -> None:
    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", "x")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "y")
    monkeypatch.setenv("DATABRICKS_TOKEN", "z")

    mock_cursor = MagicMock()
    mock_cursor.description = [("client",)]
    mock_cursor.fetchall.return_value = [("ACTURA",), ("SYMPHONIE",)]
    mock_cursor.__enter__.return_value = mock_cursor
    mock_connection = MagicMock()
    mock_connection.cursor.return_value = mock_cursor
    mock_connection.__enter__.return_value = mock_connection

    with patch("databricks.sql.connect", return_value=mock_connection) as mock_connect:
        rows = databricks_executor.execute_template("distinct_customers")

    mock_connect.assert_called_once_with(server_hostname="x", http_path="y", access_token="z")
    sql_used, kwargs = mock_cursor.execute.call_args
    assert "{{table:" not in sql_used[0]  # resolved before hitting the driver
    assert "venus_gold_prod.cp_sales_overview.cp_france_sales_insight" in sql_used[0]
    assert rows == [{"client": "ACTURA"}, {"client": "SYMPHONIE"}]
