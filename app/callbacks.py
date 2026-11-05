"""Callback data fabrikalari (Telegram limiti: 64 bayt)."""
from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class UserCb(CallbackData, prefix="u"):
    action: str  # buy | back | retry | link


class PayCb(CallbackData, prefix="p"):
    action: str  # ok | no | back | r (sabab) | custom
    pid: int
    code: str = ""


class AdmCb(CallbackData, prefix="a"):
    s: str        # bo'lim: home | set | adm | users | user | sales | bc
    a: str = ""   # amal
    v: str = ""   # qiymat
