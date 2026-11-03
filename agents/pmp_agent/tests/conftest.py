"""Session-wide test safety net: guarantees the test suite never makes a
real Portkey/LLM call or a real Databricks call, regardless of what a
developer's own `.env` happens to have in it.

pipeline/narrative_agent_runner.py's generate_narrative_slides() makes a
real call by default (that's the whole point of it) — SKIP_NARRATIVE_AGENT
is its explicit opt-out, used here (not in any individual test) so that
EVERY test, present or future, that touches build_client_deck stays free and
offline by construction. Tests that specifically want to exercise the
real-call code path (test_narrative_agent_runner.py) mock build_brief_agent
directly instead of relying on this flag being unset.

PORTKEY_API_KEY/PORTKEY_BASE_URL get harmless placeholder defaults too:
building a LangGraph agent (agent_graphs/*.py's build_*_agent() functions,
including the one app.py builds at import time to serve the AG-UI endpoint)
needs `llm.get_chat_model()` to construct a real ChatOpenAI client, which
only requires *a* string key to exist — it never contacts Portkey until a
model call is actually made, which SKIP_NARRATIVE_AGENT above guarantees
never happens in tests.

PM_DATABRICKS_* are force-cleared (not merely defaulted) for the same
reason, learned the hard way (2026-11-02): tests/test_app.py imports app.py,
whose top-level `load_dotenv(".env")` call populates any env var that isn't
ALREADY set in `os.environ` (python-dotenv's default `override=False`). A
developer's real `.env` — needed for actually exercising mcp_tools/
databricks_gateway.py by hand — leaked real Databricks credentials into the
rest of the SAME pytest process this way, silently flipping every
data_access.is_configured() check to True for the remainder of the session
and sending dozens of unrelated tests (test_builder, test_data_access*,
test_narrative_facts, ...) against the real warehouse instead of the local
CSV sample, where they failed on real data not matching their hardcoded
local-sample expectations. Forcing these to an empty string here — BEFORE
any test module (and therefore `load_dotenv`) runs — keeps them `is_configured()
== False` for the whole suite no matter what `.env` contains; this is a
plain assignment, not `setdefault`, so it also protects against a developer
having exported them directly in their shell before invoking pytest.
"""

import os

os.environ.setdefault("SKIP_NARRATIVE_AGENT", "true")
os.environ.setdefault("PORTKEY_API_KEY", "test-placeholder-key")
os.environ.setdefault("PORTKEY_BASE_URL", "https://portkey.invalid/v1")

for _var in (
    "PM_DATABRICKS_HOST",
    "PM_DATABRICKS_TOKEN",
    "PM_DATABRICKS_CATALOG",
    "PM_DATABRICKS_SCHEMA",
    "PM_DATABRICKS_WAREHOUSE_ID",
):
    os.environ[_var] = ""
