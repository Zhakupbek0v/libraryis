"""Модель данных (раздел 4.11 ТЗ)."""
from datetime import date, datetime

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer,
                        String, Text, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


class AppUser(Base):
    __tablename__ = "app_user"
    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    full_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))  # librarian / head / admin
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Reader(Base):
    __tablename__ = "reader"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_number: Mapped[str] = mapped_column(String(20), unique=True)
    full_name: Mapped[str] = mapped_column(String(100), index=True)
    birth_date: Mapped[date] = mapped_column(Date)
    address: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    registered_at: Mapped[date] = mapped_column(Date, default=date.today)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    loans: Mapped[list["Loan"]] = relationship(back_populates="reader")


class Book(Base):
    __tablename__ = "book"
    __table_args__ = (
        CheckConstraint("copies_total >= 0", name="ck_total"),
        CheckConstraint("copies_available >= 0 AND copies_available <= copies_total", name="ck_avail"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    isbn: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    author: Mapped[str] = mapped_column(String(150), index=True)
    genre: Mapped[str] = mapped_column(String(50), default="")
    publisher: Mapped[str] = mapped_column(String(100), default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    copies_total: Mapped[int] = mapped_column(Integer, default=1)
    copies_available: Mapped[int] = mapped_column(Integer, default=1)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    loans: Mapped[list["Loan"]] = relationship(back_populates="book")


class Loan(Base):
    __tablename__ = "loan"
    id: Mapped[int] = mapped_column(primary_key=True)
    reader_id: Mapped[int] = mapped_column(ForeignKey("reader.id"))
    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    issued_at: Mapped[date] = mapped_column(Date)
    due_at: Mapped[date] = mapped_column(Date)
    returned_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    renewals: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="выдана")  # выдана / возвращена / просрочена
    reader: Mapped[Reader] = relationship(back_populates="loans")
    book: Mapped[Book] = relationship(back_populates="loans")
    user: Mapped[AppUser] = relationship()


Index("ix_loan_status", Loan.status)


class Supplier(Base):
    __tablename__ = "supplier"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    phone: Mapped[str] = mapped_column(String(20), default="")
    address: Mapped[str] = mapped_column(String(200), default="")


class PurchaseOrder(Base):
    __tablename__ = "purchase_order"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"))
    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    ordered_at: Mapped[date] = mapped_column(Date, default=date.today)
    status: Mapped[str] = mapped_column(String(20), default="создан")  # создан / отправлен / получен
    supplier: Mapped[Supplier] = relationship()
    book: Mapped[Book] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    description: Mapped[str] = mapped_column(Text, default="")
    user: Mapped[AppUser | None] = relationship()


engine = create_engine(config.DB_URL, future=True)

if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        # встроенный lower() в SQLite не понимает кириллицу — подменяем на Python-версию
        dbapi_conn.create_function("lower", 1, lambda v: v.lower() if isinstance(v, str) else v, deterministic=True)

Session = sessionmaker(engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(engine)
