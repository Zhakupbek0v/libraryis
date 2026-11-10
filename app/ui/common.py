"""Общие элементы интерфейса: стиль, таблицы, диалоги, помощники."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from PyQt6.QtCore import QDate, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from ..services import BusinessError

ACCENT = "#2C5AA0"

STYLE = f"""
* {{ font-family: "Segoe UI", "Noto Sans", "DejaVu Sans", Arial; font-size: 10pt; }}
QWidget {{ color: #1D2B4A; }}
QDialog, QMessageBox {{ background: #F4F6FA; }}
QCheckBox, QLabel {{ background: transparent; }}
QLineEdit {{ selection-background-color: #CFE0F8; selection-color: #101828; }}
QComboBox QAbstractItemView, QCalendarWidget QAbstractItemView {{ background: white; color: #1D2B4A;
  selection-background-color: #CFE0F8; selection-color: #101828; }}
QToolTip {{ background: #FFFFE1; color: #1D2B4A; border: 1px solid #C9D2E3; }}
QScrollBar:vertical {{ background: #EEF1F7; width: 12px; }}
QScrollBar::handle:vertical {{ background: #B9C3D6; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: #EEF1F7; height: 12px; }}
QScrollBar::handle:horizontal {{ background: #B9C3D6; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QMainWindow, QDialog {{ background: #F4F6FA; }}
QWidget#page {{ background: #F4F6FA; }}
QLabel#appTitle {{ color: white; font-size: 15pt; font-weight: 700; }}
QLabel#userChip {{ color: #DCE6F5; }}
QFrame#header {{ background: {ACCENT}; }}
QTabWidget::pane {{ border: 0; background: #F4F6FA; }}
QTabBar::tab {{ background: transparent; padding: 9px 16px; color: #46526A; border-bottom: 3px solid transparent; }}
QTabBar::tab:selected {{ color: {ACCENT}; font-weight: 600; border-bottom: 3px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {ACCENT}; }}
QGroupBox {{ background: white; border: 1px solid #DDE3EE; border-radius: 8px; margin-top: 14px; padding: 12px 10px 8px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {ACCENT}; font-weight: 600; }}
QLineEdit, QComboBox, QSpinBox, QDateEdit {{ background: white; border: 1px solid #C9D2E3; border-radius: 5px; padding: 5px 8px; min-height: 20px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus {{ border: 1px solid {ACCENT}; }}
QPushButton {{ background: white; border: 1px solid #C0CADD; border-radius: 5px; padding: 6px 14px; color: #243047; }}
QPushButton:hover {{ background: #EAF0FA; border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #9AA5B8; background: #F0F2F7; }}
QPushButton#primary {{ background: {ACCENT}; color: white; border: 1px solid {ACCENT}; font-weight: 600; }}
QPushButton#primary:hover {{ background: #244A87; }}
QPushButton#danger {{ color: #B3261E; border-color: #E3B5B1; }}
QPushButton#danger:hover {{ background: #FCEDEC; }}
QTableWidget {{ background: white; alternate-background-color: #F6F8FC; border: 1px solid #DDE3EE; border-radius: 6px;
  selection-background-color: #CFE0F8; selection-color: #101828; gridline-color: #E7ECF4; }}
QHeaderView::section {{ background: #E8EDF5; color: #2B3752; padding: 7px 8px; border: 0; border-right: 1px solid #D5DCE9; font-weight: 600; }}
QFrame#card {{ background: white; border: 1px solid #DDE3EE; border-radius: 10px; }}
QLabel#cardNum {{ font-size: 24pt; font-weight: 700; color: {ACCENT}; }}
QLabel#cardCap {{ color: #5B6780; }}
QLabel#hint {{ color: #7A869C; font-size: 9pt; }}
QLabel#h2 {{ font-size: 12pt; font-weight: 600; color: #1D2B4A; }}
QStatusBar {{ background: white; color: #5B6780; }}
"""


def apply_theme(app):
    """Всегда светлая тема: не зависит от тёмного режима Windows (иначе белый текст на белом фоне)."""
    from PyQt6.QtGui import QPalette
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)  # Qt 6.8+
    except Exception:
        pass
    app.setStyle("Fusion")
    pal = QPalette()
    ink, white, bg = QColor("#1D2B4A"), QColor("#FFFFFF"), QColor("#F4F6FA")
    for role, color in [(QPalette.ColorRole.Window, bg), (QPalette.ColorRole.WindowText, ink),
                        (QPalette.ColorRole.Base, white), (QPalette.ColorRole.AlternateBase, QColor("#F6F8FC")),
                        (QPalette.ColorRole.Text, ink), (QPalette.ColorRole.Button, white),
                        (QPalette.ColorRole.ButtonText, ink), (QPalette.ColorRole.BrightText, white),
                        (QPalette.ColorRole.Highlight, QColor("#CFE0F8")), (QPalette.ColorRole.HighlightedText, QColor("#101828")),
                        (QPalette.ColorRole.ToolTipBase, QColor("#FFFFE1")), (QPalette.ColorRole.ToolTipText, ink),
                        (QPalette.ColorRole.PlaceholderText, QColor("#8A93A6")), (QPalette.ColorRole.Link, QColor(ACCENT))]:
        pal.setColor(role, color)
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor("#9AA5B8"))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)


# ---------------------------------------------------------------- таблицы
def cv(v):
    """Значение ячейки → (текст, ключ сортировки)."""
    if isinstance(v, tuple):
        return v
    if v is None:
        return "", ""
    if isinstance(v, bool):
        return ("Да" if v else "Нет"), int(v)
    if isinstance(v, (int, float)):
        return str(v), v
    if isinstance(v, datetime):
        return v.strftime("%d.%m.%Y %H:%M"), v.isoformat()
    if isinstance(v, date):
        return v.strftime("%d.%m.%Y"), v.isoformat()
    return str(v), str(v).lower()


class SItem(QTableWidgetItem):
    """Ячейка с правильной сортировкой (числа — как числа, даты — как даты)."""

    def __init__(self, text, key):
        super().__init__(text)
        self._key = key

    def __lt__(self, other):
        try:
            return self._key < other._key
        except (TypeError, AttributeError):
            return self.text() < other.text()


def make_table(headers, widths=None):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(30)
    t.setShowGrid(False)
    t.setSortingEnabled(True)
    t.horizontalHeader().setHighlightSections(False)
    t.setWordWrap(False)
    hh = t.horizontalHeader()
    for i, w in enumerate(widths or []):
        if w:
            t.setColumnWidth(i, w)
    hh.setStretchLastSection(True)
    return t


@dataclass
class Row:
    id: int
    cells: list
    bg: str | None = None
    fg: str | None = None
    italic: bool = False


def fill_table(t: QTableWidget, rows: list[Row]):
    sort_col = t.horizontalHeader().sortIndicatorSection()
    sort_ord = t.horizontalHeader().sortIndicatorOrder()
    t.setSortingEnabled(False)
    t.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, v in enumerate(row.cells):
            text, key = cv(v)
            it = SItem(text, key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if row.bg:
                it.setBackground(QColor(row.bg))
            if row.fg:
                it.setForeground(QColor(row.fg))
            if row.italic:
                f = it.font()
                f.setItalic(True)
                it.setFont(f)
            if c == 0:
                it.setData(Qt.ItemDataRole.UserRole, row.id)
            t.setItem(r, c, it)
    t.setSortingEnabled(True)
    if t.horizontalHeader().isSortIndicatorShown():
        t.sortByColumn(sort_col, sort_ord)


def selected_id(t: QTableWidget):
    r = t.currentRow()
    if r < 0 or t.item(r, 0) is None:
        return None
    return t.item(r, 0).data(Qt.ItemDataRole.UserRole)


# ---------------------------------------------------------------- сообщения
def guard(parent, fn, *args, **kwargs):
    """Выполняет действие; ошибки показывает понятным сообщением. Возвращает (успех, результат)."""
    try:
        return True, fn(*args, **kwargs)
    except BusinessError as e:
        QMessageBox.warning(parent, "Невозможно выполнить действие", str(e))
    except OperationalError:
        QMessageBox.critical(parent, "Нет связи с базой данных",
                             "Не удаётся подключиться к базе данных. Введённые данные сохранены в окне — "
                             "проверьте соединение и повторите попытку.")
    except SQLAlchemyError as e:
        QMessageBox.critical(parent, "Ошибка базы данных", str(e)[:400])
    return False, None


def confirm(parent, text, title="Подтверждение") -> bool:
    b = QMessageBox(QMessageBox.Icon.Question, title, text, QMessageBox.StandardButton.NoButton, parent)
    yes = b.addButton("Да", QMessageBox.ButtonRole.YesRole)
    b.addButton("Нет", QMessageBox.ButtonRole.NoRole)
    b.exec()
    return b.clickedButton() is yes


def info(parent, text, title="LibraryIS"):
    QMessageBox.information(parent, title, text)


def date_edit(d: date | None = None) -> QDateEdit:
    e = QDateEdit()
    e.setCalendarPopup(True)
    e.setDisplayFormat("dd.MM.yyyy")
    d = d or date.today()
    e.setDate(QDate(d.year, d.month, d.day))
    return e


def pydate(e: QDateEdit) -> date:
    return e.date().toPyDate()


def button(text, primary=False, danger=False) -> QPushButton:
    b = QPushButton(text)
    if primary:
        b.setObjectName("primary")
    if danger:
        b.setObjectName("danger")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class Debounce:
    """Откладывает поиск на 200 мс после ввода символа, чтобы не запрашивать базу на каждую букву."""

    def __init__(self, fn):
        self.t = QTimer()
        self.t.setSingleShot(True)
        self.t.setInterval(200)
        self.t.timeout.connect(fn)

    def __call__(self, *_):
        self.t.start()


# ---------------------------------------------------------------- диалоги
class FormDialog(QDialog):
    """Базовый диалог с формой; закрывается только если сохранение прошло успешно."""

    def __init__(self, parent, title, width=460):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.form.setSpacing(10)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 14)
        lay.addLayout(self.form)
        self.bb = QDialogButtonBox()
        ok = self.bb.addButton("Сохранить", QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setObjectName("primary")
        self.bb.addButton("Отмена", QDialogButtonBox.ButtonRole.RejectRole)
        self.bb.accepted.connect(self._try_accept)
        self.bb.rejected.connect(self.reject)
        lay.addWidget(self.bb)

    def save(self):  # переопределяется
        raise NotImplementedError

    def _try_accept(self):
        ok, _ = guard(self, self.save)
        if ok:
            self.accept()


class PickerDialog(QDialog):
    """Выбор записи из списка с поиском (читатель, книга)."""

    def __init__(self, parent, title, headers, search_fn, widths=None, hint=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(780, 480)
        self.search_fn = search_fn
        lay = QVBoxLayout(self)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Начните вводить для поиска…")
        lay.addWidget(self.edit)
        self.table = make_table(headers, widths)
        lay.addWidget(self.table)
        if hint:
            h = QLabel(hint)
            h.setObjectName("hint")
            lay.addWidget(h)
        row = QHBoxLayout()
        row.addStretch()
        ok = button("Выбрать", primary=True)
        cancel = button("Отмена")
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self.deb = Debounce(self.refresh)
        self.edit.textChanged.connect(self.deb)
        ok.clicked.connect(self._ok)
        cancel.clicked.connect(self.reject)
        self.table.doubleClicked.connect(self._ok)
        self.refresh()
        self.edit.setFocus()
        self.result_id = None
        self.result_label = ""

    def refresh(self):
        fill_table(self.table, self.search_fn(self.edit.text()))

    def _ok(self, *_):
        rid = selected_id(self.table)
        if rid is None:
            return
        self.result_id = rid
        self.result_label = self.table.item(self.table.currentRow(), 1).text() if self.table.columnCount() > 1 else ""
        self.accept()


# ---------------------------------------------------------------- график
class BarChart(QWidget):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.title = title
        self.data: list[tuple[str, int]] = []
        self.setMinimumHeight(200)

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QColor("#1D2B4A"))
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSize(11)
        p.setFont(f)
        p.drawText(0, 0, w, 26, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)
        if not self.data:
            return
        f.setBold(False)
        f.setPointSize(9)
        p.setFont(f)
        top, bottom, left = 40, 28, 10
        mx = max(v for _, v in self.data) or 1
        n = len(self.data)
        slot = (w - left * 2) / n
        bw = min(slot * 0.55, 60)
        ch = h - top - bottom
        p.setPen(QPen(QColor("#E0E6F0")))
        for i in range(4):
            y = top + ch * i / 3
            p.drawLine(left, int(y), w - left, int(y))
        for i, (label, v) in enumerate(self.data):
            x = left + slot * i + (slot - bw) / 2
            bh = ch * v / mx
            p.setBrush(QColor(ACCENT))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(int(x), int(top + ch - bh), int(bw), int(bh), 4, 4)
            p.setPen(QColor("#1D2B4A"))
            p.drawText(int(x - 10), int(top + ch - bh - 20), int(bw + 20), 18, Qt.AlignmentFlag.AlignCenter, str(v))
            p.setPen(QColor("#5B6780"))
            p.drawText(int(left + slot * i), h - bottom + 4, int(slot), 20, Qt.AlignmentFlag.AlignCenter, label)


def stat_card(caption: str):
    from PyQt6.QtWidgets import QFrame
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 12, 16, 12)
    num = QLabel("0")
    num.setObjectName("cardNum")
    cap = QLabel(caption)
    cap.setObjectName("cardCap")
    lay.addWidget(num)
    lay.addWidget(cap)
    return f, num
