"""To'liq oqim testlari: haqiqiy Dispatcher + PostgreSQL + Redis, soxta Telegram API."""
from __future__ import annotations

import asyncio
from datetime import timedelta

from aiogram.methods import (
    CopyMessage,
    CreateChatInviteLink,
    DeleteMessage,
    EditMessageCaption,
    EditMessageReplyMarkup,
    EditMessageText,
    SendDocument,
    SendMessage,
    SendPhoto,
)
from sqlalchemy import func, select, update

from app.bot import App
from app.callbacks import AdmCb, PayCb, UserCb
from app.db.models import AdminMessage, AuditLog, Payment, PaymentStatus, User
from app.texts import uz
from app.worker.scheduler import remind_overdue
from tests.conftest import ADMIN2, OWNER
from tests.fake_tg import FakeTelegram, Sim

U = 5001
BUY = UserCb(action="buy").pack()


def no_errors(fake: FakeTelegram) -> None:
    for c in fake.calls:
        t = (getattr(c, "text", None) or "") + (getattr(c, "caption", None) or "")
        assert uz.TECH_ERROR not in t and "Botda xato" not in t, t


async def pay(sim: Sim, app: App, uid: int = U, photo: str = "chek1") -> Payment:
    await sim.send(uid, "/start")
    await sim.click(uid, BUY)
    await sim.send(uid, photo=photo)
    await app.tasks.wait()
    async with app.sf() as s:
        return (await s.execute(select(Payment).where(Payment.user_id == uid).order_by(Payment.id.desc()))).scalars().first()


async def get_user(app: App, uid: int) -> User:
    async with app.sf() as s:
        return await s.get(User, uid)


# ---------------------------------------------------------------------------------

async def test_start_saves_user_once(app: App, sim: Sim, fake: FakeTelegram) -> None:
    await sim.send(U, "/start ref_insta", name="Javohir")
    await sim.send(U, "/start other", name="Javohir")
    async with app.sf() as s:
        assert (await s.execute(select(func.count()).select_from(User))).scalar_one() == 1
    u = await get_user(app, U)
    assert u.first_name == "Javohir" and u.username == f"user{U}"
    assert u.source == "ref_insta"  # manba birinchi marta yoziladi
    sends = fake.of(SendMessage, U)
    assert uz.BTN_BUY in sends[-1].reply_markup.inline_keyboard[0][0].text
    assert len(fake.of(DeleteMessage, U)) >= 3  # 2 ta /start + eski ekran
    no_errors(fake)


async def test_buy_shows_payment_details_in_same_message(app: App, sim: Sim, fake: FakeTelegram) -> None:
    await app.shop.set("card_number", "8600123456789012", OWNER)
    await sim.send(U, "/start")
    fake.reset()
    await sim.click(U, BUY)
    edits = fake.of(EditMessageText, U)
    assert len(edits) == 1 and not fake.of(SendMessage, U)  # yangi xabar emas — tahrir
    assert "8600123456789012" in edits[0].text and "50 000 so'm" in edits[0].text


async def test_full_purchase_static_link(app: App, sim: Sim, fake: FakeTelegram) -> None:
    await app.shop.set("static_link", "https://example.com/download", OWNER)
    p = await pay(sim, app)
    assert p.status == PaymentStatus.pending and p.amount == 50000
    assert any(uz.RECEIPT_ACCEPTED in t for t in fake.texts(U))

    # chek ikkala adminga ham borgan
    assert {c.chat_id for c in fake.of(SendPhoto)} == {OWNER, ADMIN2}
    async with app.sf() as s:
        assert (await s.execute(select(func.count()).select_from(AdminMessage))).scalar_one() == 2

    await sim.click(OWNER, PayCb(action="ok", pid=p.id).pack(), name="Owner")
    await app.tasks.wait()

    assert any("https://example.com/download" in t for t in fake.texts(U))
    u = await get_user(app, U)
    assert u.has_purchased
    edited = fake.of(EditMessageCaption)
    assert {c.chat_id for c in edited} == {OWNER, ADMIN2}
    assert all("Tasdiqladi" in c.caption and c.reply_markup is None for c in edited)
    no_errors(fake)

    # keyingi /start — "allaqachon xarid qilgansiz"
    await sim.send(U, "/start")
    assert "allaqachon" in fake.of(SendMessage, U)[-1].text


async def test_concurrent_approve_only_one_wins(app: App, sim: Sim, fake: FakeTelegram) -> None:
    await app.shop.set("static_link", "https://example.com/d", OWNER)
    p = await pay(sim, app)
    fake.reset()
    data = PayCb(action="ok", pid=p.id).pack()
    await asyncio.gather(sim.click(OWNER, data), sim.click(ADMIN2, data))
    await app.tasks.wait()
    approvals = [t for t in fake.texts(U) if "tasdiqlandi" in t]
    assert len(approvals) == 1
    assert sum("allaqachon" in a for a in fake.alerts()) == 1
    async with app.sf() as s:
        audits = (await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "approve"))).scalar_one()
    assert audits == 1


async def test_invite_link_mode(app: App, sim: Sim, fake: FakeTelegram) -> None:
    await app.shop.set("channel_id", "-1001234567890", OWNER)
    await app.shop.set("link_mode", "invite", OWNER)
    p = await pay(sim, app)
    await sim.click(OWNER, PayCb(action="ok", pid=p.id).pack())
    inv = fake.of(CreateChatInviteLink)
    assert len(inv) == 1 and inv[0].member_limit == 1 and inv[0].chat_id == -1001234567890
    assert any("https://t.me/+fake" in t and "24 soat" in t for t in fake.texts(U))
    async with app.sf() as s:
        assert (await s.get(Payment, p.id)).invite_link.startswith("https://t.me/+fake")


async def test_link_error_keeps_payment_pending(app: App, sim: Sim, fake: FakeTelegram) -> None:
    # static_link sozlanmagan
    p = await pay(sim, app)
    await sim.click(OWNER, PayCb(action="ok", pid=p.id).pack())
    assert any("Havola yaratib bo'lmadi" in a for a in fake.alerts())
    async with app.sf() as s:
        assert (await s.get(Payment, p.id)).status == PaymentStatus.pending
        assert not (await s.get(User, U)).has_purchased


async def test_reject_with_reason_then_retry(app: App, sim: Sim, fake: FakeTelegram) -> None:
    p = await pay(sim, app)
    await sim.click(ADMIN2, PayCb(action="no", pid=p.id).pack())
    assert fake.of(EditMessageReplyMarkup, ADMIN2)
    await sim.click(ADMIN2, PayCb(action="r", pid=p.id, code="sum").pack())
    await app.tasks.wait()
    async with app.sf() as s:
        pp = await s.get(Payment, p.id)
    assert pp.status == PaymentStatus.rejected and pp.reject_reason == "Summa noto'g'ri"
    last_user_msg = fake.of(SendMessage, U)[-1]
    assert "rad etildi" in last_user_msg.text
    assert last_user_msg.reply_markup.inline_keyboard[0][0].text == uz.BTN_RETRY
    assert all("Rad etdi" in c.caption for c in fake.of(EditMessageCaption))

    await sim.click(U, UserCb(action="retry").pack())
    await sim.send(U, photo="chek2")
    async with app.sf() as s:
        n = (await s.execute(select(func.count()).select_from(Payment).where(Payment.user_id == U))).scalar_one()
    assert n == 2
    no_errors(fake)


async def test_reject_custom_reason(app: App, sim: Sim, fake: FakeTelegram) -> None:
    p = await pay(sim, app)
    await sim.click(OWNER, PayCb(action="custom", pid=p.id).pack())
    await sim.send(OWNER, "Boshqa kartaga o'tkazilgan")
    async with app.sf() as s:
        assert (await s.get(Payment, p.id)).reject_reason == "Boshqa kartaga o'tkazilgan"
    assert any("Boshqa kartaga" in t for t in fake.texts(U))


async def test_fake_receipt_offers_ban(app: App, sim: Sim, fake: FakeTelegram) -> None:
    p = await pay(sim, app)
    await sim.click(OWNER, PayCb(action="r", pid=p.id, code="fake").pack())
    await app.tasks.wait()
    owner_edit = [c for c in fake.of(EditMessageCaption) if c.chat_id == OWNER][-1]
    ban_data = owner_edit.reply_markup.inline_keyboard[0][0].callback_data
    await sim.click(OWNER, ban_data, message_id=999)
    assert (await get_user(app, U)).is_banned
    fake.reset()
    await sim.send(U, "/start")
    assert not fake.calls  # bloklangan userga javob yo'q


async def test_wrong_content_is_deleted_and_screen_edited(app: App, sim: Sim, fake: FakeTelegram) -> None:
    await sim.send(U, "/start")
    await sim.click(U, BUY)
    fake.reset()
    await sim.send(U, "salom")
    assert fake.of(DeleteMessage, U) and not fake.of(SendMessage, U)
    assert uz.RECEIPT_INVALID in fake.of(EditMessageText, U)[-1].text
    await sim.send(U, document=("zip1", "application/zip", 1000))
    await sim.send(U, document=("big", "application/pdf", 50 * 1024 * 1024))
    async with app.sf() as s:
        assert (await s.execute(select(func.count()).select_from(Payment))).scalar_one() == 0
    await sim.send(U, document=("pdf1", "application/pdf", 200_000))
    await app.tasks.wait()
    assert {c.chat_id for c in fake.of(SendDocument)} == {OWNER, ADMIN2}


async def test_only_one_pending(app: App, sim: Sim, fake: FakeTelegram) -> None:
    await pay(sim, app)
    await sim.click(U, BUY)
    assert any(uz.PENDING_EXISTS in a for a in fake.alerts())


async def test_duplicate_receipt_flagged(app: App, sim: Sim, fake: FakeTelegram) -> None:
    p1 = await pay(sim, app, uid=U, photo="same")
    p2 = await pay(sim, app, uid=U + 1, photo="same")
    assert p2.duplicate_of == p1.id
    assert any(f"avval #{p1.id}" in (c.caption or "") for c in fake.of(SendPhoto))


async def test_non_admin_cannot_act_as_admin(app: App, sim: Sim, fake: FakeTelegram) -> None:
    p = await pay(sim, app)
    await sim.click(U, PayCb(action="ok", pid=p.id).pack())  # soxtalashtirilgan callback
    await sim.send(U, "/admin")
    async with app.sf() as s:
        assert (await s.get(Payment, p.id)).status == PaymentStatus.pending
    assert not any("Admin panel" in t for t in fake.texts(U))


async def test_blocked_user_on_approve(app: App, sim: Sim, fake: FakeTelegram) -> None:
    await app.shop.set("static_link", "https://example.com/d", OWNER)
    p = await pay(sim, app)
    fake.blocked.add(U)
    await sim.click(OWNER, PayCb(action="ok", pid=p.id).pack())
    await app.tasks.wait()
    assert (await get_user(app, U)).is_blocked_bot
    assert any("bloklagan" in c.caption for c in fake.of(EditMessageCaption))


async def test_get_link_again_with_cooldown(app: App, sim: Sim, fake: FakeTelegram) -> None:
    await app.shop.set("static_link", "https://example.com/d", OWNER)
    p = await pay(sim, app)
    await sim.click(OWNER, PayCb(action="ok", pid=p.id).pack())
    await sim.send(U, "/start")
    fake.reset()
    await sim.click(U, UserCb(action="link").pack())
    assert any("https://example.com/d" in t for t in fake.texts(U))
    await sim.click(U, UserCb(action="link").pack())
    assert any(uz.LINK_COOLDOWN in a for a in fake.alerts())


async def test_throttling(fake: FakeTelegram) -> None:
    from tests.conftest import make_app

    app = await make_app(fake, user_rate_limit=3)
    sim = Sim(app.bot, app.dp)
    try:
        await asyncio.gather(*(sim.click(U, BUY) for _ in range(10)))
        assert sum(a == uz.TOO_MANY for a in fake.alerts()) >= 6
    finally:
        await app.shutdown()


async def test_sales_disabled(app: App, sim: Sim, fake: FakeTelegram) -> None:
    await app.shop.set("sales_enabled", "0", OWNER)
    await sim.send(U, "/start")
    await sim.click(U, BUY)
    assert any(uz.SALES_OFF in a for a in fake.alerts())


async def test_settings_edit_with_validation(app: App, sim: Sim, fake: FakeTelegram) -> None:
    await sim.click(OWNER, AdmCb(s="set", a="edit", v="card_number").pack())
    await sim.send(OWNER, "1234 5678 9012 3456")  # Luhn xato
    assert any("nazorat raqami" in t for t in fake.texts(OWNER))
    await sim.send(OWNER, "8600 1234 5678 9012")
    await sim.click(OWNER, AdmCb(s="set", a="save").pack())
    assert (await app.shop.get()).card_number == "8600123456789012"

    await sim.click(OWNER, AdmCb(s="set", a="edit", v="price").pack())
    await sim.send(OWNER, "75 000")
    await sim.click(OWNER, AdmCb(s="set", a="save").pack())
    assert (await app.shop.get()).price == 75000
    async with app.sf() as s:
        n = (await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "setting_change"))).scalar_one()
    assert n == 2
    no_errors(fake)


async def test_owner_adds_and_removes_admin(app: App, sim: Sim, fake: FakeTelegram) -> None:
    await sim.click(OWNER, AdmCb(s="adm", a="add").pack())
    await sim.send(OWNER, "777777")
    assert 777777 in await app.access.admin_ids()
    await sim.click(ADMIN2, AdmCb(s="adm", a="del", v="777777").pack())  # oddiy admin o'chira olmaydi
    assert 777777 in await app.access.admin_ids()
    await sim.click(OWNER, AdmCb(s="adm", a="del", v="777777").pack())
    assert 777777 not in await app.access.admin_ids()


async def test_admin_panel_sections_render(app: App, sim: Sim, fake: FakeTelegram) -> None:
    await pay(sim, app)
    await sim.send(OWNER, "/admin")
    for btn in (uz.BTN_SETTINGS, uz.BTN_USERS, uz.BTN_SALES):
        await sim.send(OWNER, btn)
    for data in (
        AdmCb(s="users", a="list", v="0"), AdmCb(s="user", v=str(U)), AdmCb(s="users", a="xlsx"),
        AdmCb(s="sales", a="pending"), AdmCb(s="sales", a="xlsx"), AdmCb(s="sales", a="x", v="7"),
        AdmCb(s="adm"), AdmCb(s="home"),
    ):
        await sim.click(OWNER, data.pack())
    await sim.click(OWNER, AdmCb(s="users", a="search").pack())
    await sim.send(OWNER, f"@user{U}")
    await app.tasks.wait()
    assert len(fake.of(SendDocument, OWNER)) == 2  # 2 ta Excel
    assert any("Kutilayotgan to'lovlar: 1" in t for t in fake.texts(OWNER))
    assert any("👤 <b>Test</b>" in t for t in fake.texts(OWNER))
    no_errors(fake)


async def test_reminder_for_overdue(app: App, sim: Sim, fake: FakeTelegram) -> None:
    p = await pay(sim, app)
    async with app.sf() as s:
        await s.execute(update(Payment).where(Payment.id == p.id).values(created_at=func.now() - timedelta(hours=1)))
        await s.commit()
    assert await remind_overdue(app.sf, app.notifier, 50) == 1
    assert await remind_overdue(app.sf, app.notifier, 50) == 0
    assert any("tekshirilmagan" in t for t in fake.texts(ADMIN2))


async def test_broadcast(app: App, sim: Sim, fake: FakeTelegram) -> None:
    for uid in range(6000, 6030):
        await sim.send(uid, "/start")
    fake.blocked.add(6005)
    app.dp["broadcaster"].rate = 1000
    await sim.send(OWNER, uz.BTN_BROADCAST)
    await sim.send(OWNER, "Yangilik!")
    await sim.click(OWNER, AdmCb(s="bc", a="aud", v="all").pack())
    await sim.click(OWNER, AdmCb(s="bc", a="go", v="all").pack())
    await app.tasks.wait()
    assert len(fake.of(CopyMessage)) == 31  # 30 user + egasi (u ham bot foydalanuvchisi)
    assert (await get_user(app, 6005)).is_blocked_bot
    assert any("Yuborildi: 30" in t for t in fake.texts(OWNER))


async def test_race_loser_invite_link_is_revoked(app: App, sim: Sim, fake: FakeTelegram) -> None:
    from aiogram.methods import RevokeChatInviteLink

    await app.shop.set("channel_id", "-1001234567890", OWNER)
    await app.shop.set("link_mode", "invite", OWNER)
    p = await pay(sim, app)
    data = PayCb(action="ok", pid=p.id).pack()
    await asyncio.gather(sim.click(OWNER, data), sim.click(ADMIN2, data))
    created = len(fake.of(CreateChatInviteLink))
    revoked = len(fake.of(RevokeChatInviteLink))
    assert created - revoked == 1  # foydalanuvchida faqat bitta amaldagi havola
    assert sum("tasdiqlandi" in t for t in fake.texts(U)) == 1
