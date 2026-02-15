#!/usr/bin/env python3
"""
One-file Telegram bot for EduFlow push notifications.

Container env variables:
  TG_BOT_TOKEN                 required
  TG_ADMIN_CHAT_ID             required (single telegram chat id)
  TG_BOT_ALLOWED_CHAT_IDS      optional comma-separated list
  TG_BOT_API_BASE_URL          default: http://backend:8000
  TG_BOT_API_LOGIN             default: admin
  TG_BOT_API_PASSWORD          default: admin123
  TG_BOT_DEFAULT_TITLE         default: EduFlow notification
"""

from __future__ import annotations

import asyncio
import io
import os
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Optional

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message


HTTP_TIMEOUT_SECONDS = 15
API_BASE_URL = os.getenv("TG_BOT_API_BASE_URL", "http://backend:8000").rstrip("/")
DEFAULT_TITLE = os.getenv("TG_BOT_DEFAULT_TITLE", "EduFlow notification")
BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
API_LOGIN = os.getenv("TG_BOT_API_LOGIN", "admin").strip()
API_PASSWORD = os.getenv("TG_BOT_API_PASSWORD", "admin123").strip()

RECON_NOTIFICATION_TYPES = {"new", "rescheduled", "canceled"}


def _parse_allowed_chat_ids() -> set[int]:
    values: set[int] = set()

    admin_chat_id = os.getenv("TG_ADMIN_CHAT_ID", "").strip()
    if admin_chat_id:
        values.add(int(admin_chat_id))

    extra_raw = os.getenv("TG_BOT_ALLOWED_CHAT_IDS", "").strip()
    if extra_raw:
        for part in extra_raw.split(","):
            token = part.strip()
            if token:
                values.add(int(token))

    return values


ALLOWED_CHAT_IDS = _parse_allowed_chat_ids()


@dataclass
class ApiAuthState:
    token: Optional[str] = None


@dataclass
class EventCreateWizardState:
    step: str
    title: str | None = None
    event_date: date | None = None
    event_time: time | None = None
    event_id: str | None = None


router = Router()
auth_state = ApiAuthState()
create_event_states: dict[int, EventCreateWizardState] = {}


def _is_chat_allowed_chat_id(chat_id: int | None) -> bool:
    if not ALLOWED_CHAT_IDS or chat_id is None:
        return False
    return chat_id in ALLOWED_CHAT_IDS


def _is_chat_allowed(message: Message) -> bool:
    chat_id = message.chat.id if message.chat else None
    return _is_chat_allowed_chat_id(chat_id)


async def _api_login(session: aiohttp.ClientSession) -> str:
    url = f"{API_BASE_URL}/auth/login"
    payload = {"login": API_LOGIN, "password": API_PASSWORD}
    async with session.post(url, json=payload) as resp:
        data = await resp.json(content_type=None)
        if resp.status != 200:
            detail = data.get("detail", data) if isinstance(data, dict) else data
            raise RuntimeError(f"Login failed ({resp.status}): {detail}")
        token = data.get("access_token")
        if not token:
            raise RuntimeError("Login response has no access_token")
        return token


async def _ensure_token(session: aiohttp.ClientSession) -> str:
    if auth_state.token:
        return auth_state.token
    auth_state.token = await _api_login(session)
    return auth_state.token


async def _request_json_with_auth(
    session: aiohttp.ClientSession,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    token = await _ensure_token(session)
    url = f"{API_BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"}

    request_fn = session.get if method == "GET" else session.post
    async with request_fn(url, headers=headers, json=payload) as resp:
        data = await resp.json(content_type=None)
        if resp.status == 401:
            auth_state.token = await _api_login(session)
            headers = {"Authorization": f"Bearer {auth_state.token}"}
            async with request_fn(url, headers=headers, json=payload) as retry_resp:
                retry_data = await retry_resp.json(content_type=None)
                if retry_resp.status >= 400:
                    raise RuntimeError(f"{method} {path} failed ({retry_resp.status}): {retry_data}")
                return retry_data
        if resp.status >= 400:
            raise RuntimeError(f"{method} {path} failed ({resp.status}): {data}")
        return data


async def _post_push_test(session: aiohttp.ClientSession, title: str, body: str) -> dict[str, Any]:
    payload = {"title": title[:120], "body": body[:500]}
    data = await _request_json_with_auth(session, "POST", "/push/test", payload=payload)
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected /push/test response format.")
    return data


async def _get_json_with_auth(session: aiohttp.ClientSession, path: str) -> dict[str, Any]:
    data = await _request_json_with_auth(session, "GET", path, payload=None)
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response format for {path}")
    return data


async def _post_json_with_auth(
    session: aiohttp.ClientSession,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    data = await _request_json_with_auth(session, "POST", path, payload=payload)
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response format for {path}")
    return data


async def _list_events_for_recon(session: aiohttp.ClientSession, limit: int = 40) -> list[dict[str, Any]]:
    data = await _request_json_with_auth(
        session,
        "GET",
        f"/events/admin?status=all&limit={max(1, min(limit, 200))}",
        payload=None,
    )
    if not isinstance(data, list):
        raise RuntimeError("Unexpected /events/admin response format.")
    items: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict) and item.get("id"):
            items.append(item)
    return items


def _status_text(push_result: dict[str, Any]) -> str:
    ok = push_result.get("ok")
    enabled = push_result.get("enabled")
    topic = push_result.get("topic")
    tokens_total = push_result.get("tokens_total")
    tokens_delivered = push_result.get("tokens_delivered")
    tokens_pruned = push_result.get("tokens_pruned")
    topic_sent = push_result.get("topic_sent")
    errors = push_result.get("errors", [])
    error_text = "\n".join(f"- {err}" for err in errors) if errors else "-"
    return (
        f"Push response:\n"
        f"ok: {ok}\n"
        f"enabled: {enabled}\n"
        f"topic: {topic}\n"
        f"tokens_total: {tokens_total}\n"
        f"tokens_delivered: {tokens_delivered}\n"
        f"tokens_pruned: {tokens_pruned}\n"
        f"topic_sent: {topic_sent}\n"
        f"errors:\n{error_text}"
    )


def _trim(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)] + "…"


def _event_button_text(event: dict[str, Any]) -> str:
    title = (event.get("title") or "Untitled event").strip()
    status = (event.get("status") or "unknown").strip()
    dt_raw = (event.get("datetime_start") or "").strip()
    if dt_raw:
        dt_raw = dt_raw.replace("T", " ")[:16]
        text = f"{title} | {dt_raw} | {status}"
    else:
        text = f"{title} | {status}"
    return _trim(text, 56)


def _build_events_keyboard(events: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for event in events:
        event_id = str(event.get("id", "")).strip()
        if not event_id:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=_event_button_text(event),
                    callback_data=f"recon:event:{event_id}",
                )
            ]
        )
    if not rows:
        rows = [[InlineKeyboardButton(text="No events found", callback_data="recon:none")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_recon_actions_keyboard(event_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Уведомить о новом мероприятии",
                    callback_data=f"recon:send:new:{event_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Уведомить о переносе",
                    callback_data=f"recon:send:rescheduled:{event_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Уведомить об отмене",
                    callback_data=f"recon:send:canceled:{event_id}",
                )
            ],
            [InlineKeyboardButton(text="Назад к списку", callback_data="recon:list")],
        ]
    )


def _get_chat_id(message: Message | None) -> int | None:
    if not message or not message.chat:
        return None
    return message.chat.id


def _get_create_event_state(chat_id: int | None) -> EventCreateWizardState | None:
    if chat_id is None:
        return None
    return create_event_states.get(chat_id)


def _set_create_event_state(chat_id: int, state: EventCreateWizardState) -> None:
    create_event_states[chat_id] = state


def _clear_create_event_state(chat_id: int | None) -> None:
    if chat_id is None:
        return
    create_event_states.pop(chat_id, None)


def _parse_user_date(raw: str) -> date | None:
    value = raw.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_user_time(raw: str) -> time | None:
    value = raw.strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time().replace(microsecond=0)
        except ValueError:
            continue
    return None


def _to_api_datetime_iso(event_date: date, event_time: time) -> str:
    return datetime.combine(event_date, event_time).replace(microsecond=0).isoformat()


async def _create_event_draft(
    session: aiohttp.ClientSession,
    *,
    title: str,
    event_date: date,
    event_time: time,
) -> dict[str, Any]:
    payload = {
        "title": title,
        "datetime_start": _to_api_datetime_iso(event_date, event_time),
    }
    return await _post_json_with_auth(session, "/events", payload=payload)


async def _upload_event_banner(
    session: aiohttp.ClientSession,
    *,
    event_id: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> dict[str, Any]:
    async def send_with_token(token: str) -> tuple[int, Any]:
        url = f"{API_BASE_URL}/events/{event_id}/banner"
        headers = {"Authorization": f"Bearer {token}"}
        form = aiohttp.FormData()
        form.add_field(
            "banner",
            content,
            filename=filename,
            content_type=content_type,
        )
        async with session.post(url, headers=headers, data=form) as resp:
            return resp.status, await resp.json(content_type=None)

    token = await _ensure_token(session)
    status, data = await send_with_token(token)
    if status == 401:
        auth_state.token = await _api_login(session)
        status, data = await send_with_token(auth_state.token)

    if status >= 400:
        raise RuntimeError(f"POST /events/{event_id}/banner failed ({status}): {data}")
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response format for /events/{event_id}/banner")
    return data


async def _download_banner_from_message(message: Message) -> tuple[str, bytes, str] | None:
    bot = message.bot
    if bot is None:
        return None

    file_id: str | None = None
    filename = "banner.jpg"
    content_type = "image/jpeg"

    if message.photo:
        largest = message.photo[-1]
        file_id = largest.file_id
    elif message.document:
        document = message.document
        if not (document.mime_type or "").startswith("image/"):
            return None
        file_id = document.file_id
        filename = document.file_name or "banner"
        content_type = document.mime_type or "application/octet-stream"
    else:
        return None

    telegram_file = await bot.get_file(file_id)
    if not telegram_file.file_path:
        return None

    buffer = io.BytesIO()
    await bot.download_file(telegram_file.file_path, destination=buffer)
    return filename, buffer.getvalue(), content_type


def _format_event_date_for_user(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _format_event_time_for_user(value: time) -> str:
    return value.strftime("%H:%M")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not _is_chat_allowed(message):
        await message.answer("Access denied.")
        return
    await message.answer(
        "EduFlow Push Bot ready.\n\n"
        "Commands:\n"
        "/status - backend and push diagnostics\n"
        "/send <text> - send push with default title\n"
        "/notify <title> | <text> - send custom push\n"
        "/recon - send event-like test push (choose event + type)\n\n"
        "/create_event - create draft event (title/date/time/banner)\n"
        "/cancel - cancel current event creation flow\n\n"
        "You can also send plain text (same as /send)."
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not _is_chat_allowed(message):
        await message.answer("Access denied.")
        return

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            info = await _get_json_with_auth(session, "/system/info")
            push_status = await _get_json_with_auth(session, "/push/status")
        except Exception as ex:  # pragma: no cover
            await message.answer(f"API request failed:\n{ex}")
            return

    await message.answer(
        "Backend status:\n"
        f"version: {info.get('app_version')}\n"
        f"push_credentials_exists: {info.get('push_credentials_exists')}\n"
        f"registered_devices: {info.get('registered_devices')}\n"
        f"topic: {info.get('push_topic')}\n"
        "\nPush endpoint status:\n"
        f"credentials_exists: {push_status.get('credentials_exists')}\n"
        f"registered_devices: {push_status.get('registered_devices')}\n"
        f"topic: {push_status.get('topic')}"
    )


@router.message(Command("recon"))
async def cmd_recon(message: Message) -> None:
    if not _is_chat_allowed(message):
        await message.answer("Access denied.")
        return

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            events = await _list_events_for_recon(session, limit=40)
        except Exception as ex:  # pragma: no cover
            await message.answer(f"Failed to fetch events list:\n{ex}")
            return

    if not events:
        await message.answer("No events found.")
        return

    await message.answer(
        "Выберите мероприятие для тестового уведомления:",
        reply_markup=_build_events_keyboard(events),
    )


@router.message(Command("create_event"))
@router.message(Command("createevent"))
async def cmd_create_event(message: Message) -> None:
    if not _is_chat_allowed(message):
        await message.answer("Access denied.")
        return

    chat_id = _get_chat_id(message)
    if chat_id is None:
        await message.answer("Unable to resolve chat.")
        return

    _set_create_event_state(chat_id, EventCreateWizardState(step="title"))
    await message.answer(
        "Create event flow started.\n"
        "Step 1/4: send event title.\n"
        "Use /cancel to abort."
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    if not _is_chat_allowed(message):
        await message.answer("Access denied.")
        return

    chat_id = _get_chat_id(message)
    state = _get_create_event_state(chat_id)
    if not state:
        await message.answer("No active event creation flow.")
        return

    _clear_create_event_state(chat_id)
    await message.answer("Event creation flow canceled.")


async def _handle_create_event_text_step(message: Message, state: EventCreateWizardState) -> bool:
    chat_id = _get_chat_id(message)
    if chat_id is None:
        await message.answer("Unable to resolve chat.")
        return True

    text = (message.text or "").strip()
    if state.step == "title":
        if not text:
            await message.answer("Title is empty. Send a non-empty title.")
            return True
        if len(text) > 255:
            await message.answer("Title is too long (max 255 chars). Send a shorter title.")
            return True

        state.title = text
        state.step = "date"
        _set_create_event_state(chat_id, state)
        await message.answer(
            "Step 2/4: send date in format DD.MM.YYYY.\n"
            "Example: 26.02.2026"
        )
        return True

    if state.step == "date":
        parsed_date = _parse_user_date(text)
        if parsed_date is None:
            await message.answer("Invalid date format. Use DD.MM.YYYY.")
            return True

        state.event_date = parsed_date
        state.step = "time"
        _set_create_event_state(chat_id, state)
        await message.answer(
            "Step 3/4: send time in format HH:MM.\n"
            "Example: 18:30"
        )
        return True

    if state.step == "time":
        parsed_time = _parse_user_time(text)
        if parsed_time is None:
            await message.answer("Invalid time format. Use HH:MM.")
            return True
        if not state.title or not state.event_date:
            _clear_create_event_state(chat_id)
            await message.answer("Flow state is invalid. Start again with /create_event.")
            return True

        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                created = await _create_event_draft(
                    session,
                    title=state.title,
                    event_date=state.event_date,
                    event_time=parsed_time,
                )
            except Exception as ex:  # pragma: no cover
                await message.answer(f"Failed to create event draft:\n{ex}")
                return True

        event_id = str(created.get("id") or "").strip()
        if not event_id:
            await message.answer("Event was created but response has no id. Try again.")
            _clear_create_event_state(chat_id)
            return True

        state.event_time = parsed_time
        state.event_id = event_id
        state.step = "banner"
        _set_create_event_state(chat_id, state)
        await message.answer(
            "Step 4/4: send banner image.\n"
            "You can send a photo or an image document."
        )
        return True

    if state.step == "banner":
        await message.answer("Please send a banner image (photo or image document).")
        return True

    _clear_create_event_state(chat_id)
    await message.answer("Unknown flow state. Start again with /create_event.")
    return True


@router.callback_query(F.data == "recon:none")
async def cb_recon_none(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "recon:list")
async def cb_recon_list(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id if callback.message and callback.message.chat else None
    if not _is_chat_allowed_chat_id(chat_id):
        await callback.answer("Access denied.", show_alert=True)
        return

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            events = await _list_events_for_recon(session, limit=40)
        except Exception as ex:  # pragma: no cover
            await callback.answer("Failed to load events.", show_alert=True)
            if callback.message:
                await callback.message.answer(f"Failed to fetch events list:\n{ex}")
            return

    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "Выберите мероприятие для тестового уведомления:",
            reply_markup=_build_events_keyboard(events),
        )


@router.callback_query(F.data.startswith("recon:event:"))
async def cb_recon_event(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id if callback.message and callback.message.chat else None
    if not _is_chat_allowed_chat_id(chat_id):
        await callback.answer("Access denied.", show_alert=True)
        return

    data = callback.data or ""
    _, _, event_id = data.split(":", 2)
    event_title = "Selected event"

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            events = await _list_events_for_recon(session, limit=80)
            selected = next((item for item in events if item.get("id") == event_id), None)
            if selected:
                event_title = str(selected.get("title") or "Untitled event")
        except Exception:
            pass

    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"Мероприятие: {event_title}\nВыберите тип уведомления:",
            reply_markup=_build_recon_actions_keyboard(event_id),
        )


@router.callback_query(F.data.startswith("recon:send:"))
async def cb_recon_send(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id if callback.message and callback.message.chat else None
    if not _is_chat_allowed_chat_id(chat_id):
        await callback.answer("Access denied.", show_alert=True)
        return

    data = callback.data or ""
    parts = data.split(":", 3)
    if len(parts) != 4:
        await callback.answer("Invalid action.", show_alert=True)
        return
    _, _, notification_type, event_id = parts
    if notification_type not in RECON_NOTIFICATION_TYPES:
        await callback.answer("Unsupported notification type.", show_alert=True)
        return

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            result = await _post_json_with_auth(
                session,
                f"/push/recon/event/{event_id}",
                payload={"notification_type": notification_type},
            )
        except Exception as ex:  # pragma: no cover
            await callback.answer("Push failed.", show_alert=True)
            if callback.message:
                await callback.message.answer(f"Recon push failed:\n{ex}")
            return

    await callback.answer("Push sent.")
    if callback.message:
        await callback.message.answer(
            "Recon push request sent:\n"
            f"event_id: {result.get('event_id')}\n"
            f"event_title: {result.get('event_title')}\n"
            f"type: {result.get('notification_type')}"
        )


async def _send_push_from_text(message: Message, title: str, body: str) -> None:
    if not _is_chat_allowed(message):
        await message.answer("Access denied.")
        return
    if not body.strip():
        await message.answer("Notification text is empty.")
        return

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            result = await _post_push_test(session, title=title, body=body)
        except Exception as ex:  # pragma: no cover
            await message.answer(f"Push send failed:\n{ex}")
            return

    await message.answer(_status_text(result))


@router.message(Command("send"))
async def cmd_send(message: Message) -> None:
    raw = (message.text or "").strip()
    text = raw[len("/send") :].strip() if raw.lower().startswith("/send") else ""
    await _send_push_from_text(message, DEFAULT_TITLE, text)


@router.message(Command("notify"))
async def cmd_notify(message: Message) -> None:
    raw = (message.text or "").strip()
    payload = raw[len("/notify") :].strip() if raw.lower().startswith("/notify") else ""
    if "|" not in payload:
        await message.answer("Format: /notify <title> | <text>")
        return
    title, body = payload.split("|", 1)
    await _send_push_from_text(message, title.strip() or DEFAULT_TITLE, body.strip())


@router.message(F.photo | F.document)
async def on_banner_upload(message: Message) -> None:
    chat_id = _get_chat_id(message)
    state = _get_create_event_state(chat_id)
    if not state or state.step != "banner":
        return

    if not _is_chat_allowed(message):
        await message.answer("Access denied.")
        return

    if not state.event_id:
        _clear_create_event_state(chat_id)
        await message.answer("Flow state is invalid. Start again with /create_event.")
        return

    banner = await _download_banner_from_message(message)
    if banner is None:
        await message.answer("Please send a photo or an image document.")
        return
    filename, content, content_type = banner

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            upload_result = await _upload_event_banner(
                session,
                event_id=state.event_id,
                filename=filename,
                content=content,
                content_type=content_type,
            )
        except Exception as ex:  # pragma: no cover
            await message.answer(f"Failed to upload banner:\n{ex}")
            return

    event_date = _format_event_date_for_user(state.event_date) if state.event_date else "-"
    event_time = _format_event_time_for_user(state.event_time) if state.event_time else "-"
    title = state.title or "-"
    banner_url = upload_result.get("banner_image_url")
    _clear_create_event_state(chat_id)
    await message.answer(
        "Event draft created successfully.\n"
        f"id: {state.event_id}\n"
        f"title: {title}\n"
        f"date: {event_date}\n"
        f"time: {event_time}\n"
        f"banner: {banner_url}"
    )


@router.message()
async def on_plain_text(message: Message) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    state = _get_create_event_state(_get_chat_id(message))
    if state:
        if text.startswith("/"):
            await message.answer("Event creation is active. Continue steps or use /cancel.")
            return
        await _handle_create_event_text_step(message, state)
        return
    if text.startswith("/"):
        await message.answer("Unknown command. Use /start")
        return
    await _send_push_from_text(message, DEFAULT_TITLE, text)


def _validate_required_env() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TG_BOT_TOKEN is required.")
    if not ALLOWED_CHAT_IDS:
        raise RuntimeError("Set TG_ADMIN_CHAT_ID (or TG_BOT_ALLOWED_CHAT_IDS).")
    if not API_LOGIN or not API_PASSWORD:
        raise RuntimeError("TG_BOT_API_LOGIN and TG_BOT_API_PASSWORD are required.")


async def main() -> None:
    _validate_required_env()
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
