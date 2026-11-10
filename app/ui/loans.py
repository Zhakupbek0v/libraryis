"""Вкладка «Выдача и возврат» (ФТ-11…ФТ-16)."""
from PyQt6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget

from .. import config
from .. import services as sv
from ..models import Reader, Session, Book
from .common import Debounce, PickerDialog, Row, button, confirm, fill_table, guard, info, make_table, selected_id


def pick_reader(parent):
    def search(text):
        with Session() as s:
            rs = sv.search_readers(s, text, "", "") if not text.strip().isdigit() else \
                (sv.search_readers(s, "", text.strip(), ""))
            rs = rs[:200]
            return [Row(r.id, [r.ticket_number, r.full_name, r.phone, "заблокирован" if r.is_blocked else "активен"],
                        fg="#B3261E" if r.is_blocked else None) for r in rs]
    d = PickerDialog(parent, "Выбор читателя", ["Билет", "ФИО", "Телефон", "Статус"], search, [70, 260, 150],
                     "Поиск по ФИО или номеру билета")
    return (d.result_id, d.result_label) if d.exec() else (None, "")


def pick_book(parent, only_available=False):
    def search(text):
        with Session() as s:
            bs = sv.search_books(s, title=text, only_available=only_available)
            if not bs and text:
                bs = sv.search_books(s, author=text, only_available=only_available)
            return [Row(b.id, [b.title, b.author, b.year, b.copies_available],
                        bg="#FDECEA" if b.copies_available == 0 else None) for b in bs[:200]]
    d = PickerDialog(parent, "Выбор книги", ["Название", "Автор", "Год", "В наличии"], search, [320, 200, 60],
                     "Поиск по названию или автору. Красным отмечены книги без свободных экземпляров.")
    return (d.result_id, d.result_label) if d.exec() else (None, "")


class LoansTab(QWidget):
    def __init__(self, user):
        super().__init__()
        self.setObjectName("page")
        self.user = user
        self.reader_id = self.book_id = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)

        box = QGroupBox("Оформление выдачи")
        bl = QHBoxLayout(box)
        self.reader_lbl, self.book_lbl = QLabel("читатель не выбран"), QLabel("книга не выбрана")
        for l in (self.reader_lbl, self.book_lbl):
            l.setMinimumWidth(190)
            l.setStyleSheet("color:#5B6780")
        pr, pb = button("Выбрать читателя…"), button("Выбрать книгу…")
        self.days = QSpinBox()
        self.days.setRange(1, 90)
        self.days.setValue(config.LOAN_DAYS)
        self.days.setSuffix(" дн.")
        self.issue_btn = button("Выдать книгу", primary=True)
        for w in (pr, self.reader_lbl, pb, self.book_lbl, QLabel("Срок:"), self.days):
            bl.addWidget(w)
        bl.addStretch()
        bl.addWidget(self.issue_btn)
        lay.addWidget(box)
        self.reader_info = QLabel("")
        self.reader_info.setObjectName("hint")
        lay.addWidget(self.reader_info)

        top = QHBoxLayout()
        self.mode = QComboBox()
        for label, key in [("Все выдачи", "all"), ("На руках", "active"), ("Просроченные", "overdue"), ("Возвращённые", "returned")]:
            self.mode.addItem(label, key)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по читателю, книге или номеру билета (Ctrl+F)")
        top.addWidget(self.mode)
        top.addWidget(self.search, 1)
        lay.addLayout(top)
        self.table = make_table(["Читатель", "Билет", "Книга", "Выдана", "Срок возврата", "Возвращена", "Продлений", "Статус"],
                                [210, 85, 270, 100, 135, 125, 105])
        lay.addWidget(self.table)
        bar = QHBoxLayout()
        self.count = QLabel()
        self.count.setObjectName("hint")
        self.ret, self.renew = button("Принять возврат", primary=True), button("Продлить срок")
        bar.addWidget(self.count)
        bar.addStretch()
        bar.addWidget(self.renew)
        bar.addWidget(self.ret)
        lay.addLayout(bar)

        pr.clicked.connect(self.choose_reader)
        pb.clicked.connect(self.choose_book)
        self.issue_btn.clicked.connect(self.issue)
        self.ret.clicked.connect(self.do_return)
        self.renew.clicked.connect(self.do_renew)
        self.mode.currentIndexChanged.connect(self.refresh)
        self.deb = Debounce(self.refresh)
        self.search.textChanged.connect(self.deb)
        self.table.itemSelectionChanged.connect(self._sel)
        self.refresh()

    def focus_search(self):
        self.search.setFocus()

    def new_item(self):
        self.choose_reader()

    def choose_reader(self):
        rid, label = pick_reader(self)
        if rid:
            self.reader_id = rid
            self.reader_lbl.setText(label)
            self.reader_lbl.setStyleSheet("color:#1D2B4A;font-weight:600")
            with Session() as s:
                r = s.get(Reader, rid)
                n = sv.active_loans_count(s, rid)
            msg = f"Читатель: билет {r.ticket_number} · на руках {n} из {config.MAX_BOOKS} книг"
            if r.is_blocked:
                msg += " · ЗАБЛОКИРОВАН — выдача невозможна"
            self.reader_info.setText(msg)

    def choose_book(self):
        bid, label = pick_book(self)
        if bid:
            self.book_id = bid
            self.book_lbl.setText(label)
            self.book_lbl.setStyleSheet("color:#1D2B4A;font-weight:600")

    def refresh(self):
        def load():
            with Session() as s:
                sv.refresh_overdue(s)
                return sv.list_loans(s, self.mode.currentData(), self.search.text())
        ok, loans = guard(self, load)
        if not ok:
            return
        rows = []
        for l in loans:
            bg = "#FDECEA" if l.status == "просрочена" else None
            fg = "#8A93A6" if l.returned_at else None
            rows.append(Row(l.id, [l.reader.full_name, l.reader.ticket_number, l.book.title, l.issued_at, l.due_at,
                                   l.returned_at, l.renewals, l.status], bg=bg, fg=fg))
        fill_table(self.table, rows)
        active = sum(1 for l in loans if l.returned_at is None)
        self.count.setText(f"Записей: {len(loans)} · из них на руках: {active}")
        self._sel()

    def _sel(self):
        lid = selected_id(self.table)
        on = lid is not None and not self.table.item(self.table.currentRow(), 5).text()
        self.ret.setEnabled(on)
        self.renew.setEnabled(on)

    def issue(self):
        if not (self.reader_id and self.book_id):
            info(self, "Сначала выберите читателя и книгу.")
            return

        def do():
            with Session() as s:
                return sv.issue_loan(s, self.reader_id, self.book_id, self.days.value(), self.user["id"])
        ok, loan = guard(self, do)
        if ok:
            info(self, f"Книга выдана. Срок возврата: {loan.due_at:%d.%m.%Y}.", "Выдача оформлена")
            self.book_id = None
            self.book_lbl.setText("книга не выбрана")
            self.book_lbl.setStyleSheet("color:#5B6780")
            self.choose_reader_refresh()
            self.refresh()

    def choose_reader_refresh(self):
        if self.reader_id:
            with Session() as s:
                r = s.get(Reader, self.reader_id)
                n = sv.active_loans_count(s, self.reader_id)
            self.reader_info.setText(f"Читатель: билет {r.ticket_number} · на руках {n} из {config.MAX_BOOKS} книг")

    def do_return(self):
        lid = selected_id(self.table)
        if not lid or not confirm(self, "Принять возврат выбранной книги?"):
            return

        def do():
            with Session() as s:
                return sv.return_loan(s, lid, self.user["id"])
        if guard(self, do)[0]:
            self.choose_reader_refresh()
            self.refresh()

    def do_renew(self):
        lid = selected_id(self.table)
        if not lid:
            return

        def do():
            with Session() as s:
                return sv.renew_loan(s, lid, self.user["id"])
        ok, loan = guard(self, do)
        if ok:
            info(self, f"Срок продлён до {loan.due_at:%d.%m.%Y}. Продлений: {loan.renewals} из {config.MAX_RENEWALS}.")
            self.refresh()
