"""Вкладка «Отчёты» (ФТ-24…ФТ-29)."""
from datetime import date, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextDocument
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import reports
from ..models import Session
from .common import Row, button, date_edit, fill_table, guard, info, make_table, pydate
from .loans import pick_reader


def print_report(parent, rep):
    """ФТ-29: вывод на печать на любой принтер, установленный в Windows."""
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    dlg = QPrintDialog(printer, parent)
    if dlg.exec():
        doc = QTextDocument()
        doc.setHtml(reports.to_html(rep))
        doc.print(printer)


class ReportsTab(QWidget):
    def __init__(self, user):
        super().__init__()
        self.setObjectName("page")
        self.rep = None
        self.reader_id = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        bar = QHBoxLayout()
        self.kind = QComboBox()
        items = [("Справка о читателе", "cert"), ("Список должников", "debt")]
        if user["role"] == "head":
            items += [("Выдачи за период", "period"), ("Самые популярные книги (топ-10)", "top"), ("Состояние фонда", "fund")]
        for l, k in items:
            self.kind.addItem(l, k)
        self.d1 = date_edit(date.today() - timedelta(days=30))
        self.d2 = date_edit()
        self.l1, self.l2 = QLabel("с"), QLabel("по")
        self.pick = button("Выбрать читателя…")
        self.pick_lbl = QLabel("читатель не выбран")
        self.pick_lbl.setStyleSheet("color:#5B6780")
        self.make = button("Сформировать", primary=True)
        for w in (self.kind, self.l1, self.d1, self.l2, self.d2, self.pick, self.pick_lbl):
            bar.addWidget(w)
        bar.addStretch()
        bar.addWidget(self.make)
        lay.addLayout(bar)
        self.title = QLabel("")
        self.title.setObjectName("h2")
        self.lines = QLabel("")
        self.lines.setObjectName("hint")
        self.lines.setWordWrap(True)
        lay.addWidget(self.title)
        lay.addWidget(self.lines)
        self.table = make_table(["—"])
        self.table.setVisible(False)
        lay.addWidget(self.table)
        self.empty = QLabel("Выберите вид отчёта и нажмите «Сформировать».\nГотовый отчёт можно сохранить в PDF или Excel либо распечатать.")
        self.empty.setObjectName("hint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.empty, 1)
        bot = QHBoxLayout()
        bot.addStretch()
        self.pdf, self.xls, self.prn = button("Сохранить в PDF…"), button("Сохранить в Excel…"), button("Печать…")
        for b in (self.pdf, self.xls, self.prn):
            b.setEnabled(False)
            bot.addWidget(b)
        lay.addLayout(bot)
        self.kind.currentIndexChanged.connect(self._kind)
        self.make.clicked.connect(self.build)
        self.pick.clicked.connect(self.choose_reader)
        self.pdf.clicked.connect(lambda: self.export("pdf"))
        self.xls.clicked.connect(lambda: self.export("xlsx"))
        self.prn.clicked.connect(lambda: print_report(self, self.rep))
        self._kind()

    def focus_search(self):
        self.kind.setFocus()

    def refresh(self):
        pass

    def _kind(self):
        k = self.kind.currentData()
        for w in (self.l1, self.d1, self.l2, self.d2):
            w.setVisible(k == "period")
        self.pick.setVisible(k == "cert")
        self.pick_lbl.setVisible(k == "cert")

    def choose_reader(self):
        rid, label = pick_reader(self)
        if rid:
            self.reader_id = rid
            self.pick_lbl.setText(label)
            self.pick_lbl.setStyleSheet("color:#1D2B4A;font-weight:600")

    def build(self):
        k = self.kind.currentData()
        if k == "cert" and not self.reader_id:
            info(self, "Выберите читателя, для которого нужна справка.")
            return
        if k == "period" and pydate(self.d1) > pydate(self.d2):
            info(self, "Дата начала периода позже даты окончания.")
            return

        def do():
            with Session() as s:
                if k == "cert":
                    return reports.reader_certificate(s, self.reader_id)
                if k == "debt":
                    return reports.debtors(s)
                if k == "period":
                    return reports.loans_period(s, pydate(self.d1), pydate(self.d2))
                if k == "top":
                    return reports.top_books(s)
                return reports.fund_state(s)
        ok, rep = guard(self, do)
        if not ok:
            return
        self.rep = rep
        self.empty.setVisible(False)
        self.table.setVisible(True)
        self.title.setText(rep.title)
        self.lines.setText("\n".join(rep.lines))
        self.table.setSortingEnabled(False)
        self.table.setColumnCount(len(rep.headers))
        self.table.setHorizontalHeaderLabels(rep.headers)
        fill_table(self.table, [Row(i, r) for i, r in enumerate(rep.rows)])
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        for b in (self.pdf, self.xls, self.prn):
            b.setEnabled(True)

    def export(self, kind):
        ext = "pdf" if kind == "pdf" else "xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить отчёт", f"{self.rep.title}.{ext}",
                                              "PDF (*.pdf)" if kind == "pdf" else "Excel (*.xlsx)")
        if not path:
            return
        fn = reports.export_pdf if kind == "pdf" else reports.export_xlsx
        if guard(self, fn, self.rep, path)[0]:
            info(self, f"Файл сохранён:\n{path}")
