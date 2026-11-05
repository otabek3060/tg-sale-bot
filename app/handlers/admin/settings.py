"""⚙️ Sozlamalar va 👮 adminlarni boshqarish."""
from __future__ import annotations

from collections.abc import Callable
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, MessageOriginUser
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards as kb
from app.callbacks import AdmCb
from app.db.repositories import misc
from app.db.repositories import users as users_repo
from app.handlers.admin.common import IsAdmin
from app.services.access import Access
from app.services.shop_settings import ShopSettings
from app.services.ui import UI
from app.states import AdminStates
from app.texts import uz
from app.utils import validators as v

router = Router(name="admin.settings")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

FIELDS: dict[str, tuple[str, Callable[[str], str] | None]] = {
    "card_number": ("💳 Karta raqami", v.card_number),
    "card_holder": ("👤 Karta egasi", v.card_holder),
    "price": ("💰 Narx (so'm)", v.price),
    "product_text": ("📝 Mahsulot matni", None),
    "product_photo": ("🖼 Mahsulot rasmi", None),
    "channel_id": ("📣 Kanal ID", v.channel_id),
    "static_link": ("🔗 Doimiy havola", v.url),
}


def _e(key: str) -> AdmCb:
    return AdmCb(s="set", a="edit", v=key)


async def show(chat_id: int, ui: UI, shop: ShopSettings, access: Access, *, new: bool = False, note: str = "") -> None:
    s = await shop.get()
    text = (
        "⚙️ <b>Sozlamalar</b>\n\n"
        f"💳 Karta: <code>{s.card_number}</code>\n"
        f"👤 Egasi: {escape(s.card_holder)}\n"
        f"💰 Narx: {uz.money(s.price)}\n"
        f"🖼 Rasm: {'bor' if s.product_photo else 'yo‘q'}\n"
        f"🔗 Havola turi: {'Bir martalik (yopiq kanal)' if s.link_mode == 'invite' else 'Doimiy havola'}\n"
        f"📣 Kanal: {escape(s.channel_id) or '—'}\n"
        f"🔗 Doimiy havola: {escape(s.static_link) or '—'}\n"
        f"🔌 Sotuv: {'✅ Yoqilgan' if s.sales_enabled else '⛔️ O‘chirilgan'}"
    )
    if note:
        text += f"\n\n{note}"
    mode_title = "🔁 Havola turi: " + ("bir martalik" if s.link_mode == "invite" else "doimiy")
    markup = kb.rows(
        [("💳 Karta", _e("card_number")), ("👤 Egasi", _e("card_holder"))],
        [("💰 Narx", _e("price")), ("📝 Matn", _e("product_text"))],
        [("🖼 Rasm", _e("product_photo")), ("📣 Kanal ID", _e("channel_id"))],
        [("🔗 Doimiy havola", _e("static_link"))],
        [(mode_title, AdmCb(s="set", a="toggle", v="link_mode"))],
        [("⛔️ Sotuvni o‘chirish" if s.sales_enabled else "✅ Sotuvni yoqish", AdmCb(s="set", a="toggle", v="sales_enabled"))],
        [("👮 Adminlar", AdmCb(s="adm"))],
        [("⬅️ Orqaga", AdmCb(s="home"))],
    )
    await ui.render(chat_id, text, markup, new=new)


@router.callback_query(AdmCb.filter((F.s == "set") & (F.a == "")))
async def on_settings(cb: CallbackQuery, state: FSMContext, ui: UI, shop: ShopSettings, access: Access) -> None:
    await state.clear()
    await show(cb.from_user.id, ui, shop, access)
    await cb.answer()


async def _prompt(chat_id: int, key: str, ui: UI, shop: ShopSettings, error: str = "") -> None:
    s = await shop.get()
    title = FIELDS[key][0]
    current = getattr(s, key)
    hints = {
        "card_number": "16 ta raqam yuboring.",
        "product_text": "Yangi matnni yuboring. Qalin/kursiv formatlash saqlanadi.",
        "product_photo": "Yangi rasmni yuboring.",
        "channel_id": "Kanal ID (-100...) yoki @username yuboring. Bot kanalda admin bo‘lishi va "
                      "«Foydalanuvchilarni taklif qilish» huquqiga ega bo‘lishi kerak.",
        "static_link": "Havolani yuboring (https://...).",
    }
    shown = "rasm o‘rnatilgan" if key == "product_photo" and current else (escape(str(current)) or "—")
    text = f"{title}\n\nJoriy qiymat: {shown}\n\n{hints.get(key, 'Yangi qiymatni yuboring.')}"
    if error:
        text += f"\n\n❗️ {escape(error)}"
    buttons = []
    if key == "product_photo" and current:
        buttons.append([("🗑 Rasmni o‘chirish", AdmCb(s="set", a="clearphoto"))])
    buttons.append([("❌ Bekor qilish", AdmCb(s="set"))])
    await ui.render(chat_id, text, kb.rows(*buttons))


@router.callback_query(AdmCb.filter((F.s == "set") & (F.a == "edit")))
async def on_edit(cb: CallbackQuery, callback_data: AdmCb, state: FSMContext, ui: UI, shop: ShopSettings) -> None:
    if callback_data.v not in FIELDS:
        await cb.answer()
        return
    await state.set_state(AdminStates.setting_value)
    await state.update_data(key=callback_data.v)
    await _prompt(cb.from_user.id, callback_data.v, ui, shop)
    await cb.answer()


async def _check_channel(bot: Bot, channel: str) -> None:
    chat: int | str = channel if channel.startswith("@") else int(channel)
    try:
        member = await bot.get_chat_member(chat, bot.id)
    except Exception as e:  # noqa: BLE001
        raise v.ValidationError(f"Kanal topilmadi yoki bot unga qo‘shilmagan ({e}).") from e
    if member.status != "administrator" or not getattr(member, "can_invite_users", False):
        raise v.ValidationError("Bot kanalda admin emas yoki «Taklif qilish» huquqi yo‘q.")


@router.message(AdminStates.setting_value)
async def on_value(message: Message, state: FSMContext, ui: UI, shop: ShopSettings, bot: Bot) -> None:
    key = (await state.get_data()).get("key", "")
    await ui.drop(message)
    s = await shop.get()
    try:
        if key == "product_photo":
            if not message.photo:
                raise v.ValidationError("Rasm yuboring.")
            if len(s.product_text) > 900:
                raise v.ValidationError("Rasm bilan matn 900 belgidan oshmasligi kerak — avval matnni qisqartiring.")
            value = message.photo[-1].file_id
        elif key == "product_text":
            value = v.product_text(message.html_text if message.text else "", with_photo=bool(s.product_photo))
        elif key in FIELDS and FIELDS[key][1]:
            value = FIELDS[key][1](message.text or "")  # type: ignore[misc]
            if key == "channel_id":
                await _check_channel(bot, value)
        else:
            await state.clear()
            return
    except v.ValidationError as e:
        await _prompt(message.chat.id, key, ui, shop, error=str(e))
        return

    await state.set_state(AdminStates.setting_confirm)
    await state.update_data(value=value)
    confirm = kb.rows([("✅ Saqlash", AdmCb(s="set", a="save")), ("❌ Bekor qilish", AdmCb(s="set"))])
    title = FIELDS[key][0]
    if key == "product_photo":
        await ui.render(message.chat.id, f"{title} — yangi rasm. Saqlaymizmi?", confirm, photo=value)
    else:
        preview = value if key == "product_text" else f"<code>{escape(value)}</code>"
        await ui.render(message.chat.id, f"{title}\n\nYangi qiymat:\n{preview}\n\nSaqlaymizmi?", confirm)


@router.callback_query(AdmCb.filter((F.s == "set") & (F.a == "save")), AdminStates.setting_confirm)
async def on_save(cb: CallbackQuery, state: FSMContext, ui: UI, shop: ShopSettings, access: Access) -> None:
    data = await state.get_data()
    await state.clear()
    await shop.set(data["key"], data["value"], cb.from_user.id)
    await show(cb.from_user.id, ui, shop, access, note="✅ Saqlandi")
    await cb.answer("✅ Saqlandi")


@router.callback_query(AdmCb.filter((F.s == "set") & (F.a == "save")))
async def on_save_stale(cb: CallbackQuery) -> None:
    await cb.answer("Seans eskirgan, qaytadan urinib ko‘ring.", show_alert=True)


@router.callback_query(AdmCb.filter((F.s == "set") & (F.a == "clearphoto")))
async def on_clear_photo(cb: CallbackQuery, state: FSMContext, ui: UI, shop: ShopSettings, access: Access) -> None:
    await state.clear()
    await shop.set("product_photo", "", cb.from_user.id)
    await show(cb.from_user.id, ui, shop, access, note="🗑 Rasm o‘chirildi")
    await cb.answer()


@router.callback_query(AdmCb.filter((F.s == "set") & (F.a == "toggle")))
async def on_toggle(
    cb: CallbackQuery, callback_data: AdmCb, ui: UI, shop: ShopSettings, access: Access, bot: Bot
) -> None:
    s = await shop.get()
    if callback_data.v == "link_mode":
        new = "static" if s.link_mode == "invite" else "invite"
        if new == "invite" and not s.channel_id:
            await cb.answer("Avval 📣 Kanal ID ni kiriting.", show_alert=True)
            return
        await shop.set("link_mode", new, cb.from_user.id)
    elif callback_data.v == "sales_enabled":
        await shop.set("sales_enabled", "0" if s.sales_enabled else "1", cb.from_user.id)
    await show(cb.from_user.id, ui, shop, access)
    await cb.answer("✅ O‘zgartirildi")


# --- 👮 Adminlar (faqat egasi) ------------------------------------------------------

async def show_admins(chat_id: int, session: AsyncSession, ui: UI, access: Access, note: str = "") -> None:
    admins = await misc.admins(session)
    await session.commit()
    lines = [f"👑 Egasi: <code>{access.owner_id}</code>"]
    buttons: list[list[tuple[str, AdmCb]]] = []
    for a in admins:
        if a.telegram_id == access.owner_id:
            continue
        name = escape(a.name or "")
        lines.append(f"• {name} <code>{a.telegram_id}</code>")
        buttons.append([(f"❌ {a.name or a.telegram_id}", AdmCb(s="adm", a="del", v=str(a.telegram_id)))])
    text = "👮 <b>Adminlar</b>\n\n" + "\n".join(lines)
    if note:
        text += f"\n\n{note}"
    buttons.append([("➕ Admin qo‘shish", AdmCb(s="adm", a="add"))])
    buttons.append([("⬅️ Orqaga", AdmCb(s="set"))])
    await ui.render(chat_id, text, kb.rows(*buttons))


@router.callback_query(AdmCb.filter(F.s == "adm"))
async def on_admins(
    cb: CallbackQuery, callback_data: AdmCb, state: FSMContext, session: AsyncSession, ui: UI, access: Access
) -> None:
    if not access.is_owner(cb.from_user.id):
        await cb.answer("Adminlarni faqat bot egasi boshqaradi.", show_alert=True)
        return
    if callback_data.a == "add":
        await state.set_state(AdminStates.add_admin)
        await ui.render(
            cb.from_user.id,
            "➕ Yangi adminning <b>Telegram ID</b> sini yuboring yoki uning biror xabarini shu yerga "
            "<b>forward</b> qiling.\n\nℹ️ U avval botga /start bosgan bo‘lishi kerak — aks holda bot unga "
            "cheklarni yubora olmaydi.",
            kb.cancel("adm"),
        )
    elif callback_data.a == "del":
        target = int(callback_data.v)
        await misc.remove_admin(session, target)
        await misc.audit(session, cb.from_user.id, "admin_remove", admin=target)
        await session.commit()
        await access.reload_admins()
        await show_admins(cb.from_user.id, session, ui, access, note="✅ Admin o‘chirildi")
    else:
        await state.clear()
        await show_admins(cb.from_user.id, session, ui, access)
    await cb.answer()


@router.message(AdminStates.add_admin)
async def on_add_admin(message: Message, state: FSMContext, session: AsyncSession, ui: UI, access: Access) -> None:
    await ui.drop(message)
    if not access.is_owner(message.chat.id):
        await state.clear()
        return
    origin = message.forward_origin
    try:
        if isinstance(origin, MessageOriginUser):
            new_id, name = origin.sender_user.id, origin.sender_user.full_name
        elif origin is not None:
            raise v.ValidationError("Bu foydalanuvchi forward'ni yashirgan. ID ni raqam bilan yuboring.")
        else:
            new_id = v.telegram_id(message.text or "")
            known = await users_repo.get(session, new_id)
            name = known.full_name if known else None
    except v.ValidationError as e:
        await ui.render(message.chat.id, f"❗️ {escape(str(e))}", kb.cancel("adm"))
        return
    await misc.add_admin(session, new_id, name, message.chat.id)
    await misc.audit(session, message.chat.id, "admin_add", admin=new_id)
    await session.commit()
    await state.clear()
    await access.reload_admins()
    await show_admins(message.chat.id, session, ui, access, note=f"✅ <code>{new_id}</code> admin qilindi")
