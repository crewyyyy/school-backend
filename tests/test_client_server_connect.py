from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def test_health_endpoint_is_available_for_client(app_client: TestClient):
    response = app_client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "ok"


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
