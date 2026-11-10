from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QVBoxLayout

from .. import services as sv
from ..models import Session
from .common import button, guard


class LoginDialog(QDialog):
    def __init__(self, message=""):
        super().__init__()
        self.setWindowTitle("LibraryIS — вход")
        self.setFixedWidth(400)
        self.user = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(10)
        t = QLabel("LibraryIS")
        t.setStyleSheet("font-size: 24pt; font-weight: 700; color: #2C5AA0;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("Автоматизированная информационная система библиотеки")
        sub.setObjectName("hint")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        lay.addWidget(t)
        lay.addWidget(sub)
        if message:
            m = QLabel(message)
            m.setStyleSheet("color: #B3261E; background: #FCEDEC; padding: 6px; border-radius: 5px;")
            m.setWordWrap(True)
            lay.addWidget(m)
        form = QFormLayout()
        form.setSpacing(10)
        self.login = QLineEdit()
        self.login.setPlaceholderText("Логин")
        self.pwd = QLineEdit()
        self.pwd.setPlaceholderText("Пароль")
        self.pwd.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Логин", self.login)
        form.addRow("Пароль", self.pwd)
        lay.addLayout(form)
        self.btn = button("Войти", primary=True)
        self.btn.setDefault(True)
        lay.addWidget(self.btn)
        demo = QLabel("Учётные записи для демонстрации:\nlib / lib123 — библиотекарь\nhead / head123 — заведующий\nadmin / admin123 — администратор")
        demo.setObjectName("hint")
        lay.addWidget(demo)
        self.btn.clicked.connect(self.try_login)
        self.pwd.returnPressed.connect(self.try_login)
        self.login.returnPressed.connect(self.pwd.setFocus)
        self.login.setFocus()

    def try_login(self):
        def do():
            with Session() as s:
                u = sv.authenticate(s, self.login.text(), self.pwd.text())
                return dict(id=u.id, login=u.login, full_name=u.full_name, role=u.role)
        ok, user = guard(self, do)
        if ok:
            self.user = user
            self.accept()
        else:
            self.pwd.clear()
            self.pwd.setFocus()
