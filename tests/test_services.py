"""Тест-кейсы к требованиям ТЗ (раздел 4.13). Запуск: python -m pytest"""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app import services as sv
from app.models import AppUser, Book, Loan, Reader

BOOK = dict(isbn="978-9965-00-001-1", title="Тестовая книга", author="Автор Тестов", genre="Роман", year=2020, copies_total=2)
READER = dict(full_name="Иван Иванов", birth_date=date(2000, 1, 1), phone="+7 701 123-45-67", address="Астана")


def uid(s):
    return s.scalar(select(AppUser.id))


def test_ft4_duplicate_isbn_rejected(s):          # ФТ-4
    sv.add_book(s, BOOK, uid(s))
    with pytest.raises(sv.BusinessError, match="ISBN"):
        sv.add_book(s, dict(BOOK, title="Другая"), uid(s))


def test_isbn_format_validated(s):
    with pytest.raises(sv.BusinessError):
        sv.add_book(s, dict(BOOK, isbn="123"), uid(s))


def test_ft7_ticket_number_auto(s):                # ФТ-7
    r = sv.add_reader(s, READER, uid(s))
    assert r.ticket_number == f"{r.id:06d}"


def test_ft10_phone_and_birth_validation(s):      # ФТ-10
    with pytest.raises(sv.BusinessError):
        sv.add_reader(s, dict(READER, phone="abc"), uid(s))
    with pytest.raises(sv.BusinessError):
        sv.add_reader(s, dict(READER, birth_date=date.today() + timedelta(days=1)), uid(s))


def test_ft11_issue_decrements_available(s):      # ФТ-11
    b, r = sv.add_book(s, BOOK, uid(s)), sv.add_reader(s, READER, uid(s))
    sv.issue_loan(s, r.id, b.id, 14, uid(s))
    assert s.get(Book, b.id).copies_available == 1


def test_ft13_no_free_copies(s):                  # ФТ-13
    b = sv.add_book(s, dict(BOOK, copies_total=1), uid(s))
    r1, r2 = sv.add_reader(s, READER, uid(s)), sv.add_reader(s, dict(READER, full_name="Пётр Петров"), uid(s))
    sv.issue_loan(s, r1.id, b.id, 14, uid(s))
    with pytest.raises(sv.BusinessError, match="Нет свободных экземпляров"):
        sv.issue_loan(s, r2.id, b.id, 14, uid(s))


def test_ft13_blocked_reader(s):                  # ФТ-13
    b, r = sv.add_book(s, BOOK, uid(s)), sv.add_reader(s, READER, uid(s))
    sv.set_blocked(s, r.id, True, uid(s))
    with pytest.raises(sv.BusinessError, match="заблокирован"):
        sv.issue_loan(s, r.id, b.id, 14, uid(s))


def test_ft13_limit_five_books(s):                # ФТ-13
    r = sv.add_reader(s, READER, uid(s))
    for i in range(5):
        b = sv.add_book(s, dict(BOOK, isbn=f"97899650000{i}1", title=f"Книга {i}"), uid(s))
        sv.issue_loan(s, r.id, b.id, 14, uid(s))
    extra = sv.add_book(s, dict(BOOK, isbn="9789965000099", title="Лишняя"), uid(s))
    with pytest.raises(sv.BusinessError, match="максимум"):
        sv.issue_loan(s, r.id, extra.id, 14, uid(s))


def test_ft14_return_increments_available(s):    # ФТ-14
    b, r = sv.add_book(s, BOOK, uid(s)), sv.add_reader(s, READER, uid(s))
    l = sv.issue_loan(s, r.id, b.id, 14, uid(s))
    sv.return_loan(s, l.id, uid(s))
    assert s.get(Book, b.id).copies_available == 2
    assert s.get(Loan, l.id).returned_at == date.today()
    with pytest.raises(sv.BusinessError):
        sv.return_loan(s, l.id, uid(s))


def test_ft15_overdue_status(s):                  # ФТ-15
    b, r = sv.add_book(s, BOOK, uid(s)), sv.add_reader(s, READER, uid(s))
    l = sv.issue_loan(s, r.id, b.id, 14, uid(s))
    l.due_at = date.today() - timedelta(days=3)
    s.commit()
    sv.refresh_overdue(s)
    assert s.get(Loan, l.id).status == "просрочена"


def test_ft16_max_two_renewals(s):                # ФТ-16
    b, r = sv.add_book(s, BOOK, uid(s)), sv.add_reader(s, READER, uid(s))
    l = sv.issue_loan(s, r.id, b.id, 14, uid(s))
    sv.renew_loan(s, l.id, uid(s))
    sv.renew_loan(s, l.id, uid(s))
    with pytest.raises(sv.BusinessError, match="не более"):
        sv.renew_loan(s, l.id, uid(s))


def test_ft17_19_search_combined(s):              # ФТ-17, ФТ-19
    sv.add_book(s, BOOK, uid(s))
    sv.add_book(s, dict(BOOK, isbn="9789965000022", title="Война и мир", author="Лев Толстой", genre="Роман", year=2019), uid(s))
    assert len(sv.search_books(s, title="ВОЙНА")) == 1
    assert len(sv.search_books(s, genre="Роман", year="2019")) == 1
    assert len(sv.search_books(s, author="толст", year="2020")) == 0


def test_ft3_archive_not_delete(s):               # ФТ-3
    b, r = sv.add_book(s, BOOK, uid(s)), sv.add_reader(s, READER, uid(s))
    l = sv.issue_loan(s, r.id, b.id, 14, uid(s))
    with pytest.raises(sv.BusinessError):
        sv.archive_book(s, b.id, uid(s))
    sv.return_loan(s, l.id, uid(s))
    sv.archive_book(s, b.id, uid(s))
    assert s.get(Book, b.id) is not None and s.get(Book, b.id).is_archived
    assert sv.search_books(s) == []


def test_edit_copies_cannot_go_below_on_hand(s):
    b, r = sv.add_book(s, BOOK, uid(s)), sv.add_reader(s, READER, uid(s))
    sv.issue_loan(s, r.id, b.id, 14, uid(s))
    sv.issue_loan(s, sv.add_reader(s, dict(READER, full_name="Пётр Петров"), uid(s)).id, b.id, 14, uid(s))
    with pytest.raises(sv.BusinessError):
        sv.update_book(s, b.id, dict(BOOK, copies_total=1), uid(s))


def test_ft23_receive_order_adds_copies(s):       # ФТ-21…ФТ-23
    b = sv.add_book(s, BOOK, uid(s))
    sup = sv.save_supplier(s, None, dict(name="Книжный мир"), uid(s))
    o = sv.create_order(s, sup.id, b.id, 5, uid(s))
    sv.advance_order(s, o.id, uid(s))
    sv.advance_order(s, o.id, uid(s))
    assert s.get(Book, b.id).copies_total == 7 and s.get(Book, b.id).copies_available == 7
    with pytest.raises(sv.BusinessError):
        sv.advance_order(s, o.id, uid(s))


def test_login_lock_after_5_failures(s):          # безопасность
    for _ in range(4):
        with pytest.raises(sv.BusinessError, match="Осталось"):
            sv.authenticate(s, "lib", "wrong")
    with pytest.raises(sv.BusinessError, match="заблокирована"):
        sv.authenticate(s, "lib", "wrong")
    with pytest.raises(sv.BusinessError, match="заблокирована"):
        sv.authenticate(s, "lib", "secret1")


def test_login_ok_and_audit(s):                   # ФТ-32
    u = sv.authenticate(s, "lib", "secret1")
    assert u.role == "librarian"
    from app.models import AuditLog
    assert s.scalar(select(AuditLog).where(AuditLog.action == "Вход в систему")) is not None


def test_ft5_import_csv(s, tmp_path):             # ФТ-5
    f = tmp_path / "b.csv"
    f.write_text("ISBN;Название;Автор;Жанр;Год;Количество\n9789965000101;А;Автор А;Роман;2020;3\n"
                 "9789965000101;Дубль;Автор Б;Роман;2020;1\nплохой;Б;Автор;;;\n", encoding="utf-8-sig")
    res = sv.import_books(s, f, uid(s))
    assert res.added == 1 and len(res.errors) == 2


def test_ft30_user_management(s):
    admin = sv.save_user(s, None, dict(login="boss", password="abcdef", full_name="Босс", role="admin"), uid(s))
    with pytest.raises(sv.BusinessError):
        sv.save_user(s, None, dict(login="boss", password="abcdef", full_name="Дубль", role="head"), uid(s))
    with pytest.raises(sv.BusinessError, match="последнего"):
        sv.save_user(s, admin.id, dict(full_name="Босс", role="head"), uid(s))


def test_ft31_backup_restore(s, tmp_path):        # ФТ-31
    sv.add_book(s, BOOK, uid(s))
    path = sv.backup_database(directory=tmp_path)
    assert path.exists()
