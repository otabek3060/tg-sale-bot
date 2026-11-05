from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


def _created() -> Any:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    language_code: Mapped[str | None] = mapped_column(String(8))
    source: Mapped[str | None] = mapped_column(String(64))
    has_purchased: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    is_blocked_bot: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = _created()
    last_active_at: Mapped[datetime] = _created()

    __table_args__ = (
        Index("ix_users_created_at", "created_at"),
        Index("ix_users_username_lower", text("lower(username)")),
    )

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p) or str(self.telegram_id)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    file_id: Mapped[str] = mapped_column(String(256), nullable=False)
    file_unique_id: Mapped[str] = mapped_column(String(64), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)  # photo | document
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", values_callable=lambda e: [m.value for m in e]),
        default=PaymentStatus.pending,
        server_default=PaymentStatus.pending.value,
        nullable=False,
    )
    duplicate_of: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(String(256))
    invite_link: Mapped[str | None] = mapped_column(String(256))
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()

    __table_args__ = (
        Index("ix_payments_status_created", "status", "created_at"),
        Index("ix_payments_user", "user_id"),
        Index("ix_payments_file_unique", "file_unique_id"),
        Index("ix_payments_reviewed_at", "reviewed_at"),
        # Bitta foydalanuvchida bir vaqtda faqat bitta "pending" to'lov bo'lishi mumkin
        Index(
            "ux_payments_one_pending",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )


class AdminMessage(Base):
    """Har bir adminga yuborilgan chek xabari — keyin barcha adminlarda natijani yangilash uchun."""

    __tablename__ = "admin_messages"

    payment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("payments.id", ondelete="CASCADE"), primary_key=True
    )
    admin_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class Admin(Base):
    __tablename__ = "admins"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str | None] = mapped_column(String(128))
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    added_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = _created()


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = _created()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created()

    __table_args__ = (Index("ix_audit_created", "created_at"),)
