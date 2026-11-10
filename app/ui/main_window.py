"""Главное окно: вкладки по ролям (раздел 4.8 ТЗ), горячие клавиши, автовыход."""
from datetime import date

from PyQt6.QtCore import QEvent, QObject, QTimer, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QTabWidget, QVBoxLayout,
                             QWidget)

from .. import config
from ..models import Session
from .. import services as sv
from .admin import AdminTab
from .catalog import CatalogTab
from .common import button
from .dashboard import DashboardTab
from .loans import LoansTab
from .orders import OrdersTab
from .readers import ReadersTab
from .reports_tab import ReportsTab

EXIT_RELOGIN = 1000


class _Activity(QObject):
    def __init__(self, cb):
        super().__init__()
        self.cb = cb

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress, QEvent.Type.MouseMove):
            self.cb()
        return False


class MainWindow(QMainWindow):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.reason = ""
        self.setWindowTitle("LibraryIS — автоматизированная информационная система библиотеки")
        self.resize(1240, 760)
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QFrame()
        head.setObjectName("header")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(18, 10, 18, 10)
        t = QLabel("📚  LibraryIS")
        t.setObjectName("appTitle")
        chip = QLabel(f"{user['full_name']}  ·  {config.ROLES[user['role']]}")
        chip.setObjectName("userChip")
        out = button("Выйти")
        hl.addWidget(t)
        hl.addStretch()
        hl.addWidget(chip)
        hl.addWidget(out)
        v.addWidget(head)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)

        role = user["role"]
        self.pages = [("Главная", DashboardTab(user))]
        if role in ("librarian", "head"):
            self.pages += [("Каталог книг", CatalogTab(user)), ("Читатели", ReadersTab(user)),
                           ("Выдача и возврат", LoansTab(user))]
        if role == "head":
            self.pages.append(("Заказы поставщикам", OrdersTab(user)))
        if role in ("librarian", "head"):
            self.pages.append(("Отчёты", ReportsTab(user)))
        if role == "admin":
            self.pages.append(("Администрирование", AdminTab(user)))
        for name, w in self.pages:
            self.tabs.addTab(w, name)
        self.tabs.currentChanged.connect(lambda i: self.tabs.widget(i).refresh())
        out.clicked.connect(self.relogin)
        self.statusBar().showMessage(f"Сегодня {date.today():%d.%m.%Y}   ·   Ctrl+F — поиск   ·   Ctrl+N — новая запись   ·   F5 — обновить")

        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self._call("focus_search"))
        QShortcut(QKeySequence("Ctrl+N"), self, activated=lambda: self._call("new_item"))
        QShortcut(QKeySequence("F5"), self, activated=lambda: self._call("refresh"))

        # автоматический выход при бездействии (по умолчанию 30 минут)
        self.idle = QTimer(self)
        self.idle.setSingleShot(True)
        self.idle.setInterval(config.IDLE_MINUTES * 60 * 1000)
        self.idle.timeout.connect(self._idle_logout)
        self.idle.start()
        self._filter = _Activity(lambda: self.idle.start())
        QApplication.instance().installEventFilter(self._filter)

    def _call(self, name):
        w = self.tabs.currentWidget()
        if hasattr(w, name):
            getattr(w, name)()

    def _idle_logout(self):
        self.reason = f"Выход выполнен автоматически: нет активности более {config.IDLE_MINUTES} мин."
        self.relogin()

    def relogin(self):
        QApplication.instance().removeEventFilter(self._filter)
        self.idle.stop()
        with Session() as s:
            sv.log(s, self.user["id"], "Выход из системы", self.user["login"])
            s.commit()
        self.relogin_reason = self.reason
        QApplication.instance().exit(EXIT_RELOGIN)
