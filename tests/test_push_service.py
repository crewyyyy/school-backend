from datetime import datetime

from app.services.push import _format_ru_short_datetime, _notification_body, _notification_title


class _EventStub:
    def __init__(self, title: str | None, datetime_start: datetime | None, location: str | None):
        self.title = title
        self.datetime_start = datetime_start
        self.location = location


def test_notification_title():
    assert _notification_title("new") == "Новое мероприятие!"
    assert _notification_title("rescheduled") == "Мероприятие перенесено"
    assert _notification_title("updated") == "Мероприятие изменено"
    assert _notification_title("canceled") == "Мероприятие отменено"


def test_notification_body_format():
    event = _EventStub(
        title="Олимпиада по физике",
        datetime_start=datetime(2026, 2, 11, 13, 30),
        location="Актовый зал",
    )
    body = _notification_body(event)
    assert body == "Олимпиада по физике\n11 февр, 13:30\nАктовый зал"


def test_notification_body_fallbacks():
    event = _EventStub(title=None, datetime_start=None, location=None)
    body = _notification_body(event)
    assert body == "Без названия\nДата не указана\nЛокация не указана"


def test_format_ru_short_datetime():
    assert _format_ru_short_datetime(datetime(2026, 11, 5, 9, 7)) == "05 нояб, 09:07"
