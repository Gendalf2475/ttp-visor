from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class KTCheck(Base):
    __tablename__ = "kt_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(255), unique=True)
    ticket_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tickets_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    ticket_numbers: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
    raw_range_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff_members.id", ondelete="SET NULL"), nullable=True)
    moderator_alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sender_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sender_is_bot: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    chat_id: Mapped[int] = mapped_column(BigInteger)
    topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int] = mapped_column(BigInteger)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    staff = relationship("StaffMember", back_populates="kt_checks")


Index("ix_kt_checks_checked_at", KTCheck.checked_at)
Index("ix_kt_checks_staff_id", KTCheck.staff_id)
Index("ix_kt_checks_staff_date", KTCheck.staff_id, KTCheck.checked_at)
Index("ix_kt_checks_sender_user_id", KTCheck.sender_user_id)
Index("ix_kt_checks_source", KTCheck.chat_id, KTCheck.message_id)
