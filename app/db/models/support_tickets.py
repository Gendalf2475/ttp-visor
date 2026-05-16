from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(255), unique=True)
    ticket_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff_members.id", ondelete="SET NULL"), nullable=True)
    moderator_alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sender_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sender_is_bot: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    chat_id: Mapped[int] = mapped_column(BigInteger)
    topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int] = mapped_column(BigInteger)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    staff = relationship("StaffMember", back_populates="support_tickets")


Index("ix_support_tickets_closed_at", SupportTicket.closed_at)
Index("ix_support_tickets_staff_id", SupportTicket.staff_id)
Index("ix_support_tickets_sender_user_id", SupportTicket.sender_user_id)
Index("ix_support_tickets_source", SupportTicket.chat_id, SupportTicket.message_id)
