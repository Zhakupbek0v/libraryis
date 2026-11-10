"""Вкладка «Читатели» и карточка читателя (ФТ-7…ФТ-10, ФТ-18, ФТ-24)."""
from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget)
from sqlalchemy import func, select

from .. import reports
from .. import services as sv
from ..models import Loan, Reader, Session
from .common import (Debounce, FormDialog, Row, button, confirm, date_edit, fill_table, guard, info, make_table,
                     pydate, selected_id)
from .reports_tab import print_report


class ReaderDialog(FormDialog):
    def __init__(self, parent, user_id, reader_id=None):
        super().__init__(parent, "Редактирование читателя" if reader_id else "Новый читатель")
        self.user_id, self.reader_id = user_id, reader_id
        self.name, self.phone, self.address = QLineEdit(), QLineEdit(), QLineEdit()
        self.name.setPlaceholderText("Фамилия Имя Отчество")
        self.phone.setPlaceholderText("+7 701 123-45-67")
        self.birth = date_edit(date(2000, 1, 1))
        if reader_id:
            with Session() as s:
                r = s.get(Reader, reader_id)
                self.name.setText(r.full_name)
                self.phone.setText(r.phone)
                self.address.setText(r.address)
                self.birth = date_edit(r.birth_date)
        else:
            note = QLabel("Номер читательского билета будет присвоен автоматически.")
            note.setObjectName("hint")
        for label, w in [("ФИО *", self.name), ("Дата рождения *", self.birth), ("Телефон", self.phone), ("Адрес", self.address)]:
            self.form.addRow(label, w)
        if not reader_id:
            self.form.addRow("", note)

    def save(self):
        data = dict(full_name=self.name.text(), birth_date=pydate(self.birth), phone=self.phone.text(), address=self.address.text())
        with Session() as s:
            if self.reader_id:
                sv.update_reader(s, self.reader_id, data, self.user_id)
            else:
                sv.add_reader(s, data, self.user_id)


class ReaderCard(QDialog):
    """ФТ-9: карточка читателя — данные, книги на руках, история выдач."""

    def __init__(self, parent, reader_id):
        super().__init__(parent)
        self.reader_id = reader_id
        self.setWindowTitle("Карточка читателя")
        self.resize(860, 560)
        lay = QVBoxLayout(self)
        with Session() as s:
            r = s.get(Reader, reader_id)
            loans = list(s.scalars(select(Loan).where(Loan.reader_id == reader_id).order_by(Loan.issued_at.desc())))
            on_hand = [l for l in loans if l.returned_at is None]
            head = QLabel(f"<span style='font-size:15pt;font-weight:600'>{r.full_name}</span><br>"
                          f"Билет № <b>{r.ticket_number}</b> · {r.birth_date:%d.%m.%Y} г.р. · {r.phone or 'телефон не указан'}<br>"
                          f"{r.address or 'адрес не указан'}<br>Зарегистрирован: {r.registered_at:%d.%m.%Y} · "
                          f"Статус: <b style='color:{'#B3261E' if r.is_blocked else '#1B7F3B'}'>{'заблокирован' if r.is_blocked else 'активен'}</b>")
            lay.addWidget(head)
            h1 = QLabel(f"Книги на руках ({len(on_hand)})")
            h1.setObjectName("h2")
            lay.addWidget(h1)
            t1 = make_table(["Книга", "Автор", "Выдана", "Срок возврата", "Продлений", "Статус"], [260, 170, 90, 110, 80])
            fill_table(t1, [Row(l.id, [l.book.title, l.book.author, l.issued_at, l.due_at, l.renewals, l.status],
                                bg="#FDECEA" if l.status == "просрочена" else None) for l in on_hand])
            t1.setMaximumHeight(170)
            lay.addWidget(t1)
            h2 = QLabel(f"История выдач ({len(loans)})")
            h2.setObjectName("h2")
            lay.addWidget(h2)
            t2 = make_table(["Книга", "Автор", "Выдана", "Срок возврата", "Возвращена", "Статус"], [260, 170, 90, 110, 100])
            fill_table(t2, [Row(l.id, [l.book.title, l.book.author, l.issued_at, l.due_at, l.returned_at, l.status]) for l in loans])
            lay.addWidget(t2)
        bar = QHBoxLayout()
        pdf, prn, close = button("Справка в PDF…"), button("Печать справки…"), button("Закрыть", primary=True)
        bar.addStretch()
        for b in (pdf, prn, close):
            bar.addWidget(b)
        lay.addLayout(bar)
        pdf.clicked.connect(self.pdf)
        prn.clicked.connect(self.prn)
        close.clicked.connect(self.accept)

    def _rep(self):
        with Session() as s:
            return reports.reader_certificate(s, self.reader_id)

    def pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить справку", f"справка_{self.reader_id}.pdf", "PDF (*.pdf)")
        if path and guard(self, reports.export_pdf, self._rep(), path)[0]:
            info(self, "Справка сохранена.")

    def prn(self):
        print_report(self, self._rep())


class ReadersTab(QWidget):
    def __init__(self, user):
        super().__init__()
        self.setObjectName("page")
        self.user = user
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        top = QHBoxLayout()
        self.f_name, self.f_ticket, self.f_phone = QLineEdit(), QLineEdit(), QLineEdit()
        self.f_name.setPlaceholderText("ФИО (Ctrl+F)")
        self.f_ticket.setPlaceholderText("Номер билета")
        self.f_phone.setPlaceholderText("Телефон")
        for w in (self.f_name, self.f_ticket, self.f_phone):
            top.addWidget(w)
        lay.addLayout(top)
        self.table = make_table(["Билет", "ФИО", "Дата рождения", "Телефон", "Адрес", "Регистрация", "Книг на руках", "Статус"],
                                [85, 230, 135, 155, 240, 120, 135])
        lay.addWidget(self.table)
        bar = QHBoxLayout()
        self.count = QLabel()
        self.count.setObjectName("hint")
        add, edit, card = button("Добавить (Ctrl+N)", primary=True), button("Изменить"), button("Карточка")
        self.btn_block = button("Заблокировать", danger=True)
        bar.addWidget(self.count)
        bar.addStretch()
        for b in (self.btn_block, card, edit, add):
            bar.addWidget(b)
        lay.addLayout(bar)
        self.deb = Debounce(self.refresh)
        for w in (self.f_name, self.f_ticket, self.f_phone):
            w.textChanged.connect(self.deb)
        add.clicked.connect(self.new_item)
        edit.clicked.connect(self.edit_item)
        card.clicked.connect(self.open_card)
        self.table.doubleClicked.connect(self.open_card)
        self.btn_block.clicked.connect(self.toggle_block)
        self.table.itemSelectionChanged.connect(self._sel)
        self.refresh()

    def focus_search(self):
        self.f_name.setFocus()
        self.f_name.selectAll()

    def refresh(self):
        def load():
            with Session() as s:
                rs = sv.search_readers(s, self.f_name.text(), self.f_ticket.text(), self.f_phone.text())
                cnt = dict(s.execute(select(Loan.reader_id, func.count(Loan.id)).where(Loan.returned_at.is_(None))
                                     .group_by(Loan.reader_id)).all())
                return rs, cnt
        ok, res = guard(self, load)
        if not ok:
            return
        rs, cnt = res
        fill_table(self.table, [Row(r.id, [r.ticket_number, r.full_name, r.birth_date, r.phone, r.address, r.registered_at,
                                           cnt.get(r.id, 0), "заблокирован" if r.is_blocked else "активен"],
                                    fg="#B3261E" if r.is_blocked else None) for r in rs])
        self.count.setText(f"Читателей: {len(rs)}")
        self._sel()

    def _sel(self):
        rid = selected_id(self.table)
        self.btn_block.setEnabled(rid is not None)
        if rid is not None:
            blocked = self.table.item(self.table.currentRow(), 7).text() == "заблокирован"
            self.btn_block.setText("Разблокировать" if blocked else "Заблокировать")

    def new_item(self):
        if ReaderDialog(self, self.user["id"]).exec():
            self.refresh()

    def edit_item(self):
        rid = selected_id(self.table)
        if rid and ReaderDialog(self, self.user["id"], rid).exec():
            self.refresh()

    def open_card(self, *_):
        rid = selected_id(self.table)
        if rid:
            ReaderCard(self, rid).exec()

    def toggle_block(self):
        rid = selected_id(self.table)
        if not rid:
            return
        blocked = self.table.item(self.table.currentRow(), 7).text() == "заблокирован"
        if not confirm(self, "Разблокировать читателя?" if blocked else "Заблокировать читателя? Выдача книг ему станет невозможна."):
            return

        def do():
            with Session() as s:
                sv.set_blocked(s, rid, not blocked, self.user["id"])
        if guard(self, do)[0]:
            self.refresh()
