from __future__ import annotations

from datetime import date
from sqlalchemy import String, Integer, Date, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Users(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_name: Mapped[str] = mapped_column(String(10))
    sex: Mapped[str] = mapped_column(String(5))
    birthday: Mapped[date] = mapped_column(Date)
    shozoku: Mapped[str | None] = mapped_column(String(45))
    shokui: Mapped[str | None] = mapped_column(String(45))
    skill: Mapped[str | None] = mapped_column(String(45))
    other: Mapped[str | None] = mapped_column(String(200))


class Items(Base):
    __tablename__ = 'items'
    item_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    item_name: Mapped[str] = mapped_column(String(100))
    price: Mapped[int] = mapped_column(Integer)


class Purchases(Base):
    __tablename__ = 'purchases'
    purchase_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(10), ForeignKey("customers.customer_id"))
    purchase_date: Mapped[str] = mapped_column(String(10))


class PurchaseDetails(Base):
    __tablename__ = 'purchase_details'
    detail_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    purchase_id: Mapped[str] = mapped_column(String(10), ForeignKey("purchases.purchase_id"))
    item_id: Mapped[str] = mapped_column(String(10), ForeignKey("items.item_id"))
    quantity: Mapped[int] = mapped_column(Integer)