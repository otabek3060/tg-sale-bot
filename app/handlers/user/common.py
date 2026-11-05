from __future__ import annotations

from app import keyboards as kb
from app.db.models import User
from app.services.shop_settings import Shop
from app.services.ui import UI
from app.texts import uz


async def show_home(chat_id: int, user: User, ui: UI, shop: Shop, *, new: bool = False) -> None:
    if user.has_purchased:
        await ui.render(chat_id, uz.purchased(user.first_name), kb.purchased(), new=new)
    else:
        await ui.render(
            chat_id,
            uz.home(user.first_name, shop.product_text, shop.price),
            kb.home(),
            photo=shop.product_photo or None,
            new=new,
        )


def payment_screen(shop: Shop, warning: str | None = None) -> str:
    return uz.payment_details(shop.card_number, shop.card_holder, shop.price, warning)
