"""Smoke tests for the test_agent agent."""

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_health():
    resp = client.get("/ping")
    assert resp.status_code == 200


def test_agent_card():
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    card = resp.json()
    assert "name" in card
    assert "skills" in card
