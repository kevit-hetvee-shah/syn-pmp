"""Deck Builder — thin re-export over pipeline/pipeline_graph.py, which owns
the actual top-level LangGraph StateGraph (fetch_facts -> generate_narrative
-> plan_deck -> write_spec -> validate -> render -> post_render). See that
module's docstring for the full pipeline description and the project's
LangGraph-as-orchestrator rationale.

Kept as its own thin module (rather than having callers import
pipeline.pipeline_graph directly) so `import builder` / `builder.
build_client_deck(...)` / `except builder.DeckValidationError` keep working
unchanged for context_api.py and the test suite.
"""

from __future__ import annotations

from pipeline.pipeline_graph import DeckRenderError, DeckValidationError, build_client_deck

__all__ = ["build_client_deck", "DeckValidationError", "DeckRenderError"]
