import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture()
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "test.db"
    media_dir = tmp_path / "media"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("MEDIA_DIR", str(media_dir))
    monkeypatch.setenv("MEDIA_BASE_URL", "http://testserver/media")
    monkeypatch.setenv("AUTO_CREATE_ADMIN", "true")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_LOGIN", "admin")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "admin123")
    monkeypatch.setenv("FCM_SERVICE_ACCOUNT_JSON", str(tmp_path / "missing_fcm.json"))

    from app.core.config import clear_settings_cache
    from app.db.base import Base
    from app.db.session import get_engine, get_session_factory, reset_engine
    from app.main import create_app
    from app.models.class_model import SchoolClass

    clear_settings_cache()
    reset_engine()
    Base.metadata.create_all(bind=get_engine())

    with get_session_factory()() as db:
        for grade in range(5, 7):
            for letter in ("А", "Б"):
                name = f"{grade}{letter}"
                existing = db.scalar(select(SchoolClass).where(SchoolClass.name == name))
                if not existing:
                    db.add(SchoolClass(grade=grade, letter=letter, name=name, total_points=0))
        db.commit()

    app = create_app()
    with TestClient(app) as client:
        yield client

    Base.metadata.drop_all(bind=get_engine())
    reset_engine()


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/login", json={"login": "admin", "password": "admin123"})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

