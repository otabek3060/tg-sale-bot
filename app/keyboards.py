from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.callbacks import AdmCb, PayCb, UserCb
from app.texts import uz


def _btn(text: str, cb: object) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())  # type: ignore[attr-defined]


# --- foydalanuvchi ----------------------------------------------------------------

def home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn(uz.BTN_BUY, UserCb(action="buy"))]])


def purchased() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn(uz.BTN_GET_LINK, UserCb(action="link"))]])


def payment_details() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn(uz.BTN_BACK, UserCb(action="back"))]])


def retry() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn(uz.BTN_RETRY, UserCb(action="retry"))]])


# --- to'lovni ko'rib chiqish ------------------------------------------------------

def review(pid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            _btn(uz.BTN_APPROVE, PayCb(action="ok", pid=pid)),
            _btn(uz.BTN_REJECT, PayCb(action="no", pid=pid)),
        ]]
    )


def reject_reasons(pid: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for code, title in uz.REJECT_REASONS.items():
        b.add(_btn(title, PayCb(action="r", pid=pid, code=code)))
    b.add(_btn("✍️ Boshqa sabab", PayCb(action="custom", pid=pid)))
    b.add(_btn("⬅️ Bekor qilish", PayCb(action="back", pid=pid)))
    b.adjust(2, 2, 1, 1)
    return b.as_markup()


def ban_offer(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("🚫 Userni bloklash", AdmCb(s="user", a="ban", v=str(user_id)))]]
    )


# --- admin panel ------------------------------------------------------------------

def admin_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=uz.BTN_SETTINGS), KeyboardButton(text=uz.BTN_USERS), KeyboardButton(text=uz.BTN_SALES)],
            [KeyboardButton(text=uz.BTN_BROADCAST), KeyboardButton(text=uz.BTN_EXIT)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def rows(*buttons: list[tuple[str, AdmCb]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn(t, cb) for t, cb in row] for row in buttons])


def back(section: str = "home", action: str = "", value: str = "", text: str = "⬅️ Orqaga") -> InlineKeyboardMarkup:
    return rows([(text, AdmCb(s=section, a=action, v=value))])


def cancel(section: str, action: str = "", value: str = "") -> InlineKeyboardMarkup:
    return back(section, action, value, text="❌ Bekor qilish")
