from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards as kb
from app.config import Config
from app.db.repositories import payments, users
from app.handlers.user.common import payment_screen
from app.services.notifier import Notifier
from app.services.shop_settings import ShopSettings
from app.services.ui import UI
from app.states import BuyStates
from app.texts import uz
from app.utils.tasks import BackgroundTasks

router = Router(name="user.receipt")

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


@router.message(BuyStates.waiting_receipt, F.photo | F.document)
async def on_receipt(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    ui: UI,
    shop: ShopSettings,
    redis: Redis,
    notifier: Notifier,
    tasks: BackgroundTasks,
    config: Config,
) -> None:
    chat_id = message.chat.id
    s = await shop.get()

    if message.photo:
        file, file_type = message.photo[-1], "photo"
    else:
        doc = message.document
        assert doc is not None
        too_big = (doc.file_size or 0) > config.max_receipt_mb * 1024 * 1024
        if doc.mime_type not in ALLOWED_MIME or too_big:
            await ui.drop(message)
            await ui.render(chat_id, payment_screen(s, uz.RECEIPT_INVALID), kb.payment_details())
            return
        file, file_type = doc, "document"

    # Anti-spam: daqiqasiga N tadan ko'p chek yo'q
    key = f"rl:receipt:{chat_id}"
    async with redis.pipeline(transaction=False) as p:
        p.incr(key)
        p.expire(key, 60, nx=True)
        hits, _ = await p.execute()
    if hits > config.receipts_per_minute:
        await ui.drop(message)
        await ui.render(chat_id, payment_screen(s, uz.TOO_MANY), kb.payment_details())
        return

    if not s.sales_enabled:
        await state.clear()
        await ui.render(chat_id, uz.SALES_OFF, new=True)
        return

    user = await users.upsert(session, message.from_user)  # type: ignore[arg-type]
    payment = await payments.create(
        session,
        user_id=chat_id,
        amount=s.price,
        file_id=file.file_id,
        file_unique_id=file.file_unique_id,
        file_type=file_type,
    )
    if payment is None:  # parallel ikkinchi chek — unique index ushlab qoldi
        await state.clear()
        await ui.render(chat_id, uz.PENDING_EXISTS, new=True)
        return
    await session.commit()

    await state.clear()
    # Chek rasmi chatda qoladi (dalil), eski ekran o'chib, yangi xabar chekdan keyin chiqadi
    await ui.render(chat_id, uz.RECEIPT_ACCEPTED, new=True)
    tasks.spawn(notifier.new_payment(payment, user), name=f"fanout#{payment.id}")


@router.message(BuyStates.waiting_receipt)
async def on_wrong_receipt(message: Message, ui: UI, shop: ShopSettings) -> None:
    await ui.drop(message)
    await ui.render(message.chat.id, payment_screen(await shop.get(), uz.RECEIPT_INVALID), kb.payment_details())
