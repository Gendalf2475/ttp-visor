from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StaffMember(Base):
    __tablename__ = "staff_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    nickname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rank: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mentor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    real_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    role: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    bindings = relationship("ModeratorBinding", back_populates="staff", cascade="all, delete-orphan")
    active_periods = relationship("StaffActivePeriod", back_populates="staff", cascade="all, delete-orphan")
    support_tickets = relationship("SupportTicket", back_populates="staff")
    kt_checks = relationship("KTCheck", back_populates="staff")
    punishments = relationship("Punishment", back_populates="staff")


Index("ix_staff_members_username", StaffMember.username)
Index("ix_staff_members_nickname", StaffMember.nickname)
Index("ix_staff_members_is_active", StaffMember.is_active)


class StaffActivePeriod(Base):
    __tablename__ = "staff_active_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff_members.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    staff = relationship("StaffMember", back_populates="active_periods")


Index("ix_staff_active_periods_staff_id", StaffActivePeriod.staff_id)
Index("ix_staff_active_periods_open", StaffActivePeriod.staff_id, StaffActivePeriod.ended_at)


class StaffExtraOccupation(Base):
    __tablename__ = "staff_extra_occupations"
    __table_args__ = (
        UniqueConstraint(
            "nickname",
            "direction",
            "occupation",
            "position",
            name="uq_staff_extra_occupations_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(255))
    direction: Mapped[str] = mapped_column(String(255))
    occupation: Mapped[str] = mapped_column(String(255))
    position: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


Index("ix_staff_extra_occupations_nickname", StaffExtraOccupation.nickname)
Index("ix_staff_extra_occupations_is_active", StaffExtraOccupation.is_active)
