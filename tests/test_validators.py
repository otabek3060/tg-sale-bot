import pytest

from app.utils import validators as v


def test_card_number() -> None:
    assert v.card_number("8600 1234 5678 9012") == "8600123456789012"
    for bad in ("1234", "8600 1234 5678 9013", "abcd" * 4):
        with pytest.raises(v.ValidationError):
            v.card_number(bad)


def test_price() -> None:
    assert v.price("75 000") == "75000"
    with pytest.raises(v.ValidationError):
        v.price("-5")


def test_url_and_channel() -> None:
    assert v.url("https://t.me/x") == "https://t.me/x"
    assert v.channel_id("-1001234567890") == "-1001234567890"
    assert v.channel_id("@my_channel") == "@my_channel"
    with pytest.raises(v.ValidationError):
        v.url("ftp://x")
    with pytest.raises(v.ValidationError):
        v.channel_id("12345")
