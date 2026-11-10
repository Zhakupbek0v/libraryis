"""Точка входа LibraryIS."""
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.models import init_db
from app.seed import seed
from app.services import auto_backup
from app.ui.common import apply_theme
from app.ui.login import LoginDialog
from app.ui.main_window import EXIT_RELOGIN, MainWindow


def main():
    app = QApplication(sys.argv)
    apply_theme(app)
    try:
        init_db()
        seed()          # при первом запуске создаёт пользователей и демонстрационные данные
        auto_backup()   # ежедневная резервная копия
    except Exception as e:  # нет связи с БД и т.п.
        QMessageBox.critical(None, "LibraryIS", f"Не удалось подключиться к базе данных:\n{e}\n\nПроверьте настройки в config.ini.")
        return 1
    message = ""
    while True:
        dlg = LoginDialog(message)
        if not dlg.exec():
            return 0
        win = MainWindow(dlg.user)
        win.show()
        code = app.exec()
        message = getattr(win, "relogin_reason", "")
        win.close()
        win.deleteLater()
        if code != EXIT_RELOGIN:
            return 0


if __name__ == "__main__":
    sys.exit(main())
