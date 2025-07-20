from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'user'
    id: Mapped[str] = mapped_column(Integer, primary_key=True)
    user_name: Mapped[str] = mapped_column(String(10))
    sex: Mapped[str] = mapped_column(String(5))
    birthday: Mapped[str] = mapped_column(String(10))
    shozoku: Mapped[str] = mapped_column(String(45))
    shokui: Mapped[str] = mapped_column(String(45))
    skill: Mapped[str] = mapped_column(String(45))
    other: Mapped[str] = mapped_column(String(10))


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