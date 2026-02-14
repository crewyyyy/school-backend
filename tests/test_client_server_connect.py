from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def test_health_endpoint_is_available_for_client(app_client: TestClient):
    response = app_client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "ok"
    assert isinstance(payload.get("version"), str)


def test_system_info_endpoint_returns_backend_version(app_client: TestClient):
    response = app_client.get("/system/info")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("app_name"), str)
    assert isinstance(payload.get("app_env"), str)
    assert isinstance(payload.get("app_version"), str)
    assert "push_credentials_exists" in payload
    assert "registered_devices" in payload


def test_admin_events_contract_for_client_parsing(app_client: TestClient):
    headers = auth_headers(app_client)

    create_response = app_client.post("/events", headers=headers, json={"title": "Contract draft"})
    assert create_response.status_code == 200, create_response.text
    event_id = create_response.json()["id"]

    list_response = app_client.get("/events/admin", headers=headers, params={"status": "all"})
    assert list_response.status_code == 200, list_response.text
    items = list_response.json()

    event_item = next((item for item in items if item["id"] == event_id), None)
    assert event_item is not None
    assert isinstance(event_item.get("id"), str)
    assert isinstance(event_item.get("status"), str)

    for key in ("title", "datetime_start", "location", "banner_image_url"):
        assert key in event_item
        assert event_item[key] is None or isinstance(event_item[key], str)


def test_push_test_endpoint_requires_auth(app_client: TestClient):
    response = app_client.post(
        "/push/test",
        json={"title": "test", "body": "body"},
    )
    assert response.status_code == 401


def test_push_test_endpoint_calls_service(app_client: TestClient, monkeypatch):
    from app.api import system as system_api

    headers = auth_headers(app_client)

    expected = {
        "ok": True,
        "enabled": True,
        "topic": "school_all",
        "tokens_total": 1,
        "tokens_delivered": 1,
        "topic_sent": False,
        "errors": [],
    }

    def fake_send_test_notification(title: str, body: str, db=None):
        assert title == "Ping"
        assert body == "Push check"
        return expected

    monkeypatch.setattr(system_api.push_service, "send_test_notification", fake_send_test_notification)

    response = app_client.post(
        "/push/test",
        headers=headers,
        json={"title": "Ping", "body": "Push check"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == expected
