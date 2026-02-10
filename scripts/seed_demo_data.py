from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import base64
import sys

from sqlalchemy import delete, select

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.admin import Admin
from app.models.class_model import SchoolClass
from app.models.event import Event
from app.models.event_block import EventBlock
from app.models.point_transaction import PointTransaction


DEMO_PREFIX = "[DEMO]"
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO3f2I0AAAAASUVORK5CYII="
)


def ensure_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(PNG_1X1)


def main() -> None:
    settings = get_settings()
    media_root = settings.media_path
    media_root.mkdir(parents=True, exist_ok=True)
    session_factory = get_session_factory()

    with session_factory() as db:
        admin = db.scalar(select(Admin).where(Admin.login == settings.bootstrap_admin_login))
        if not admin:
            raise RuntimeError("Admin user not found. Run seed_admin first.")

        demo_events = db.scalars(select(Event).where(Event.title.like(f"{DEMO_PREFIX}%"))).all()
        demo_ids = [event.id for event in demo_events]
        if demo_ids:
            db.execute(delete(EventBlock).where(EventBlock.event_id.in_(demo_ids)))
            db.execute(delete(Event).where(Event.id.in_(demo_ids)))

        now = datetime.now(UTC)
        event_templates = [
            ("День науки", "Актовый зал"),
            ("Турнир по баскетболу", "Спортзал"),
            ("Концерт талантов", "Сцена"),
            ("Ярмарка проектов", "Фойе"),
            ("Олимпиадный интенсив", "Кабинет 301"),
        ]

        for index, (title, location) in enumerate(event_templates):
            event_id = f"demo-event-{index + 1}"
            banner_relative = f"events/{event_id}/banner/banner.png"
            banner_path = media_root / banner_relative
            ensure_file(banner_path)

            event = Event(
                id=event_id,
                title=f"{DEMO_PREFIX} {title}",
                datetime_start=now + timedelta(days=index + 1, hours=10 + index),
                location=location,
                banner_image_url=f"{settings.media_base_url.rstrip('/')}/{banner_relative}",
                status="published",
                created_by_admin_id=admin.id,
                created_at=now - timedelta(minutes=5 * index),
            )
            db.add(event)

            text_block = EventBlock(
                id=f"demo-block-text-{index + 1}",
                event_id=event_id,
                type="text",
                text=f"{DEMO_PREFIX} Подробности мероприятия: {title}.",
                image_url=None,
                sort_order=1,
            )
            image_relative = f"events/{event_id}/blocks/image.png"
            image_path = media_root / image_relative
            ensure_file(image_path)
            image_block = EventBlock(
                id=f"demo-block-image-{index + 1}",
                event_id=event_id,
                type="image",
                text=None,
                image_url=f"{settings.media_base_url.rstrip('/')}/{image_relative}",
                sort_order=2,
            )
            db.add(text_block)
            db.add(image_block)

        classes = db.scalars(select(SchoolClass).order_by(SchoolClass.grade, SchoolClass.letter)).all()
        for idx, school_class in enumerate(classes[:6]):
            delta = 5 + idx * 2
            tx = PointTransaction(
                id=f"demo-points-{idx + 1}",
                class_id=school_class.id,
                delta_points=delta,
                category="Демо",
                reason=f"{DEMO_PREFIX} Стартовые баллы",
                created_by_admin_id=admin.id,
                created_at=now - timedelta(hours=idx),
            )
            school_class.total_points += delta
            db.add(tx)
            db.add(school_class)

        db.commit()

    print("Demo data seeded: 5 events, event blocks, and sample point transactions.")


if __name__ == "__main__":
    main()

