"""Бизнес-логика LibraryIS. Каждая функция принимает сессию SQLAlchemy.
Номера ФТ-* соответствуют функциональным требованиям из технического задания."""
from __future__ import annotations

import csv
import re
import shutil
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import bcrypt
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from . import config
from .models import (AppUser, AuditLog, Book, Loan, PurchaseOrder, Reader, Supplier, engine)


class BusinessError(Exception):
    """Ошибка бизнес-правила: текст показывается пользователю как есть."""


# ----------------------------------------------------------------- журнал / безопасность
def log(s, user_id, action: str, description: str = ""):
    """ФТ-32: журнал действий пользователей."""
    s.add(AuditLog(user_id=user_id, action=action, description=description, created_at=datetime.now()))


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode()


def check_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode("utf-8"), h.encode())
    except ValueError:
        return False


def authenticate(s, login: str, password: str) -> AppUser:
    """Вход по логину и паролю; блокировка после 5 неудачных попыток."""
    u = s.scalar(select(AppUser).where(AppUser.login == login.strip()))
    if u is None:
        raise BusinessError("Неверный логин или пароль")
    if not u.is_active:
        raise BusinessError("Учётная запись отключена")
    if u.is_locked:
        raise BusinessError("Учётная запись заблокирована после 5 неудачных попыток входа.\n"
                            "Обратитесь к администратору.")
    if not check_password(password, u.password_hash):
        u.failed_attempts += 1
        left = config.MAX_ATTEMPTS - u.failed_attempts
        if u.failed_attempts >= config.MAX_ATTEMPTS:
            u.is_locked = True
            log(s, u.id, "Блокировка учётной записи", f"{u.login}: {config.MAX_ATTEMPTS} неудачных попыток входа")
            s.commit()
            raise BusinessError("Учётная запись заблокирована после 5 неудачных попыток входа.")
        s.commit()
        raise BusinessError(f"Неверный логин или пароль. Осталось попыток: {left}")
    u.failed_attempts = 0
    log(s, u.id, "Вход в систему", u.login)
    s.commit()
    return u


# ----------------------------------------------------------------- валидация
PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-()]{8,18}[0-9]$")


def validate_phone(phone: str):
    if phone and not PHONE_RE.match(phone.strip()):
        raise BusinessError("Телефон указан в неверном формате. Пример: +7 701 123-45-67")


def validate_birth(d: date):
    if d is None:
        raise BusinessError("Укажите дату рождения")
    if d > date.today():
        raise BusinessError("Дата рождения не может быть в будущем")
    if d.year < 1900:
        raise BusinessError("Дата рождения указана неверно")


def normalize_isbn(isbn: str) -> str:
    isbn = (isbn or "").strip().replace("-", "").replace(" ", "")
    if not re.fullmatch(r"\d{13}|\d{9}[\dXx]", isbn):
        raise BusinessError("ISBN должен содержать 10 или 13 цифр (дефисы допускаются)")
    return isbn.upper()


# ----------------------------------------------------------------- каталог (ФТ-1…ФТ-6, ФТ-17, ФТ-19, ФТ-20)
def _book_fields(data: dict) -> dict:
    title = (data.get("title") or "").strip()
    author = (data.get("author") or "").strip()
    if not title:
        raise BusinessError("Укажите название книги")
    if not author:
        raise BusinessError("Укажите автора")
    year = data.get("year")
    if year in ("", None):
        year = None
    else:
        try:
            year = int(year)
        except (TypeError, ValueError):
            raise BusinessError("Год издания должен быть числом")
        if not 1400 <= year <= date.today().year + 1:
            raise BusinessError("Год издания указан неверно")
    try:
        copies = int(data.get("copies_total", 1))
    except (TypeError, ValueError):
        raise BusinessError("Количество экземпляров должно быть числом")
    if copies < 0:
        raise BusinessError("Количество экземпляров не может быть отрицательным")
    return dict(isbn=normalize_isbn(data.get("isbn", "")), title=title, author=author,
                genre=(data.get("genre") or "").strip(), publisher=(data.get("publisher") or "").strip(),
                year=year, copies_total=copies)


def add_book(s, data: dict, user_id: int) -> Book:
    f = _book_fields(data)
    if s.scalar(select(Book.id).where(Book.isbn == f["isbn"])):  # ФТ-4
        raise BusinessError("Книга с таким ISBN уже есть в каталоге")
    b = Book(**f, copies_available=f["copies_total"])
    s.add(b)
    log(s, user_id, "Добавление книги", f"{b.title} ({b.isbn})")
    s.commit()
    return b


def update_book(s, book_id: int, data: dict, user_id: int) -> Book:
    b = s.get(Book, book_id)
    f = _book_fields(data)
    other = s.scalar(select(Book.id).where(Book.isbn == f["isbn"], Book.id != book_id))
    if other:
        raise BusinessError("Книга с таким ISBN уже есть в каталоге")
    on_hand = b.copies_total - b.copies_available
    if f["copies_total"] < on_hand:
        raise BusinessError(f"Нельзя уменьшить количество экземпляров: {on_hand} шт. сейчас у читателей")
    for k, v in f.items():
        setattr(b, k, v)
    b.copies_available = b.copies_total - on_hand
    log(s, user_id, "Изменение книги", f"{b.title} ({b.isbn})")
    s.commit()
    return b


def archive_book(s, book_id: int, user_id: int, archive: bool = True):
    """ФТ-3: списание = архивирование, физическое удаление запрещено."""
    b = s.get(Book, book_id)
    if archive and b.copies_available < b.copies_total:
        raise BusinessError("Нельзя списать книгу: часть экземпляров сейчас на руках у читателей")
    b.is_archived = archive
    log(s, user_id, "Списание книги" if archive else "Восстановление книги", f"{b.title} ({b.isbn})")
    s.commit()


def search_books(s, title="", author="", genre="", year="", isbn="", only_available=False,
                 include_archived=False) -> list[Book]:
    """ФТ-17, ФТ-19: поиск по части слова без учёта регистра, условия комбинируются."""
    q = select(Book)
    for col, val in ((Book.title, title), (Book.author, author), (Book.publisher, None)):
        if val:
            q = q.where(func.lower(col).contains(val.strip().lower()))
    if genre:
        q = q.where(Book.genre == genre)
    if str(year).strip():
        try:
            q = q.where(Book.year == int(year))
        except ValueError:
            raise BusinessError("Год в поиске должен быть числом")
    if isbn:
        q = q.where(Book.isbn.contains(isbn.replace("-", "").strip()))
    if only_available:
        q = q.where(Book.copies_available > 0)
    if not include_archived:
        q = q.where(Book.is_archived.is_(False))
    return list(s.scalars(q.order_by(Book.title)))


def genres(s) -> list[str]:
    return [g for g in s.scalars(select(Book.genre).where(Book.genre != "").distinct().order_by(Book.genre))]


# ----------------------------------------------------------------- импорт (ФТ-5)
@dataclass
class ImportResult:
    added: int = 0
    errors: list = field(default_factory=list)  # (номер строки, сообщение)


_ALIASES = {
    "isbn": "isbn", "название": "title", "title": "title", "автор": "author", "author": "author",
    "жанр": "genre", "genre": "genre", "издательство": "publisher", "publisher": "publisher",
    "год": "year", "год издания": "year", "year": "year",
    "количество": "copies_total", "кол-во": "copies_total", "количество экземпляров": "copies_total",
    "copies": "copies_total", "copies_total": "copies_total",
}


def _read_rows(path: Path):
    ext = path.suffix.lower()
    if ext == ".csv":
        text = path.read_text(encoding="utf-8-sig")
        dialect = csv.Sniffer().sniff(text[:2000], delimiters=";,\t") if text.strip() else csv.excel
        return [list(r) for r in csv.reader(text.splitlines(), dialect)]
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        return [["" if c is None else c for c in row] for row in ws.iter_rows(values_only=True)]
    raise BusinessError("Поддерживаются файлы .xlsx и .csv")


def import_books(s, path, user_id: int) -> ImportResult:
    rows = _read_rows(Path(path))
    res = ImportResult()
    if not rows:
        raise BusinessError("Файл пуст")
    header = [_ALIASES.get(str(h).strip().lower()) for h in rows[0]]
    for need in ("isbn", "title", "author"):
        if need not in header:
            raise BusinessError("В первой строке должны быть заголовки: ISBN, Название, Автор "
                                "(и необязательно Жанр, Издательство, Год, Количество)")
    seen = set()
    for n, row in enumerate(rows[1:], start=2):
        if not any(str(c).strip() for c in row):
            continue
        data = {header[i]: row[i] for i in range(min(len(header), len(row))) if header[i]}
        data.setdefault("copies_total", 1)
        if str(data.get("copies_total", "")).strip() == "":
            data["copies_total"] = 1
        if isinstance(data.get("year"), float):
            data["year"] = int(data["year"])
        if isinstance(data.get("copies_total"), float):
            data["copies_total"] = int(data["copies_total"])
        try:
            f = _book_fields(data)
            if f["isbn"] in seen or s.scalar(select(Book.id).where(Book.isbn == f["isbn"])):
                raise BusinessError("дубликат ISBN")
            seen.add(f["isbn"])
            s.add(Book(**f, copies_available=f["copies_total"]))
            res.added += 1
        except BusinessError as e:
            res.errors.append((n, str(e)))
    log(s, user_id, "Импорт каталога", f"{Path(path).name}: добавлено {res.added}, ошибок {len(res.errors)}")
    s.commit()
    return res


# ----------------------------------------------------------------- читатели (ФТ-7…ФТ-10, ФТ-18)
def _reader_fields(data: dict) -> dict:
    name = (data.get("full_name") or "").strip()
    if len(name.split()) < 2:
        raise BusinessError("Укажите ФИО полностью (фамилия и имя)")
    validate_birth(data.get("birth_date"))
    phone = (data.get("phone") or "").strip()
    validate_phone(phone)
    return dict(full_name=name, birth_date=data["birth_date"], address=(data.get("address") or "").strip(),
                phone=phone)


def add_reader(s, data: dict, user_id: int) -> Reader:
    f = _reader_fields(data)
    r = Reader(**f, ticket_number="tmp-" + uuid.uuid4().hex[:12], registered_at=date.today())
    s.add(r)
    s.flush()
    r.ticket_number = f"{r.id:06d}"  # номер билета присваивается автоматически
    log(s, user_id, "Регистрация читателя", f"{r.full_name}, билет {r.ticket_number}")
    s.commit()
    return r


def update_reader(s, reader_id: int, data: dict, user_id: int) -> Reader:
    r = s.get(Reader, reader_id)
    for k, v in _reader_fields(data).items():
        setattr(r, k, v)
    log(s, user_id, "Изменение читателя", f"{r.full_name}, билет {r.ticket_number}")
    s.commit()
    return r


def set_blocked(s, reader_id: int, blocked: bool, user_id: int):
    r = s.get(Reader, reader_id)
    r.is_blocked = blocked
    log(s, user_id, "Блокировка читателя" if blocked else "Разблокировка читателя",
        f"{r.full_name}, билет {r.ticket_number}")
    s.commit()


def search_readers(s, name="", ticket="", phone="") -> list[Reader]:
    q = select(Reader)
    if name:
        q = q.where(func.lower(Reader.full_name).contains(name.strip().lower()))
    if ticket:
        q = q.where(Reader.ticket_number.contains(ticket.strip()))
    if phone:
        digits = re.sub(r"\D", "", phone)
        q = q.where(func.replace(func.replace(func.replace(func.replace(Reader.phone, " ", ""), "-", ""), "(", ""), ")", "")
                    .contains(digits))
    return list(s.scalars(q.order_by(Reader.full_name)))


def active_loans_count(s, reader_id: int) -> int:
    return s.scalar(select(func.count(Loan.id)).where(Loan.reader_id == reader_id, Loan.returned_at.is_(None)))


# ----------------------------------------------------------------- выдача и возврат (ФТ-11…ФТ-16)
def refresh_overdue(s) -> int:
    """ФТ-15: автоматически выставляет статус «просрочена»."""
    today = date.today()
    n = 0
    for l in s.scalars(select(Loan).where(Loan.returned_at.is_(None))):
        new = "просрочена" if l.due_at < today else "выдана"
        if l.status != new:
            l.status = new
            n += 1
    s.commit()
    return n


def issue_loan(s, reader_id: int, book_id: int, days: int, user_id: int) -> Loan:
    r, b = s.get(Reader, reader_id), s.get(Book, book_id)
    if r is None or b is None:
        raise BusinessError("Выберите читателя и книгу")
    if days < 1 or days > 90:
        raise BusinessError("Срок выдачи должен быть от 1 до 90 дней")
    if r.is_blocked:  # ФТ-13
        raise BusinessError("Читатель заблокирован (например, из-за задолженности)")
    if b.is_archived:
        raise BusinessError("Книга списана и недоступна для выдачи")
    if b.copies_available <= 0:  # ФТ-13
        raise BusinessError("Нет свободных экземпляров этой книги")
    if active_loans_count(s, r.id) >= config.MAX_BOOKS:  # ФТ-13
        raise BusinessError(f"У читателя уже {config.MAX_BOOKS} книг на руках — это максимум")
    dup = s.scalar(select(Loan.id).where(Loan.reader_id == r.id, Loan.book_id == b.id, Loan.returned_at.is_(None)))
    if dup:
        raise BusinessError("Эта книга уже выдана данному читателю")
    today = date.today()
    loan = Loan(reader_id=r.id, book_id=b.id, user_id=user_id, issued_at=today,
                due_at=today + timedelta(days=days), status="выдана")
    b.copies_available -= 1  # ФТ-11: одна транзакция
    s.add(loan)
    log(s, user_id, "Выдача книги", f"{b.title} → {r.full_name} (билет {r.ticket_number}), срок {loan.due_at:%d.%m.%Y}")
    s.commit()
    return loan


def return_loan(s, loan_id: int, user_id: int) -> Loan:
    l = s.get(Loan, loan_id)
    if l.returned_at is not None:
        raise BusinessError("Эта книга уже возвращена")
    l.returned_at = date.today()  # ФТ-14
    l.status = "возвращена"
    l.book.copies_available += 1
    log(s, user_id, "Возврат книги", f"{l.book.title} ← {l.reader.full_name}")
    s.commit()
    return l


def renew_loan(s, loan_id: int, user_id: int, days: int | None = None) -> Loan:
    l = s.get(Loan, loan_id)
    if l.returned_at is not None:
        raise BusinessError("Книга уже возвращена, продлевать нечего")
    if l.renewals >= config.MAX_RENEWALS:  # ФТ-16
        raise BusinessError(f"Продлевать можно не более {config.MAX_RENEWALS} раз")
    l.due_at += timedelta(days=days or config.LOAN_DAYS)
    l.renewals += 1
    l.status = "просрочена" if l.due_at < date.today() else "выдана"
    log(s, user_id, "Продление выдачи", f"{l.book.title}, {l.reader.full_name}: до {l.due_at:%d.%m.%Y}")
    s.commit()
    return l


def list_loans(s, mode="all", text="") -> list[Loan]:
    q = select(Loan).join(Reader).join(Book).options(joinedload(Loan.reader), joinedload(Loan.book))
    if mode == "active":
        q = q.where(Loan.returned_at.is_(None))
    elif mode == "overdue":
        q = q.where(Loan.returned_at.is_(None), Loan.due_at < date.today())
    elif mode == "returned":
        q = q.where(Loan.returned_at.is_not(None))
    if text:
        t = text.strip().lower()
        q = q.where(or_(func.lower(Reader.full_name).contains(t), func.lower(Book.title).contains(t),
                        Reader.ticket_number.contains(t)))
    return list(s.scalars(q.order_by(Loan.issued_at.desc(), Loan.id.desc())).unique())


# ----------------------------------------------------------------- поставщики и заказы (ФТ-21…ФТ-23)
def save_supplier(s, supplier_id, data: dict, user_id: int) -> Supplier:
    name = (data.get("name") or "").strip()
    if not name:
        raise BusinessError("Укажите название поставщика")
    validate_phone((data.get("phone") or "").strip())
    sup = s.get(Supplier, supplier_id) if supplier_id else Supplier()
    sup.name, sup.phone, sup.address = name, (data.get("phone") or "").strip(), (data.get("address") or "").strip()
    s.add(sup)
    try:
        s.flush()
    except IntegrityError:
        s.rollback()
        raise BusinessError("Поставщик с таким названием уже есть")
    log(s, user_id, "Сохранение поставщика", name)
    s.commit()
    return sup


def create_order(s, supplier_id: int, book_id: int, quantity: int, user_id: int) -> PurchaseOrder:
    if not supplier_id or not book_id:
        raise BusinessError("Выберите поставщика и книгу")
    if quantity < 1:
        raise BusinessError("Количество должно быть не меньше 1")
    o = PurchaseOrder(supplier_id=supplier_id, book_id=book_id, quantity=quantity, ordered_at=date.today(), status="создан")
    s.add(o)
    s.flush()
    log(s, user_id, "Создание заказа", f"№{o.id}: {o.book.title} × {quantity}, {o.supplier.name}")
    s.commit()
    return o


_NEXT = {"создан": "отправлен", "отправлен": "получен"}


def advance_order(s, order_id: int, user_id: int) -> PurchaseOrder:
    o = s.get(PurchaseOrder, order_id)
    if o.status not in _NEXT:
        raise BusinessError("Заказ уже получен")
    o.status = _NEXT[o.status]
    if o.status == "получен":  # ФТ-23: книги автоматически попадают в каталог
        o.book.copies_total += o.quantity
        o.book.copies_available += o.quantity
        o.book.is_archived = False
    log(s, user_id, "Статус заказа", f"№{o.id}: {o.status}")
    s.commit()
    return o


# ----------------------------------------------------------------- пользователи (ФТ-30)
def save_user(s, user_id, data: dict, actor_id: int) -> AppUser:
    login = (data.get("login") or "").strip()
    name = (data.get("full_name") or "").strip()
    role = data.get("role")
    if role not in config.ROLES:
        raise BusinessError("Выберите роль")
    if not name:
        raise BusinessError("Укажите ФИО")
    if user_id:
        u = s.get(AppUser, user_id)
        if u.role == "admin" and role != "admin" and s.scalar(
                select(func.count(AppUser.id)).where(AppUser.role == "admin", AppUser.is_active.is_(True))) <= 1:
            raise BusinessError("Нельзя убрать роль у последнего администратора")
        u.full_name, u.role = name, role
    else:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", login):
            raise BusinessError("Логин: 3–30 символов, латиница, цифры, _ . -")
        pwd = data.get("password") or ""
        if len(pwd) < 6:
            raise BusinessError("Пароль должен быть не короче 6 символов")
        if s.scalar(select(AppUser.id).where(AppUser.login == login)):
            raise BusinessError("Пользователь с таким логином уже существует")
        u = AppUser(login=login, full_name=name, role=role, password_hash=hash_password(pwd))
        s.add(u)
    log(s, actor_id, "Сохранение пользователя", f"{u.login or login} ({role})")
    s.commit()
    return u


def reset_password(s, user_id: int, new_password: str, actor_id: int):
    if len(new_password) < 6:
        raise BusinessError("Пароль должен быть не короче 6 символов")
    u = s.get(AppUser, user_id)
    u.password_hash = hash_password(new_password)
    u.failed_attempts, u.is_locked = 0, False
    log(s, actor_id, "Сброс пароля", u.login)
    s.commit()


def unlock_user(s, user_id: int, actor_id: int):
    u = s.get(AppUser, user_id)
    u.is_locked, u.failed_attempts = False, 0
    log(s, actor_id, "Разблокировка пользователя", u.login)
    s.commit()


def set_user_active(s, user_id: int, active: bool, actor_id: int):
    u = s.get(AppUser, user_id)
    if user_id == actor_id and not active:
        raise BusinessError("Нельзя отключить собственную учётную запись")
    u.is_active = active
    log(s, actor_id, "Включение пользователя" if active else "Отключение пользователя", u.login)
    s.commit()


# ----------------------------------------------------------------- резервное копирование (ФТ-31)
def backup_database(user_id: int | None = None, directory: Path | None = None) -> Path:
    directory = directory or config.BACKUP_DIR
    directory.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if engine.dialect.name == "sqlite":
        dst = directory / f"library_{stamp}.db"
        src_path = engine.url.database
        with sqlite3.connect(src_path) as src, sqlite3.connect(dst) as out:
            src.backup(out)
        out.close()
    else:
        dst = directory / f"library_{stamp}.sql"
        if not shutil.which("pg_dump"):
            raise BusinessError("Не найдена программа pg_dump (входит в установку PostgreSQL)")
        u = engine.url
        env = {"PGPASSWORD": u.password or "", "PATH": __import__("os").environ.get("PATH", "")}
        r = subprocess.run(["pg_dump", "-h", u.host or "localhost", "-p", str(u.port or 5432), "-U", u.username,
                            "-f", str(dst), u.database], env=env, capture_output=True, text=True)
        if r.returncode:
            raise BusinessError("Ошибка pg_dump: " + r.stderr[:300])
    return dst


def auto_backup():
    """Ежедневная копия при запуске + удаление копий старше 30 дней."""
    today = datetime.now().strftime("%Y%m%d")
    existing = list(config.BACKUP_DIR.glob(f"library_{today}_*"))
    if not existing:
        backup_database()
    limit = datetime.now() - timedelta(days=config.BACKUP_KEEP_DAYS)
    for f in config.BACKUP_DIR.glob("library_*"):
        if datetime.fromtimestamp(f.stat().st_mtime) < limit:
            f.unlink(missing_ok=True)


def restore_database(path: Path):
    path = Path(path)
    if engine.dialect.name == "sqlite":
        try:
            with sqlite3.connect(path) as t:
                t.execute("SELECT count(*) FROM book")
        except sqlite3.DatabaseError:
            raise BusinessError("Выбранный файл не является резервной копией LibraryIS")
        engine.dispose()
        shutil.copyfile(path, engine.url.database)
    else:
        if not shutil.which("psql"):
            raise BusinessError("Не найдена программа psql (входит в установку PostgreSQL)")
        u = engine.url
        env = {"PGPASSWORD": u.password or "", "PATH": __import__("os").environ.get("PATH", "")}
        r = subprocess.run(["psql", "-h", u.host or "localhost", "-p", str(u.port or 5432), "-U", u.username,
                            "-d", u.database, "-f", str(path)], env=env, capture_output=True, text=True)
        if r.returncode:
            raise BusinessError("Ошибка psql: " + r.stderr[:300])
