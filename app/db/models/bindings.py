from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ModeratorBinding(Base):
    __tablename__ = "moderator_bindings"
    __table_args__ = (UniqueConstraint("alias_normalized", name="uq_moderator_bindings_alias_normalized"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff_members.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(255))
    alias_normalized: Mapped[str] = mapped_column(String(255))
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    staff = relationship("StaffMember", back_populates="bindings")


Index("ix_moderator_bindings_staff_id", ModeratorBinding.staff_id)
Index("ix_moderator_bindings_telegram_username", ModeratorBinding.telegram_username)
