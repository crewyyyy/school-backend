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
import os
from dataclasses import dataclass
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message


HTTP_TIMEOUT_SECONDS = 15
API_BASE_URL = os.getenv("TG_BOT_API_BASE_URL", "http://backend:8000").rstrip("/")
DEFAULT_TITLE = os.getenv("TG_BOT_DEFAULT_TITLE", "EduFlow notification")
BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
API_LOGIN = os.getenv("TG_BOT_API_LOGIN", "admin").strip()
API_PASSWORD = os.getenv("TG_BOT_API_PASSWORD", "admin123").strip()


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


router = Router()
auth_state = ApiAuthState()


def _is_chat_allowed(message: Message) -> bool:
    if not ALLOWED_CHAT_IDS:
        return False
    chat_id = message.chat.id if message.chat else None
    return chat_id in ALLOWED_CHAT_IDS


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


async def _post_push_test(session: aiohttp.ClientSession, title: str, body: str) -> dict:
    token = await _ensure_token(session)
    url = f"{API_BASE_URL}/push/test"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"title": title[:120], "body": body[:500]}

    async with session.post(url, headers=headers, json=payload) as resp:
        data = await resp.json(content_type=None)
        if resp.status == 401:
            auth_state.token = await _api_login(session)
            headers = {"Authorization": f"Bearer {auth_state.token}"}
            async with session.post(url, headers=headers, json=payload) as retry_resp:
                retry_data = await retry_resp.json(content_type=None)
                if retry_resp.status != 200:
                    raise RuntimeError(f"Push test failed ({retry_resp.status}): {retry_data}")
                return retry_data

        if resp.status != 200:
            raise RuntimeError(f"Push test failed ({resp.status}): {data}")
        return data


async def _get_json_with_auth(session: aiohttp.ClientSession, path: str) -> dict:
    token = await _ensure_token(session)
    url = f"{API_BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    async with session.get(url, headers=headers) as resp:
        data = await resp.json(content_type=None)
        if resp.status == 401:
            auth_state.token = await _api_login(session)
            headers = {"Authorization": f"Bearer {auth_state.token}"}
            async with session.get(url, headers=headers) as retry_resp:
                retry_data = await retry_resp.json(content_type=None)
                if retry_resp.status != 200:
                    raise RuntimeError(f"GET {path} failed ({retry_resp.status}): {retry_data}")
                return retry_data

        if resp.status != 200:
            raise RuntimeError(f"GET {path} failed ({resp.status}): {data}")
        return data


def _status_text(push_result: dict) -> str:
    ok = push_result.get("ok")
    enabled = push_result.get("enabled")
    topic = push_result.get("topic")
    tokens_total = push_result.get("tokens_total")
    tokens_delivered = push_result.get("tokens_delivered")
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
        f"topic_sent: {topic_sent}\n"
        f"errors:\n{error_text}"
    )


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
        "/notify <title> | <text> - send custom push\n\n"
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
    text = raw[len("/send"):].strip() if raw.lower().startswith("/send") else ""
    await _send_push_from_text(message, DEFAULT_TITLE, text)


@router.message(Command("notify"))
async def cmd_notify(message: Message) -> None:
    raw = (message.text or "").strip()
    payload = raw[len("/notify"):].strip() if raw.lower().startswith("/notify") else ""
    if "|" not in payload:
        await message.answer("Format: /notify <title> | <text>")
        return
    title, body = payload.split("|", 1)
    await _send_push_from_text(message, title.strip() or DEFAULT_TITLE, body.strip())


@router.message()
async def on_plain_text(message: Message) -> None:
    text = (message.text or "").strip()
    if not text:
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
