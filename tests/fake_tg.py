"""Soxta Telegram Bot API: haqiqiy Dispatcher, Postgres va Redis bilan to'liq oqimni sinash uchun.
Barcha chaqiruvlar `calls` ga yoziladi; `latency` — tarmoq kechikishini simulyatsiya qiladi."""
from __future__ import annotations

import asyncio
import itertools
import time
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import (
    AnswerCallbackQuery,
    CopyMessage,
    CreateChatInviteLink,
    EditMessageCaption,
    EditMessageMedia,
    EditMessageText,
    GetMe,
    SendDocument,
    SendMessage,
    SendPhoto,
    TelegramMethod,
)
from aiogram.types import Chat, ChatInviteLink, Message, MessageId, Update, User

SENDS = (SendMessage, SendPhoto, SendDocument, CopyMessage)


class FakeTelegram(BaseSession):
    def __init__(self, latency: float = 0.0) -> None:
        super().__init__()
        self.latency = latency
        self.calls: list[TelegramMethod[Any]] = []
        self.blocked: set[int] = set()
        self._ids = itertools.count(10_000)

    async def close(self) -> None:  # noqa: D401
        return None

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        if self.latency:
            await asyncio.sleep(self.latency)
        self.calls.append(method)
        chat_id = getattr(method, "chat_id", None)
        if isinstance(method, SENDS) and chat_id in self.blocked:
            raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
        if isinstance(method, (SendMessage, SendPhoto, SendDocument, EditMessageText, EditMessageMedia, EditMessageCaption)):
            mid = getattr(method, "message_id", None) or next(self._ids)
            return Message(
                message_id=mid,
                date=datetime.now(),
                chat=Chat(id=int(chat_id), type="private"),
                text=getattr(method, "text", None),
            ).as_(bot)
        if isinstance(method, CopyMessage):
            return MessageId(message_id=next(self._ids))
        if isinstance(method, CreateChatInviteLink):
            return ChatInviteLink(
                invite_link=f"https://t.me/+fake{next(self._ids)}",
                creator=User(id=1, is_bot=True, first_name="Bot"),
                creates_join_request=False,
                is_primary=False,
                is_revoked=False,
                member_limit=method.member_limit,
            )
        if isinstance(method, GetMe):
            return User(id=1, is_bot=True, first_name="Bot", username="test_bot")
        return True

    # --- yordamchilar ---
    def of(self, kind: type, chat_id: int | None = None) -> list[Any]:
        return [c for c in self.calls if isinstance(c, kind) and (chat_id is None or getattr(c, "chat_id", None) == chat_id)]

    def texts(self, chat_id: int) -> list[str]:
        out = []
        for c in self.calls:
            if getattr(c, "chat_id", None) == chat_id:
                t = getattr(c, "text", None) or getattr(c, "caption", None)
                if t:
                    out.append(t)
        return out

    def alerts(self) -> list[str]:
        return [c.text or "" for c in self.of(AnswerCallbackQuery)]

    def reset(self) -> None:
        self.calls.clear()


class Sim:
    """Telegram update'larini yasab, dispatcher'ga beradi."""

    def __init__(self, bot: Bot, dp: Dispatcher) -> None:
        self.bot, self.dp = bot, dp
        self._upd = itertools.count(1)
        self._mid = itertools.count(1)

    @staticmethod
    def _user(uid: int, name: str) -> dict[str, Any]:
        return {"id": uid, "is_bot": False, "first_name": name, "username": f"user{uid}"}

    async def _feed(self, payload: dict[str, Any]) -> None:
        upd = Update.model_validate({"update_id": next(self._upd), **payload}, context={"bot": self.bot})
        await self.dp.feed_update(self.bot, upd)

    async def send(
        self,
        uid: int,
        text: str | None = None,
        *,
        photo: str | None = None,
        document: tuple[str, str, int] | None = None,  # (file_id, mime, size)
        name: str = "Test",
    ) -> None:
        msg: dict[str, Any] = {
            "message_id": next(self._mid),
            "date": int(time.time()),
            "chat": {"id": uid, "type": "private"},
            "from": self._user(uid, name),
        }
        if text is not None:
            msg["text"] = text
            if text.startswith("/"):
                msg["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        if photo:
            msg["photo"] = [{"file_id": photo, "file_unique_id": f"u_{photo}", "width": 800, "height": 1200}]
        if document:
            fid, mime, size = document
            msg["document"] = {"file_id": fid, "file_unique_id": f"u_{fid}", "mime_type": mime, "file_size": size}
        await self._feed({"message": msg})

    async def click(self, uid: int, data: str, message_id: int = 1, name: str = "Test") -> None:
        await self._feed({
            "callback_query": {
                "id": str(next(self._upd)),
                "from": self._user(uid, name),
                "chat_instance": "ci",
                "data": data,
                "message": {
                    "message_id": message_id,
                    "date": int(time.time()),
                    "chat": {"id": uid, "type": "private"},
                    "text": "screen",
                },
            }
        })
