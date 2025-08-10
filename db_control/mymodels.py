# backend/db_control/mymodels.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    String,
    Text,
    DateTime,
    DECIMAL,
    ForeignKey,
    BigInteger,
    Index,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# MySQL 方言タイプ（UNSIGNED / BINARY / MEDIUMBLOB / DATETIME(6) 用）
from sqlalchemy.dialects.mysql import (
    INTEGER as MySQLInteger,
    BINARY as MySQLBinary,
    MEDIUMBLOB,
    DATETIME as MySQLDateTime,
)


class Base(DeclarativeBase):
    """Declarative base for all models."""
    pass


# -------------------------
# account
# -------------------------
class Account(Base):
    __tablename__ = "account"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Relationships
    trips: Mapped[List["Trip"]] = relationship(back_populates="account")
    pictures: Mapped[List["Picture"]] = relationship(back_populates="account")

    def __repr__(self) -> str:
        return f"<Account id={self.id} email={self.email!r}>"


# -------------------------
# trip
# -------------------------
class Trip(Base):
    __tablename__ = "trip"

    trip_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), nullable=False)
    trip_started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    account: Mapped["Account"] = relationship(back_populates="trips")
    pictures: Mapped[List["Picture"]] = relationship(back_populates="trip")

    def __repr__(self) -> str:
        return f"<Trip id={self.trip_id} account_id={self.account_id} started_at={self.trip_started_at!r}>"


# -------------------------
# picture
# -------------------------
class Picture(Base):
    __tablename__ = "picture"

    picture_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), nullable=False)
    trip_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("trip.trip_id", ondelete="SET NULL"),
        nullable=True,
    )

    pictured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    gps_lat: Mapped[Optional[float]] = mapped_column(DECIMAL(9, 6), nullable=True)
    gps_lng: Mapped[Optional[float]] = mapped_column(DECIMAL(9, 6), nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    speech: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    situation_for_quiz: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    image_size: Mapped[int] = mapped_column(MySQLInteger(unsigned=True), nullable=False)
    sha256: Mapped[Optional[bytes]] = mapped_column(MySQLBinary(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )

    # Relationships
    account: Mapped["Account"] = relationship(back_populates="pictures")
    trip: Mapped[Optional["Trip"]] = relationship(back_populates="pictures")
    data: Mapped[Optional["PictureData"]] = relationship(
        back_populates="picture",
        uselist=False,
        cascade="all, delete-orphan",   # 子を明示的に先に DELETE する
        passive_deletes=True,           # DB の ON DELETE CASCADE に任せる（NULL化しない）
        single_parent=True,             # 1対1の整合性
    )

    # Indexes（DDL に合わせて作成）
    __table_args__ = (
        Index("idx_picture_owner_created", "account_id", created_at.desc()),
        Index("idx_picture_trip", "trip_id"),
        Index("idx_picture_time", "pictured_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Picture id={self.picture_id} account_id={self.account_id} "
            f"trip_id={self.trip_id} pictured_at={self.pictured_at!r}>"
        )


# -------------------------
# picture_data (1:1, PK=FK)
# -------------------------
class PictureData(Base):
    __tablename__ = "picture_data"

    picture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("picture.picture_id", ondelete="CASCADE"),
        primary_key=True,
    )
    image_binary: Mapped[bytes] = mapped_column(MEDIUMBLOB, nullable=False)

    # Relationships
    picture: Mapped["Picture"] = relationship(back_populates="data")

    def __repr__(self) -> str:
        return f"<PictureData picture_id={self.picture_id}>"
