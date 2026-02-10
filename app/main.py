from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api.router import api_router
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import get_session_factory
from app.models import admin as _admin_model  # noqa: F401
from app.models.admin import Admin


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if settings.auto_create_admin:
            session_factory = get_session_factory()
            with session_factory() as db:
                existing = db.scalar(select(Admin).where(Admin.login == settings.bootstrap_admin_login))
                if not existing:
                    admin = Admin(
                        login=settings.bootstrap_admin_login,
                        password_hash=hash_password(settings.bootstrap_admin_password),
                        role="admin",
                    )
                    db.add(admin)
                    db.commit()
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    settings.media_path.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(settings.media_path)), name="media")
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
