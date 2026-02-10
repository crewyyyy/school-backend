import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine import make_url


def _env_default(name: str, value: str) -> None:
    current = os.environ.get(name)
    if current is None or current.strip() == "":
        os.environ[name] = value


def _prepare_environment() -> None:
    _env_default("APP_PORT", "8000")
    _env_default("DATABASE_URL", "sqlite+pysqlite:////data/school.db")
    _env_default("MEDIA_DIR", "/data/media")
    _env_default("STORAGE_BACKEND", "local")
    _env_default("AUTO_CREATE_ADMIN", "true")
    _env_default("BOOTSTRAP_ADMIN_LOGIN", "admin")
    _env_default("BOOTSTRAP_ADMIN_PASSWORD", "admin123")
    _env_default("PUBLIC_SCHEME", "http")
    _env_default("PUBLIC_HOST", "localhost")
    _env_default("STANDALONE_ALLOW_EXTERNAL_DB", "false")
    _env_default("FCM_SERVICE_ACCOUNT_JSON", "/app/secrets/fcm-service-account.json")
    _env_default("FCM_TOPIC", "school_all")

    if not os.environ.get("MEDIA_BASE_URL", "").strip():
        os.environ["MEDIA_BASE_URL"] = (
            f"{os.environ['PUBLIC_SCHEME']}://{os.environ['PUBLIC_HOST']}:{os.environ['APP_PORT']}/media"
        )

    allow_external_db = os.environ["STANDALONE_ALLOW_EXTERNAL_DB"].strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if allow_external_db:
        return

    try:
        parsed_db = make_url(os.environ["DATABASE_URL"])
    except Exception:
        return

    is_postgres = parsed_db.drivername.startswith("postgres")
    is_localhost = parsed_db.host in {"localhost", "127.0.0.1", "::1"}
    if is_postgres and is_localhost:
        print(
            "Detected localhost Postgres URL in standalone mode; switching DATABASE_URL to SQLite (/data/school.db). "
            "Set STANDALONE_ALLOW_EXTERNAL_DB=true to keep external DB URL.",
            flush=True,
        )
        os.environ["DATABASE_URL"] = "sqlite+pysqlite:////data/school.db"


def _ensure_storage_paths() -> None:
    media_dir = Path(os.environ["MEDIA_DIR"])
    media_dir.mkdir(parents=True, exist_ok=True)

    database_url = os.environ["DATABASE_URL"]
    try:
        parsed_url = make_url(database_url)
    except Exception:
        return

    if not parsed_url.drivername.startswith("sqlite"):
        return

    db_path = parsed_url.database
    if not db_path or db_path == ":memory:":
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def _run(cmd: list[str]) -> None:
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    _prepare_environment()
    _ensure_storage_paths()

    print("Starting standalone School backend with:", flush=True)
    print(f"  DATABASE_URL={os.environ['DATABASE_URL']}", flush=True)
    print(f"  MEDIA_DIR={os.environ['MEDIA_DIR']}", flush=True)
    print(f"  MEDIA_BASE_URL={os.environ['MEDIA_BASE_URL']}", flush=True)
    fcm_path = Path(os.environ["FCM_SERVICE_ACCOUNT_JSON"])
    print(
        f"  FCM_SERVICE_ACCOUNT_JSON={fcm_path} (exists={fcm_path.exists()}) topic={os.environ['FCM_TOPIC']}",
        flush=True,
    )

    _run([sys.executable, "-m", "alembic", "upgrade", "head"])
    _run([sys.executable, "scripts/seed_classes.py"])
    _run(
        [
            sys.executable,
            "scripts/seed_admin.py",
            "--login",
            os.environ["BOOTSTRAP_ADMIN_LOGIN"],
            "--password",
            os.environ["BOOTSTRAP_ADMIN_PASSWORD"],
        ]
    )

    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            os.environ["APP_PORT"],
        ],
    )


if __name__ == "__main__":
    main()
