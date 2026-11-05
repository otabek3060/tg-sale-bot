from __future__ import annotations

import re

_URL = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


class ValidationError(ValueError):
    pass


def luhn_ok(number: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def card_number(raw: str) -> str:
    digits = re.sub(r"[\s-]", "", raw or "")
    if not digits.isdigit() or len(digits) != 16:
        raise ValidationError("Karta raqami 16 ta raqamdan iborat bo'lishi kerak.")
    if not luhn_ok(digits):
        raise ValidationError("Karta raqami noto'g'ri (nazorat raqami mos kelmadi).")
    return digits


def card_holder(raw: str) -> str:
    v = " ".join((raw or "").split())
    if not 3 <= len(v) <= 64:
        raise ValidationError("Karta egasi 3–64 belgi bo'lishi kerak.")
    return v


def price(raw: str) -> str:
    digits = re.sub(r"[\s_.,]", "", raw or "")
    if not digits.isdigit() or int(digits) <= 0 or int(digits) > 100_000_000:
        raise ValidationError("Narx musbat butun son bo'lishi kerak (so'mda).")
    return str(int(digits))


def product_text(raw: str, with_photo: bool) -> str:
    limit = 900 if with_photo else 3500  # salomlashish va narx uchun joy qoldiramiz
    v = (raw or "").strip()
    if not v:
        raise ValidationError("Matn bo'sh bo'lmasligi kerak.")
    if len(v) > limit:
        raise ValidationError(f"Matn juda uzun ({len(v)}). Maksimum: {limit} belgi.")
    return v


def url(raw: str) -> str:
    v = (raw or "").strip()
    if not _URL.match(v):
        raise ValidationError("To'g'ri havola yuboring (https://...).")
    return v


def channel_id(raw: str) -> str:
    v = (raw or "").strip()
    if v.startswith("@") and len(v) > 5:
        return v
    if re.fullmatch(r"-100\d{5,}", v):
        return v
    raise ValidationError("Kanal ID -100... ko'rinishida yoki @username bo'lishi kerak.")


def telegram_id(raw: str) -> int:
    v = (raw or "").strip()
    if not v.isdigit() or not 3 <= len(v) <= 16:
        raise ValidationError("Telegram ID faqat raqamlardan iborat bo'lishi kerak.")
    return int(v)
