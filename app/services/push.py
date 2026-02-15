import logging
from pathlib import Path
from typing import Literal, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except ImportError:  # pragma: no cover
    firebase_admin = None
    credentials = None
    messaging = None

from app.core.config import get_settings
from app.models.device import Device
from app.models.event import Event

logger = logging.getLogger(__name__)

NotificationType = Literal["new", "rescheduled", "updated", "canceled"]

_INVALID_TOKEN_ERROR_MARKERS = (
    "not a valid fcm registration token",
    "invalid registration token",
    "registration-token-not-registered",
    "requested entity was not found",
    "unregistered",
)

_RU_MONTHS_SHORT = (
    "янв",
    "февр",
    "мар",
    "апр",
    "мая",
    "июн",
    "июл",
    "авг",
    "сент",
    "окт",
    "нояб",
    "дек",
)


def _format_ru_short_datetime(value) -> str:
    if value is None:
        return "Дата не указана"
    month = _RU_MONTHS_SHORT[max(0, min(11, value.month - 1))]
    return f"{value.day:02d} {month}, {value.hour:02d}:{value.minute:02d}"


def _notification_title(notification_type: NotificationType) -> str:
    if notification_type == "new":
        return "Новое мероприятие!"
    if notification_type == "rescheduled":
        return "Мероприятие перенесено"
    if notification_type == "updated":
        return "Мероприятие изменено"
    return "Мероприятие отменено"


def _notification_body(event: Event) -> str:
    title_line = event.title or "Без названия"
    datetime_line = _format_ru_short_datetime(event.datetime_start)
    location_line = event.location or "Локация не указана"
    return "\n".join((title_line, datetime_line, location_line))


class PushService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.enabled = False
        if firebase_admin is None:
            logger.info("Firebase SDK is not available, push notifications disabled.")
            return

        creds_path = Path(self.settings.fcm_service_account_json)
        if not creds_path.exists():
            logger.info("FCM service account is missing (%s), push notifications disabled.", creds_path)
            return

        if not firebase_admin._apps:
            cred = credentials.Certificate(str(creds_path))
            firebase_admin.initialize_app(cred)
        self.enabled = True

    def _build_message(
        self,
        event: Event,
        notification_type: NotificationType,
        *,
        topic: str | None = None,
        token: str | None = None,
    ):
        datetime_iso = event.datetime_start.isoformat() if event.datetime_start else ""
        title = _notification_title(notification_type)
        body = _notification_body(event)
        return messaging.Message(
            data={
                "event_id": event.id,
                "deep_link": f"school-events://event/{event.id}",
                "event_title": event.title or "",
                "event_datetime_start": datetime_iso,
                "event_location": event.location or "",
                "notification_type": notification_type,
                "push_title": title,
                "push_body": body,
            },
            android=messaging.AndroidConfig(priority="high"),
            topic=topic,
            token=token,
        )

    def _build_test_message(
        self,
        title: str,
        body: str,
        *,
        topic: str | None = None,
        token: str | None = None,
    ):
        return messaging.Message(
            data={
                "notification_type": "test",
                "event_id": "test",
                "deep_link": "school-events://event/test",
                "event_title": title,
                "event_datetime_start": "",
                "event_location": body,
                "push_title": title,
                "push_body": body,
            },
            android=messaging.AndroidConfig(priority="high"),
            topic=topic,
            token=token,
        )

    def _collect_device_tokens(self, db: Session | None) -> list[str]:
        if db is None:
            return []
        rows: Sequence[str] = db.scalars(select(Device.fcm_token)).all()
        return list(dict.fromkeys(token for token in rows if token))

    def _is_invalid_token_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return any(marker in message for marker in _INVALID_TOKEN_ERROR_MARKERS)

    def _prune_invalid_tokens(self, db: Session | None, tokens: list[str]) -> int:
        if db is None or not tokens:
            return 0

        unique_tokens = list(dict.fromkeys(token for token in tokens if token))
        if not unique_tokens:
            return 0

        rows = db.scalars(select(Device).where(Device.fcm_token.in_(unique_tokens))).all()
        for row in rows:
            db.delete(row)
        if rows:
            db.commit()
            logger.info("Removed %d invalid FCM token(s) from devices table.", len(rows))
        return len(rows)

    def _send_to_topic(self, event: Event, notification_type: NotificationType) -> bool:
        try:
            messaging.send(self._build_message(event, notification_type, topic=self.settings.fcm_topic))
            return True
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "FCM topic send failed for event %s notification_type=%s: %s",
                event.id,
                notification_type,
                exc,
            )
            return False

    def _send_to_tokens(
        self,
        event: Event,
        notification_type: NotificationType,
        tokens: list[str],
        db: Session | None = None,
    ) -> int:
        delivered = 0
        invalid_tokens: list[str] = []
        for token in tokens:
            try:
                messaging.send(self._build_message(event, notification_type, token=token))
                delivered += 1
            except Exception as exc:  # pragma: no cover
                if self._is_invalid_token_error(exc):
                    invalid_tokens.append(token)
                    logger.info(
                        "FCM token is invalid/unregistered for event %s token=%s notification_type=%s",
                        event.id,
                        token,
                        notification_type,
                    )
                else:
                    logger.warning(
                        "FCM token send failed for event %s token=%s notification_type=%s: %s",
                        event.id,
                        token,
                        notification_type,
                        exc,
                    )

        self._prune_invalid_tokens(db, invalid_tokens)
        return delivered

    def _send_event(self, event: Event, notification_type: NotificationType, db: Session | None = None) -> None:
        if not self.enabled:
            logger.info("Push skipped for event %s: service disabled.", event.id)
            return

        tokens = self._collect_device_tokens(db)
        delivered = self._send_to_tokens(event, notification_type, tokens, db=db) if tokens else 0

        if delivered == 0:
            topic_delivered = self._send_to_topic(event, notification_type)
            if topic_delivered:
                logger.info(
                    "Push sent to topic '%s' for event %s type=%s.",
                    self.settings.fcm_topic,
                    event.id,
                    notification_type,
                )
            else:
                logger.warning(
                    "Push not delivered for event %s type=%s: topic and token delivery failed.",
                    event.id,
                    notification_type,
                )
            return

        logger.info(
            "Push sent to %d registered devices for event %s type=%s.",
            delivered,
            event.id,
            notification_type,
        )

    def send_event_published(self, event: Event, db: Session | None = None) -> None:
        self._send_event(event, "new", db)

    def send_event_rescheduled(self, event: Event, db: Session | None = None) -> None:
        self._send_event(event, "rescheduled", db)

    def send_event_updated(self, event: Event, db: Session | None = None) -> None:
        self._send_event(event, "updated", db)

    def send_event_canceled(self, event: Event, db: Session | None = None) -> None:
        self._send_event(event, "canceled", db)

    def send_test_notification(
        self,
        title: str,
        body: str,
        db: Session | None = None,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "ok": False,
            "enabled": self.enabled,
            "topic": self.settings.fcm_topic,
            "tokens_total": 0,
            "tokens_delivered": 0,
            "tokens_pruned": 0,
            "topic_sent": False,
            "errors": [],
        }

        if not self.enabled:
            result["errors"] = ["push_service_disabled_or_missing_credentials"]
            return result

        tokens = self._collect_device_tokens(db)
        result["tokens_total"] = len(tokens)

        errors: list[str] = []
        delivered = 0
        invalid_tokens: list[str] = []
        for token in tokens:
            try:
                messaging.send(self._build_test_message(title, body, token=token))
                delivered += 1
            except Exception as exc:  # pragma: no cover
                if self._is_invalid_token_error(exc):
                    invalid_tokens.append(token)
                    errors.append(f"token:{token[:12]}... invalid_or_unregistered (removed)")
                else:
                    errors.append(f"token:{token[:12]}... {exc}")

        result["tokens_pruned"] = self._prune_invalid_tokens(db, invalid_tokens)

        result["tokens_delivered"] = delivered
        topic_sent = False
        if delivered == 0:
            try:
                messaging.send(self._build_test_message(title, body, topic=self.settings.fcm_topic))
                topic_sent = True
            except Exception as exc:  # pragma: no cover
                errors.append(f"topic:{self.settings.fcm_topic} {exc}")
        result["topic_sent"] = topic_sent

        result["ok"] = delivered > 0 or topic_sent
        if errors:
            result["errors"] = errors[:5]
        return result
