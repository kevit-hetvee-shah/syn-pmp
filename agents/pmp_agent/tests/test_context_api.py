"""Tests for the Meeting Context intake API.

Deliberately imports context_api directly (not app.py) and mounts it on a
plain FastAPI() instance, so this suite runs without the AI Foundry SDK
installed and without ever touching the agent/Portkey code path.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import storage
from context_api import router

app = FastAPI()
app.include_router(router, prefix="/api")
client = TestClient(app)


def setup_function() -> None:
    storage._reset_for_tests()


def test_reference_data_endpoints_return_mock_lists() -> None:
    customers = client.get("/api/customers").json()
    assert customers["data_source"] == "local-sample-csv"
    assert "ACTURA" in customers["items"]

    assert "Business Review & Outlook" in client.get("/api/meeting-types").json()

    seasons = client.get("/api/seasons").json()
    assert seasons["items"]

    assert client.get("/api/locations").json()
    assert client.get("/api/regions").json() == ["EST", "NORD", "OUEST", "SUD EST", "SUD OUEST"]
    assert set(client.get("/api/distributor-profiles").json()) == {"Hedgehog", "Polar Bear", "Wolf", "Dolphin"}

    products = client.get("/api/product-suggestions").json()
    assert products["items"]

    scoped = client.get("/api/product-suggestions", params={"customer": "ACTURA"}).json()
    assert len(scoped["items"]) < len(products["items"])


def test_draft_lifecycle_and_readiness_gate() -> None:
    draft = {
        "customer_id": "ACTURA",
        "meeting_type": "Business Review & Outlook",
    }
    created = client.post("/api/meeting-context/draft", json=draft).json()
    draft_id = created["id"]
    assert created["status"] == "draft"

    readiness = client.get(f"/api/meeting-context/{draft_id}/readiness").json()
    assert readiness["ready_count"] == 2
    assert readiness["required_count"] == 6
    assert readiness["all_ready"] is False
    assert len(readiness["follow_up_prompts"]) == 4

    # Confirm is blocked while required fields are missing.
    resp = client.post(f"/api/meeting-context/{draft_id}/confirm")
    assert resp.status_code == 422

    complete = {
        "customer_id": "ACTURA",
        "meeting_type": "Business Review & Outlook",
        "meeting_date": "2026-11-12",
        "duration_minutes": 45,
        "season": "2025/2026",
        "campaign": "2026/2027",
        "objectives": "Review 2026 performance vs commitment.",
        "hook": "ELATUS Era delivered the strongest wheat season in 3 years.",
        "focus_products": ["ELATUS ERA"],
    }
    updated = client.put(f"/api/meeting-context/{draft_id}/draft", json=complete).json()
    assert updated["id"] == draft_id

    readiness = client.get(f"/api/meeting-context/{draft_id}/readiness").json()
    assert readiness["all_ready"] is True
    assert readiness["ready_count"] == readiness["required_count"] == 6

    confirmed = client.post(f"/api/meeting-context/{draft_id}/confirm").json()
    assert confirmed["status"] == "confirmed"

    deck_resp = client.get(f"/api/meeting-context/{draft_id}/deck")
    assert deck_resp.status_code == 200
    assert deck_resp.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert len(deck_resp.content) > 10_000


def test_deck_download_blocked_before_confirm() -> None:
    draft = {"customer_id": "ACTURA"}
    created = client.post("/api/meeting-context/draft", json=draft).json()
    resp = client.get(f"/api/meeting-context/{created['id']}/deck")
    assert resp.status_code == 409


def test_unknown_draft_returns_404() -> None:
    assert client.get("/api/meeting-context/does-not-exist").status_code == 404
    assert client.get("/api/meeting-context/does-not-exist/readiness").status_code == 404
    assert client.post("/api/meeting-context/does-not-exist/confirm").status_code == 404


def test_distributor_profile_questions_endpoint_shape() -> None:
    body = client.get("/api/distributor-profile-questions").json()
    assert body["pressure_to_protect_value"]["max_score"] == 60
    assert body["partnership_mode"]["max_score"] == 60
    assert len(body["pressure_to_protect_value"]["questions"]) == 5
    assert len(body["partnership_mode"]["questions"]) == 5
    first = body["pressure_to_protect_value"]["questions"][0]
    assert set(first.keys()) == {"key", "criterion", "question", "possible_scores"}


def test_known_distributor_profile_is_accepted_and_persisted() -> None:
    draft = {"customer_id": "ACTURA", "distributor_profile_known": True, "distributor_profile": "Wolf"}
    created = client.post("/api/meeting-context/draft", json=draft).json()
    assert created["distributor_profile"] == "Wolf"


def test_invalid_known_distributor_profile_is_rejected() -> None:
    draft = {"customer_id": "ACTURA", "distributor_profile_known": True, "distributor_profile": "Unicorn"}
    resp = client.post("/api/meeting-context/draft", json=draft)
    assert resp.status_code == 422


def test_dynamic_distributor_profile_is_computed_server_side_not_trusted_from_client() -> None:
    draft = {
        "customer_id": "ACTURA",
        "distributor_profile_known": False,
        # Client claims "Hedgehog" but the actual scores classify as "Wolf" — the
        # server must ignore the client's claim and compute its own answer.
        "distributor_profile": "Hedgehog",
        "pressure_scores": {"portfolio": 6, "competition_profitability": 18, "route_to_market": 12, "operations": 6, "urgency": 18},
        "partnership_scores": {"teams": 6, "governance": 18, "frameworks": 18, "services": 12, "ecosystem": 6},
    }
    created = client.post("/api/meeting-context/draft", json=draft).json()
    assert created["distributor_profile"] == "Wolf"


def test_dynamic_distributor_profile_can_be_skipped_entirely() -> None:
    draft = {"customer_id": "ACTURA", "distributor_profile_known": False, "pressure_scores": {}, "partnership_scores": {}}
    created = client.post("/api/meeting-context/draft", json=draft).json()
    assert created["distributor_profile"] is None


def test_invalid_dynamic_score_value_is_rejected() -> None:
    draft = {
        "customer_id": "ACTURA",
        "distributor_profile_known": False,
        "pressure_scores": {"portfolio": 5},  # 5 isn't one of portfolio's allowed scores [0,2,4,6]
    }
    resp = client.post("/api/meeting-context/draft", json=draft)
    assert resp.status_code == 422


def test_customer_location_endpoint_has_no_real_source_yet() -> None:
    """"Set the Region" story: Location auto-fills from the customer
    account's State, but no real source is connected yet — always None."""
    assert client.get("/api/customer-location", params={"customer": "ACTURA"}).json() == {"location": None}


def test_region_accepts_multiple_values_from_the_fixed_set() -> None:
    draft = {"customer_id": "ACTURA", "region": ["NORD", "SUD EST"]}
    created = client.post("/api/meeting-context/draft", json=draft).json()
    assert created["region"] == ["NORD", "SUD EST"]


def test_region_rejects_a_value_outside_the_fixed_set() -> None:
    draft = {"customer_id": "ACTURA", "region": ["NORD", "Unicorn"]}
    resp = client.post("/api/meeting-context/draft", json=draft)
    assert resp.status_code == 422


def test_location_is_read_only_server_side_not_trusted_from_client() -> None:
    """Same defense-in-depth pattern as distributor_profile: a client-sent
    `location` must never be trusted — the server always recomputes it (here,
    always None — see data_access.get_customer_location's docstring)."""
    draft = {"customer_id": "ACTURA", "location": "A client-claimed location that isn't real"}
    created = client.post("/api/meeting-context/draft", json=draft).json()
    assert created["location"] is None
