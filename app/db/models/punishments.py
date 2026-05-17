from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Punishment(Base):
    __tablename__ = "punishments"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(255), unique=True)
    punishment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    punishment_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rule_missing: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff_members.id", ondelete="SET NULL"), nullable=True)
    moderator_alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sender_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sender_is_bot: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    chat_id: Mapped[int] = mapped_column(BigInteger)
    topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int] = mapped_column(BigInteger)
    punished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    staff = relationship("StaffMember", back_populates="punishments")


Index("ix_punishments_punished_at", Punishment.punished_at)
Index("ix_punishments_staff_id", Punishment.staff_id)
Index("ix_punishments_sender_user_id", Punishment.sender_user_id)
Index("ix_punishments_action", Punishment.action)
Index("ix_punishments_punishment_type", Punishment.punishment_type)
Index("ix_punishments_staff_date_type", Punishment.staff_id, Punishment.punished_at, Punishment.punishment_type)
Index("ix_punishments_source", Punishment.chat_id, Punishment.message_id)
