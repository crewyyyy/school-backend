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
        json={"delta_points": 10, "category": "sport", "reason": "tournament"},
    )
    assert points_response.status_code == 200
    assert points_response.json()["total_points"] == 10

    history_response = app_client.get(f"/classes/{class_id}/points/history", headers=headers)
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 1
    assert history[0]["delta_points"] == 10
    assert history[0]["category"] == "sport"


def test_public_classes_top_available_and_sorted(app_client: TestClient):
    headers = auth_headers(app_client)
    classes_response = app_client.get("/classes", headers=headers)
    assert classes_response.status_code == 200
    classes = classes_response.json()
    assert len(classes) >= 2

    class_id_first = classes[0]["id"]
    class_id_second = classes[1]["id"]

    points_response_first = app_client.post(
        f"/classes/{class_id_first}/points",
        headers=headers,
        json={"delta_points": 5, "category": "test", "reason": "a"},
    )
    assert points_response_first.status_code == 200

    points_response_second = app_client.post(
        f"/classes/{class_id_second}/points",
        headers=headers,
        json={"delta_points": 15, "category": "test", "reason": "b"},
    )
    assert points_response_second.status_code == 200

    public_response = app_client.get("/classes/public/top", params={"limit": 10})
    assert public_response.status_code == 200
    public_items = public_response.json()
    assert public_items
    assert public_items[0]["id"] == class_id_second
    assert public_items[0]["total_points"] >= public_items[1]["total_points"]


def test_publish_requires_banner(app_client: TestClient):
    headers = auth_headers(app_client)
    dt = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    create_response = app_client.post(
        "/events",
        headers=headers,
        json={"title": "science day", "datetime_start": dt, "location": "assembly hall"},
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

    first_id = _create_and_publish_event(app_client, headers, "event 1", first_dt)
    second_id = _create_and_publish_event(app_client, headers, "event 2", second_dt)

    response = app_client.get("/events", params={"from": "now", "limit": 20})
    assert response.status_code == 200
    events = response.json()
    ids = [item["id"] for item in events]
    assert second_id in ids and first_id in ids
    assert ids.index(second_id) < ids.index(first_id)


def test_event_admin_editing_flow(app_client: TestClient):
    headers = auth_headers(app_client)

    create_response = app_client.post("/events", headers=headers, json={"title": "draft"})
    assert create_response.status_code == 200
    event_id = create_response.json()["id"]

    new_dt = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    update_response = app_client.patch(
        f"/events/{event_id}",
        headers=headers,
        json={"title": "updated", "datetime_start": new_dt, "location": "room 42"},
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
    create_response = app_client.post("/events", headers=headers, json={"title": "event to delete"})
    assert create_response.status_code == 200
    event_id = create_response.json()["id"]

    delete_response = app_client.delete(f"/events/{event_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["ok"] is True

    details_response = app_client.get(f"/events/{event_id}")
    assert details_response.status_code == 404


def test_publish_notifies_only_first_publish(app_client: TestClient, monkeypatch):
    from app.api import events as events_api

    calls: list[str] = []

    def _fake_send_event_published(event, db=None):
        calls.append(event.id)

    monkeypatch.setattr(events_api.push_service, "send_event_published", _fake_send_event_published)

    headers = auth_headers(app_client)
    event_id = _create_event_with_banner(app_client, headers, "publish-once", datetime.now(UTC) + timedelta(days=2))

    first_publish = app_client.post(f"/events/{event_id}/publish", headers=headers)
    assert first_publish.status_code == 200
    second_publish = app_client.post(f"/events/{event_id}/publish", headers=headers)
    assert second_publish.status_code == 200

    assert calls == [event_id]


def test_update_published_datetime_sends_rescheduled_push(app_client: TestClient, monkeypatch):
    from app.api import events as events_api

    rescheduled_calls: list[str] = []
    updated_calls: list[str] = []

    monkeypatch.setattr(
        events_api.push_service,
        "send_event_rescheduled",
        lambda event, db=None: rescheduled_calls.append(event.id),
    )
    monkeypatch.setattr(
        events_api.push_service,
        "send_event_updated",
        lambda event, db=None: updated_calls.append(event.id),
    )

    headers = auth_headers(app_client)
    event_id = _create_and_publish_event(app_client, headers, "published-to-reschedule", datetime.now(UTC) + timedelta(days=3))

    patch_response = app_client.patch(
        f"/events/{event_id}",
        headers=headers,
        json={"datetime_start": (datetime.now(UTC) + timedelta(days=5)).isoformat()},
    )
    assert patch_response.status_code == 200
    assert rescheduled_calls == [event_id]
    assert updated_calls == []


def test_update_published_title_sends_updated_push(app_client: TestClient, monkeypatch):
    from app.api import events as events_api

    rescheduled_calls: list[str] = []
    updated_calls: list[str] = []

    monkeypatch.setattr(
        events_api.push_service,
        "send_event_rescheduled",
        lambda event, db=None: rescheduled_calls.append(event.id),
    )
    monkeypatch.setattr(
        events_api.push_service,
        "send_event_updated",
        lambda event, db=None: updated_calls.append(event.id),
    )

    headers = auth_headers(app_client)
    event_id = _create_and_publish_event(app_client, headers, "published-to-update", datetime.now(UTC) + timedelta(days=4))

    patch_response = app_client.patch(
        f"/events/{event_id}",
        headers=headers,
        json={"title": "published-to-update-v2", "location": "new hall"},
    )
    assert patch_response.status_code == 200
    assert updated_calls == [event_id]
    assert rescheduled_calls == []


def test_delete_published_event_sends_canceled_push(app_client: TestClient, monkeypatch):
    from app.api import events as events_api

    canceled_calls: list[str] = []
    monkeypatch.setattr(
        events_api.push_service,
        "send_event_canceled",
        lambda event, db=None: canceled_calls.append(event.id),
    )

    headers = auth_headers(app_client)
    event_id = _create_and_publish_event(app_client, headers, "published-to-delete", datetime.now(UTC) + timedelta(days=2))

    delete_response = app_client.delete(f"/events/{event_id}", headers=headers)
    assert delete_response.status_code == 200
    assert canceled_calls == [event_id]


def _create_event_with_banner(client: TestClient, headers: dict[str, str], title: str, dt: datetime) -> str:
    create_response = client.post(
        "/events",
        headers=headers,
        json={"title": title, "datetime_start": dt.isoformat(), "location": "test location"},
    )
    assert create_response.status_code == 200, create_response.text
    event_id = create_response.json()["id"]

    banner_response = client.post(
        f"/events/{event_id}/banner",
        headers=headers,
        files={"banner": ("banner.png", b"png-bytes", "image/png")},
    )
    assert banner_response.status_code == 200, banner_response.text
    return event_id


def _create_and_publish_event(client: TestClient, headers: dict[str, str], title: str, dt: datetime) -> str:
    event_id = _create_event_with_banner(client, headers, title, dt)

    publish_response = client.post(f"/events/{event_id}/publish", headers=headers)
    assert publish_response.status_code == 200, publish_response.text
    return event_id
