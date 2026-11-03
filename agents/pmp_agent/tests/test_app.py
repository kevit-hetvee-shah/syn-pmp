"""Smoke tests for the pmp_agent FastAPI app (health + agent-card)."""

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/ping")
    assert resp.status_code == 200


def test_ready() -> None:
    resp = client.get("/ready")
    assert resp.status_code == 200


def test_agent_card() -> None:
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    card = resp.json()
    assert "name" in card
    assert "skills" in card


def test_invocations_health_endpoint_registered_by_ag_ui() -> None:
    """ag_ui_langgraph's add_langgraph_fastapi_endpoint registers its own
    `<path>/health` route alongside the main AG-UI endpoint."""
    resp = client.get("/invocations/health")
    assert resp.status_code == 200
