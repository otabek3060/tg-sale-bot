"""Soxta Telegram Bot API HTTP serveri — botni haqiqiy jarayon sifatida (python -m app) sinash uchun.
    python -m loadtest.fake_api_server 8081     →  TELEGRAM_API_URL=http://localhost:8081
Kelgan chaqiruvlar: GET /_calls"""
from __future__ import annotations

import asyncio
import itertools
import sys
import time

from aiohttp import web

calls: list[dict] = []
ids = itertools.count(1000)


def _msg(chat_id: object, **extra: object) -> dict:
    return {"message_id": next(ids), "date": int(time.time()), "chat": {"id": int(chat_id), "type": "private"}, **extra}


async def api(request: web.Request) -> web.Response:
    method = request.match_info["method"]
    data = dict(await request.post()) if request.can_read_body else {}
    calls.append({"method": method, **{k: str(v)[:300] for k, v in data.items()}})
    lower = method.lower()
    if lower == "getme":
        result: object = {"id": 1, "is_bot": True, "first_name": "Bot", "username": "test_bot"}
    elif lower == "getupdates":
        await asyncio.sleep(1)
        result = []
    elif lower in {"sendmessage", "sendphoto", "senddocument", "editmessagetext", "editmessagecaption"}:
        result = _msg(data.get("chat_id", 0), text=data.get("text", ""))
    else:
        result = True
    return web.json_response({"ok": True, "result": result})


async def dump(_: web.Request) -> web.Response:
    return web.json_response(calls)


if __name__ == "__main__":
    app = web.Application()
    app.router.add_post("/bot{token}/{method}", api)
    app.router.add_get("/_calls", dump)
    web.run_app(app, port=int(sys.argv[1]) if len(sys.argv) > 1 else 8081, print=None)
