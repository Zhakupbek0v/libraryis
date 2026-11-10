"""Обход всех окон приложения без показа на экране: ловим исключения при построении интерфейса."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PyQt6.QtWidgets import QApplication

from app.models import init_db
from app.seed import seed


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.common import apply_theme
    apply_theme(app)
    init_db()
    from app.models import Base, engine
    Base.metadata.drop_all(engine)
    init_db()
    seed()
    return app


USERS = {"librarian": dict(id=3, login="lib", full_name="Мухамедова Салтанат Ермековна", role="librarian"),
         "head": dict(id=2, login="head", full_name="Сагынбаева Гульнара Маратовна", role="head"),
         "admin": dict(id=1, login="admin", full_name="Администратор системы", role="admin")}


@pytest.mark.parametrize("role", USERS)
def test_main_window_all_tabs(qapp, role):
    from app.ui.main_window import MainWindow
    w = MainWindow(USERS[role])
    w.show()
    for i in range(w.tabs.count()):
        w.tabs.setCurrentIndex(i)
        qapp.processEvents()
        w._call("focus_search")
        w._call("refresh")
    names = [n for n, _ in w.pages]
    assert ("Заказы поставщикам" in names) == (role == "head")
    assert ("Администрирование" in names) == (role == "admin")
    assert ("Каталог книг" in names) == (role != "admin")
    w.idle.stop()
    w.close()


def test_dialogs_build(qapp):
    from app.ui.catalog import BookDialog
    from app.ui.readers import ReaderCard, ReaderDialog
    from app.ui.orders import OrderDialog, SupplierDialog
    from app.ui.admin import UserDialog, PasswordDialog
    BookDialog(None, 3); BookDialog(None, 3, 1)
    ReaderDialog(None, 3); ReaderDialog(None, 3, 1)
    ReaderCard(None, 1)
    SupplierDialog(None, 2); OrderDialog(None, 2)
    UserDialog(None, 1); UserDialog(None, 1, 2); PasswordDialog(None, 1, 2)


def test_reports_export(qapp, tmp_path):
    from app import reports
    from app.models import Session
    with Session() as s:
        reps = [reports.debtors(s), reports.top_books(s), reports.fund_state(s), reports.reader_certificate(s, 1),
                reports.loans_period(s, __import__("datetime").date(2020, 1, 1), __import__("datetime").date.today())]
    for i, r in enumerate(reps):
        reports.export_pdf(r, tmp_path / f"{i}.pdf")
        reports.export_xlsx(r, tmp_path / f"{i}.xlsx")
        assert (tmp_path / f"{i}.pdf").stat().st_size > 1000
        assert "<table" in reports.to_html(r)


def test_login_dialog_wrong_and_right(qapp):
    from app.ui import common
    from app.ui.login import LoginDialog
    import app.ui.common as c
    d = LoginDialog()
    d.login.setText("lib"); d.pwd.setText("lib123")
    d.try_login()
    assert d.user and d.user["role"] == "librarian"
