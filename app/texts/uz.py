"""Foydalanuvchiga ko'rinadigan barcha matnlar (o'zbek tili). HTML parse_mode."""
from __future__ import annotations

from html import escape

# --- tugmalar ---------------------------------------------------------------------
BTN_BUY = "🛒 Sotib olish"
BTN_BACK = "⬅️ Orqaga"
BTN_RETRY = "🔄 Chekni qayta yuborish"
BTN_GET_LINK = "🔗 Havolani olish"

BTN_SETTINGS = "⚙️ Sozlamalar"
BTN_USERS = "👥 Userlar"
BTN_SALES = "💰 Sotuvlar"
BTN_BROADCAST = "📢 Xabar yuborish"
BTN_EXIT = "🏠 Chiqish"
ADMIN_BUTTONS = (BTN_SETTINGS, BTN_USERS, BTN_SALES, BTN_BROADCAST, BTN_EXIT)

BTN_APPROVE = "✅ Tasdiqlash"
BTN_REJECT = "❌ Rad etish"

DEFAULT_PRODUCT_TEXT = (
    "🔤 <b>Yangi o'zbek kirill alifbosiga o'tkazuvchi dastur</b>\n\n"
    "Matnlaringizni lotin va eski kirill yozuvidan yangi kirill alifbosiga bir zumda o'tkazadi.\n\n"
    "✅ Tez va aniq o'girish\n"
    "✅ Word va matn fayllari bilan ishlaydi\n"
    "✅ Internetsiz ishlaydi"
)

REJECT_REASONS: dict[str, str] = {
    "sum": "Summa noto'g'ri",
    "unread": "Chek o'qilmaydi",
    "nopay": "To'lov tushmagan",
    "fake": "Soxta chek",
}


def money(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " so'm"


def card(number: str) -> str:
    return " ".join(number[i : i + 4] for i in range(0, len(number), 4))


def home(name: str, product_text: str, price: int) -> str:
    return (
        f"👋 Assalomu alaykum, <b>{escape(name)}</b>!\n\n"
        f"{product_text}\n\n"
        f"💰 Narxi: <b>{money(price)}</b>"
    )


def purchased(name: str) -> str:
    return (
        f"👋 <b>{escape(name)}</b>, siz dasturni allaqachon xarid qilgansiz. ✅\n\n"
        "Havolani qayta olish uchun quyidagi tugmani bosing."
    )


def payment_details(card_number: str, holder: str, price: int, warning: str | None = None) -> str:
    text = (
        "💳 <b>To'lov ma'lumotlari</b>\n\n"
        f"Karta raqami: <code>{card_number}</code>\n"
        f"<i>({card(card_number)})</i>\n"
        f"Karta egasi: <b>{escape(holder)}</b>\n"
        f"Summa: <b>{money(price)}</b>\n\n"
        "📸 To'lovni amalga oshiring va <b>chek (skrinshot yoki fayl)</b>ni shu yerga yuboring."
    )
    if warning:
        text += f"\n\n{warning}"
    return text


RECEIPT_INVALID = "⚠️ Iltimos, chekni <b>rasm</b> yoki <b>fayl</b> (JPG, PNG, PDF, 10 MB gacha) ko'rinishida yuboring."
RECEIPT_ACCEPTED = (
    "✅ <b>Chekingiz qabul qilindi!</b>\n\n"
    "Chek tekshirilib, <b>1 soat ichida</b> sizga havola yuboriladi. ⏳"
)
PENDING_EXISTS = "⏳ Chekingiz tekshirilmoqda, iltimos kuting."
SALES_OFF = "⛔️ Sotuv vaqtincha to'xtatilgan. Keyinroq urinib ko'ring."
TOO_MANY = "⚠️ Juda ko'p urinish. Birozdan so'ng qayta urinib ko'ring."
TECH_ERROR = "⚠️ Texnik nosozlik. Birozdan so'ng urinib ko'ring."
LINK_COOLDOWN = "⏳ Havola yaqinda yuborilgan. 10 daqiqadan so'ng qayta urinib ko'ring."
NOT_PURCHASED = "Siz hali xarid qilmagansiz."


def approved(link: str, hours: int | None) -> str:
    text = (
        "🎉 <b>To'lovingiz tasdiqlandi!</b> Xaridingiz uchun rahmat.\n\n"
        f"🔗 Havola: {escape(link)}"
    )
    if hours:
        text += f"\n\n⚠️ Havola faqat siz uchun va {hours} soat amal qiladi."
    return text


def link_again(link: str, hours: int | None) -> str:
    text = f"🔗 Sizning havolangiz: {escape(link)}"
    if hours:
        text += f"\n\n⚠️ Havola faqat siz uchun va {hours} soat amal qiladi."
    return text


def rejected(reason: str) -> str:
    return f"❌ <b>To'lovingiz rad etildi.</b>\n\nSabab: {escape(reason)}"
