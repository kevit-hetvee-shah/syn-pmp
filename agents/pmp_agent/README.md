# PMP Agent (Pre-Meeting Preparation)

Pre-meeting sales deck pipeline, rebuilt on **LangGraph** — agents, tools, and
MCP, replacing the AI Foundry Platform SDK / Strands version in
`agents/test_agent`. Serving layer: FastAPI, with the Conversation Agent
bridged onto the **AG-UI** protocol (`ag-ui-langgraph`) at `POST /invocations`.

> Infra (Terraform, Dockerfile, CI) is intentionally out of scope for this
> package right now — application code only. See `agents/test_agent/infra/`
> for the deployment plumbing pattern to adapt once this agent is ready to
> deploy for real.

## Quick Start

```bash
# Install dependencies
python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"

# Configure environment
cp .env.example .env   # then fill in PORTKEY_API_KEY (or AGENT_SECRET_NAME) for real model calls

# Run locally
.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8081
```

## Test

```bash
.venv/bin/pytest
```

Tests never make a real Portkey call — `tests/conftest.py` sets
`SKIP_NARRATIVE_AGENT=true` and placeholder Portkey credentials for the whole
session (building a LangGraph agent needs *a* model client to exist; it's
never actually invoked in tests).

## Architecture

```
pmp_agent/
├── app.py                     # FastAPI + AG-UI (/invocations), REST (context_api), health, agent-card
├── builder.py                 # thin re-export of pipeline/pipeline_graph.py
├── context_api.py             # meeting-context wizard REST API (unchanged from test_agent)
├── llm/
│   └── portkey.py             # ChatOpenAI wired to the Portkey gateway (every agent's model client)
├── mcp_tools/
│   └── databricks_gateway.py  # real Databricks access: each template's SQL run directly (Statement Execution API)
├── agent_graphs/               # LangGraph agents (langchain.agents.create_agent)
│   ├── conversation_agent.py   # served live via the AG-UI endpoint
│   ├── deck_planner_agent.py   # not invoked by the live pipeline (deterministic path used instead)
│   ├── content_verifier_agent.py  # not invoked by default
│   └── brief_agent.py          # the ONE agent actually invoked — real Portkey call per narrative slide
├── pipeline/
│   ├── pipeline_graph.py       # top-level LangGraph StateGraph: the whole deck-build pipeline
│   ├── data_analyst.py         # fetch real data, record every value as a Fact
│   ├── narrative_agent_runner.py  # invokes agent_graphs.brief_agent, converts+validates its output
│   ├── deck_planner.py / deck_plan.py / spec_writer.py / validator.py / renderer.py / diagnostics.py
│   └── models.py               # DeckSpec / FactRegistry / Narrative*Block dataclasses
├── data_access/                 # real Databricks (via MCP) when configured, local CSV sample otherwise
└── utils/, sql/templates/, meeting-context-ui/, chat-ui/   # unchanged from test_agent
```

Only `pipeline/narrative_agent_runner.py` (via `agent_graphs/brief_agent.py`)
makes a real model call by default — every other agent graph is defined and
testable but not wired into the live pipeline, same invariant the old
AI-Foundry-SDK agents followed. Importing any `agent_graphs/*.py` module never
needs credentials; calling its `build_*_agent()` function does (it resolves a
real Portkey-backed model client) — see `agent_graphs/conversation_agent.py`'s
docstring.

## Environment Variables

| Variable | Required | Description |
|----------|----------|--------------|
| `PORTKEY_BASE_URL` | Yes | Portkey gateway URL |
| `PORTKEY_API_KEY` | Local dev | Direct key, bypasses AWS Secrets Manager |
| `AGENT_SECRET_NAME` | Deployed | AWS Secrets Manager secret holding `PORTKEY_API_KEY` (legacy `PORTKEY_SECRET_NAME` also accepted) |
| `PORTKEY_MODEL_ID` | No | Default model ID (e.g. `@az-openai/gpt-4.1-mini`) |
| `SKIP_NARRATIVE_AGENT` | No | Skip the one real LLM call; render placeholder narrative slides |
| `PM_DATABRICKS_HOST` / `PM_DATABRICKS_TOKEN` / `PM_DATABRICKS_CATALOG` / `PM_DATABRICKS_SCHEMA` | No | Real Databricks access (see repo-root `example.env`). Unset falls back to the local CSV sample |
| `PM_DATABRICKS_WAREHOUSE_ID` | No | Pins the SQL warehouse; unset auto-picks the first RUNNING one |
| `CORS_ORIGINS` | No | Local dev only, for a browser UI calling `/invocations` |
| `ALLOWED_AD_GROUPS` | No | Not yet wired (JWT RBAC was out of scope for this migration) |
