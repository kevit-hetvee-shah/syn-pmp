"""Session-wide test safety net: guarantees the test suite never makes a
real Portkey/LLM call, even indirectly through builder.build_client_deck,
and never a real Databricks call either.

pipeline/narrative_agent_runner.py's generate_narrative_slides() makes a
real call by default (that's the whole point of it) — SKIP_NARRATIVE_AGENT
is its explicit opt-out, used here (not in any individual test) so that
EVERY test, present or future, that touches build_client_deck stays free and
offline by construction, the same guarantee OFFLINE_PROMPTS gives app.py at
import time. Tests that specifically want to exercise the real-call code
path (test_narrative_agent_runner.py) mock build_agent directly instead of
relying on this flag being unset.

PM_DATABRICKS_* are force-cleared (not merely defaulted), same reasoning
learned on agents/pmp_agent (2026-11-02): tests/test_agent.py imports app.py,
whose top-level `load_dotenv(".env")` populates any env var not ALREADY set
in `os.environ` (python-dotenv's default `override=False`). Once this
agent's own `.env` carries real Databricks credentials (for local testing),
that import would otherwise leak them into the rest of the same pytest
process, flipping every data_access.is_configured() check to True for
unrelated tests. Plain assignment, not `setdefault`, so this also protects
against a developer having exported them directly in their shell.
"""

import os

os.environ.setdefault("SKIP_NARRATIVE_AGENT", "true")

for _var in (
    "PM_DATABRICKS_HOST",
    "PM_DATABRICKS_TOKEN",
    "PM_DATABRICKS_CATALOG",
    "PM_DATABRICKS_SCHEMA",
    "PM_DATABRICKS_WAREHOUSE_ID",
):
    os.environ[_var] = ""
