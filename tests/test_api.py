from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def test_classes_auth_required(app_client: TestClient):
    response = app_client.get("/classes")
    assert response.status_code == 401


def test_points_update_and_history(app_client: TestClient):
    headers = auth_headers(app_client)
    classes_response = app_client.get("/classes", headers=headers)
    assert classes_response.status_code == 200
    classes = classes_response.json()
    assert classes

    class_id = classes[0]["id"]
    points_response = app_client.post(
        f"/classes/{class_id}/points",
        headers=headers,
        json={"delta_points": 10, "category": "Спорт", "reason": "Турнир"},
    )
    assert points_response.status_code == 200
    assert points_response.json()["total_points"] == 10

    history_response = app_client.get(f"/classes/{class_id}/points/history", headers=headers)
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 1
    assert history[0]["delta_points"] == 10
    assert history[0]["category"] == "Спорт"


def test_publish_requires_banner(app_client: TestClient):
    headers = auth_headers(app_client)
    dt = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    create_response = app_client.post(
        "/events",
        headers=headers,
        json={"title": "День науки", "datetime_start": dt, "location": "Актовый зал"},
    )
    assert create_response.status_code == 200
    event_id = create_response.json()["id"]

    publish_response = app_client.post(f"/events/{event_id}/publish", headers=headers)
    assert publish_response.status_code == 400
    detail = publish_response.json()["detail"]
    assert detail["error"] == "missing_required_fields"
    assert "banner_image_url" in detail["fields"]


def test_upcoming_events_sorted_by_datetime(app_client: TestClient):
    headers = auth_headers(app_client)
    first_dt = datetime.now(UTC) + timedelta(days=2)
    second_dt = datetime.now(UTC) + timedelta(days=1)

    first_id = _create_and_publish_event(app_client, headers, "Событие 1", first_dt)
    second_id = _create_and_publish_event(app_client, headers, "Событие 2", second_dt)

    response = app_client.get("/events", params={"from": "now", "limit": 20})
    assert response.status_code == 200
    events = response.json()
    ids = [item["id"] for item in events]
    assert second_id in ids and first_id in ids
    assert ids.index(second_id) < ids.index(first_id)


def test_event_admin_editing_flow(app_client: TestClient):
    headers = auth_headers(app_client)

    create_response = app_client.post("/events", headers=headers, json={"title": "Черновик"})
    assert create_response.status_code == 200
    event_id = create_response.json()["id"]

    new_dt = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    update_response = app_client.patch(
        f"/events/{event_id}",
        headers=headers,
        json={"title": "Обновленное", "datetime_start": new_dt, "location": "Каб. 42"},
    )
    assert update_response.status_code == 200

    image_block_response = app_client.post(
        f"/events/{event_id}/blocks/image",
        headers=headers,
        params={"sort_order": 2},
        files={"image": ("block.png", b"img-bytes", "image/png")},
    )
    assert image_block_response.status_code == 200, image_block_response.text
    assert image_block_response.json()["type"] == "image"

    admin_list_response = app_client.get("/events/admin", headers=headers, params={"status": "all"})
    assert admin_list_response.status_code == 200
    admin_ids = [item["id"] for item in admin_list_response.json()]
    assert event_id in admin_ids


def test_event_delete_flow(app_client: TestClient):
    headers = auth_headers(app_client)
    create_response = app_client.post("/events", headers=headers, json={"title": "Удаляемое мероприятие"})
    assert create_response.status_code == 200
    event_id = create_response.json()["id"]

    delete_response = app_client.delete(f"/events/{event_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["ok"] is True

    details_response = app_client.get(f"/events/{event_id}")
    assert details_response.status_code == 404


def _create_and_publish_event(client: TestClient, headers: dict[str, str], title: str, dt: datetime) -> str:
    create_response = client.post(
        "/events",
        headers=headers,
        json={"title": title, "datetime_start": dt.isoformat(), "location": "Спортзал"},
    )
    assert create_response.status_code == 200, create_response.text
    event_id = create_response.json()["id"]

    banner_response = client.post(
        f"/events/{event_id}/banner",
        headers=headers,
        files={"banner": ("banner.png", b"png-bytes", "image/png")},
    )
    assert banner_response.status_code == 200, banner_response.text

    publish_response = client.post(f"/events/{event_id}/publish", headers=headers)
    assert publish_response.status_code == 200, publish_response.text
    return event_id
