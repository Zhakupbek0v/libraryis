"""Вкладка «Администрирование» (ФТ-30…ФТ-32)."""
from datetime import datetime

from PyQt6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QTabWidget, QVBoxLayout, QWidget)
from sqlalchemy import select

from .. import config
from .. import services as sv
from ..models import AppUser, AuditLog, Session
from .common import (Debounce, FormDialog, Row, button, confirm, fill_table, guard, info, make_table, selected_id)


class UserDialog(FormDialog):
    def __init__(self, parent, actor_id, user_id=None):
        super().__init__(parent, "Пользователь системы")
        self.actor_id, self.user_id = actor_id, user_id
        self.login, self.name, self.pwd = QLineEdit(), QLineEdit(), QLineEdit()
        self.role = QComboBox()
        for k, v in config.ROLES.items():
            self.role.addItem(v, k)
        if user_id:
            with Session() as s:
                u = s.get(AppUser, user_id)
                self.login.setText(u.login)
                self.login.setEnabled(False)
                self.name.setText(u.full_name)
                self.role.setCurrentIndex(self.role.findData(u.role))
        else:
            self.pwd.setEchoMode(QLineEdit.EchoMode.Password)
            self.pwd.setPlaceholderText("не короче 6 символов")
        self.form.addRow("Логин *", self.login)
        self.form.addRow("ФИО *", self.name)
        self.form.addRow("Роль *", self.role)
        if not user_id:
            self.form.addRow("Пароль *", self.pwd)

    def save(self):
        with Session() as s:
            sv.save_user(s, self.user_id, dict(login=self.login.text(), full_name=self.name.text(), role=self.role.currentData(),
                                               password=self.pwd.text()), self.actor_id)


class PasswordDialog(FormDialog):
    def __init__(self, parent, actor_id, user_id):
        super().__init__(parent, "Сброс пароля", 380)
        self.actor_id, self.user_id = actor_id, user_id
        self.pwd = QLineEdit()
        self.pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.form.addRow("Новый пароль", self.pwd)

    def save(self):
        with Session() as s:
            sv.reset_password(s, self.user_id, self.pwd.text(), self.actor_id)


class AdminTab(QWidget):
    def __init__(self, user):
        super().__init__()
        self.setObjectName("page")
        self.user = user
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # --- пользователи
        w = QWidget()
        v = QVBoxLayout(w)
        self.users = make_table(["Логин", "ФИО", "Роль", "Состояние"], [130, 290, 140])
        v.addWidget(self.users)
        bar = QHBoxLayout()
        bar.addStretch()
        self.b_toggle, self.b_unlock = button("Отключить", danger=True), button("Разблокировать")
        b_pwd, b_edit, b_add = button("Сбросить пароль…"), button("Изменить"), button("Добавить (Ctrl+N)", primary=True)
        for b in (self.b_toggle, self.b_unlock, b_pwd, b_edit, b_add):
            bar.addWidget(b)
        v.addLayout(bar)
        tabs.addTab(w, "Пользователи")
        b_add.clicked.connect(self.new_item)
        b_edit.clicked.connect(self.edit_user)
        b_pwd.clicked.connect(self.reset_pwd)
        self.b_unlock.clicked.connect(self.unlock)
        self.b_toggle.clicked.connect(self.toggle)
        self.users.itemSelectionChanged.connect(self._sel)

        # --- журнал
        w = QWidget()
        v = QVBoxLayout(w)
        self.f_log = QLineEdit()
        self.f_log.setPlaceholderText("Поиск по журналу: действие, описание или пользователь (Ctrl+F)")
        v.addWidget(self.f_log)
        self.log = make_table(["Дата и время", "Пользователь", "Действие", "Описание"], [140, 190, 190])
        v.addWidget(self.log)
        self.log_cnt = QLabel()
        self.log_cnt.setObjectName("hint")
        v.addWidget(self.log_cnt)
        tabs.addTab(w, "Журнал действий")
        self.deb = Debounce(self.load_log)
        self.f_log.textChanged.connect(self.deb)

        # --- резервные копии
        w = QWidget()
        v = QVBoxLayout(w)
        t = QLabel("Резервные копии базы данных создаются автоматически раз в сутки при первом запуске программы; "
                   f"копии старше {config.BACKUP_KEEP_DAYS} дней удаляются.\nПапка: {config.BACKUP_DIR}")
        t.setWordWrap(True)
        v.addWidget(t)
        self.backups = make_table(["Файл", "Создан", "Размер"], [280, 150])
        v.addWidget(self.backups)
        bar = QHBoxLayout()
        bar.addStretch()
        b_rest, b_file, b_new = button("Восстановить из выбранной", danger=True), button("Восстановить из файла…"), button("Создать копию сейчас", primary=True)
        for b in (b_rest, b_file, b_new):
            bar.addWidget(b)
        v.addLayout(bar)
        tabs.addTab(w, "Резервное копирование")
        b_new.clicked.connect(self.make_backup)
        b_rest.clicked.connect(self.restore_selected)
        b_file.clicked.connect(self.restore_file)
        self.refresh()

    def focus_search(self):
        self.f_log.setFocus()

    def refresh(self):
        self.load_users()
        self.load_log()
        self.load_backups()

    # пользователи
    def load_users(self):
        with Session() as s:
            rows = []
            for u in s.scalars(select(AppUser).order_by(AppUser.login)):
                state = "отключён" if not u.is_active else ("заблокирован" if u.is_locked else "активен")
                rows.append(Row(u.id, [u.login, u.full_name, config.ROLES.get(u.role, u.role), state],
                                fg=None if state == "активен" else "#B3261E"))
            fill_table(self.users, rows)
        self._sel()

    def _sel(self):
        uid = selected_id(self.users)
        on = uid is not None
        self.b_toggle.setEnabled(on)
        self.b_unlock.setEnabled(on)
        if on:
            st = self.users.item(self.users.currentRow(), 3).text()
            self.b_toggle.setText("Включить" if st == "отключён" else "Отключить")
            self.b_unlock.setEnabled(st == "заблокирован")

    def new_item(self):
        if UserDialog(self, self.user["id"]).exec():
            self.load_users()

    def edit_user(self):
        uid = selected_id(self.users)
        if uid and UserDialog(self, self.user["id"], uid).exec():
            self.load_users()

    def reset_pwd(self):
        uid = selected_id(self.users)
        if uid and PasswordDialog(self, self.user["id"], uid).exec():
            info(self, "Пароль изменён, блокировка снята.")
            self.load_users()

    def unlock(self):
        uid = selected_id(self.users)

        def do():
            with Session() as s:
                sv.unlock_user(s, uid, self.user["id"])
        if uid and guard(self, do)[0]:
            self.load_users()

    def toggle(self):
        uid = selected_id(self.users)
        active = self.users.item(self.users.currentRow(), 3).text() == "отключён"

        def do():
            with Session() as s:
                sv.set_user_active(s, uid, active, self.user["id"])
        if uid and guard(self, do)[0]:
            self.load_users()

    # журнал
    def load_log(self):
        t = self.f_log.text().strip().lower()
        with Session() as s:
            q = select(AuditLog).order_by(AuditLog.id.desc()).limit(1500)
            rows = []
            for a in s.scalars(q):
                who = a.user.full_name if a.user else "система"
                if t and t not in f"{a.action} {a.description} {who}".lower():
                    continue
                rows.append(Row(a.id, [a.created_at, who, a.action, a.description]))
            fill_table(self.log, rows[:500])
            self.log_cnt.setText(f"Показано записей: {min(len(rows), 500)} (последние события вверху)")

    # резервные копии
    def load_backups(self):
        files = sorted(config.BACKUP_DIR.glob("library_*"), reverse=True)
        fill_table(self.backups, [Row(i, [f.name, datetime.fromtimestamp(f.stat().st_mtime), f"{f.stat().st_size // 1024} КБ"])
                                  for i, f in enumerate(files)])
        self._files = files

    def make_backup(self):
        ok, path = guard(self, sv.backup_database)
        if ok:
            with Session() as s:
                sv.log(s, self.user["id"], "Резервная копия", path.name)
                s.commit()
            info(self, f"Резервная копия создана:\n{path.name}")
            self.refresh()

    def _restore(self, path):
        if not confirm(self, "Текущие данные будут ЗАМЕНЕНЫ данными из копии.\nПрограмма перезапустится. Продолжить?", "Восстановление"):
            return
        if guard(self, sv.restore_database, path)[0]:
            info(self, "Данные восстановлены. Войдите в систему заново.")
            self.window().relogin()

    def restore_selected(self):
        i = selected_id(self.backups)
        if i is not None:
            self._restore(self._files[i])

    def restore_file(self):
        p, _ = QFileDialog.getOpenFileName(self, "Файл резервной копии", str(config.BACKUP_DIR), "Копии (*.db *.sql)")
        if p:
            self._restore(p)
