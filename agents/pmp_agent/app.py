"""Pre-Meeting Preparation agent — built on LangGraph, served via FastAPI.

Serving layer: plain FastAPI, with the Conversation Agent (the one agent
here meant for direct chat interaction — Deck Planner, Content Verifier and
Brief are invoked programmatically from the deck-build pipeline, never as a
standalone chat agent) bridged onto the AG-UI wire protocol via
`ag_ui_langgraph.add_langgraph_fastapi_endpoint`. That keeps `POST
/invocations` (SSE event stream) working the same way it did under the old
ai_foundry_platform_sdk.app.create_agui_app, for any AgentCore Runtime
registration or AG-UI client that expects it — even though the
meeting-context-ui only ever calls the plain REST routes in context_api.py.

Loading .env here (not left to a framework) matches the old app.py's
reasoning: whatever needs .env values (model credentials, CORS_ORIGINS) must
see them before this module's own top-level code runs.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv(".env")

from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from agent_graphs.conversation_agent import (  # noqa: E402
    DESCRIPTION as AGENT_DESCRIPTION,
)
from agent_graphs.conversation_agent import (  # noqa: E402
    NAME as AGENT_NAME,
)
from agent_graphs.conversation_agent import build_conversation_agent  # noqa: E402

AGENT_VERSION = "0.1.0"

app = FastAPI(title=AGENT_NAME, version=AGENT_VERSION)

# Local dev only: lets a browser-based test UI running on another origin/port
# call this agent. Set CORS_ORIGINS="*" (or a comma-separated allowlist) in
# .env for local testing; leave unset in deployed environments.
if os.environ.get("CORS_ORIGINS"):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ["CORS_ORIGINS"].split(","),
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/ping")
def ping() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    return {"status": "ready"}


@app.get("/.well-known/agent-card.json")
def agent_card() -> dict:
    return {
        "name": AGENT_NAME,
        "description": AGENT_DESCRIPTION,
        "version": AGENT_VERSION,
        "skills": [
            {
                "id": "context_sufficiency",
                "name": "Context Sufficiency Check",
                "description": (
                    "Judge whether a meeting-context draft has enough specific, usable "
                    "information to proceed — not just whether required fields are non-empty."
                ),
                "tags": ["conversation", "context", "pre-meeting"],
            }
        ],
    }


# Per-request agent build (same timing the old create_agui_app used) — needs
# real Portkey credentials to exist (not necessarily be valid) at this point;
# see agent_graphs/conversation_agent.py's docstring and tests/conftest.py's
# placeholder-credential defaults for why that's safe in tests too.
_conversation_graph = build_conversation_agent()
_langgraph_agent = LangGraphAgent(name=AGENT_NAME, graph=_conversation_graph, description=AGENT_DESCRIPTION)
add_langgraph_fastapi_endpoint(app, _langgraph_agent, path="/invocations")

# Meeting Context intake step (wizard step 1) — plain REST, mock data only.
# This router never imports a model client and cannot trigger a Portkey
# call; see context_api.py's module docstring for the scope boundary.
from context_api import router as meeting_context_router  # noqa: E402

app.include_router(meeting_context_router, prefix="/api")
