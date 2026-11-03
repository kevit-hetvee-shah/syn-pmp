"""Databricks access for data_access/__init__.py's dispatch layer — delegates
to mcp_tools.databricks_gateway (the real MCP client). Kept as its own module,
rather than importing mcp_tools directly from __init__.py, so data_access's
public shape (`is_configured()` / `execute_template()`) stays identical to
every other backend module here, same as the local_csv module it's dispatched
alongside.
"""

from __future__ import annotations

from mcp_tools.databricks_gateway import execute_template, is_configured

__all__ = ["is_configured", "execute_template"]
