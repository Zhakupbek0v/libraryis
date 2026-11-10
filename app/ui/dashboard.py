"""Вкладка «Главная»: краткая сводка (раздел 4.5 ТЗ)."""
from datetime import date, timedelta

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from sqlalchemy import func, select

from .. import services as sv
from ..models import Book, Loan, Reader, Session
from .common import BarChart, Row, fill_table, make_table, stat_card

RU_MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


class DashboardTab(QWidget):
    def __init__(self, user):
        super().__init__()
        self.setObjectName("page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        hello = QLabel(f"Здравствуйте, {user['full_name'].split()[1] if len(user['full_name'].split()) > 1 else user['full_name']}!")
        hello.setObjectName("h2")
        lay.addWidget(hello)
        row = QHBoxLayout()
        self.cards = {}
        for key, cap in [("today", "Выдано сегодня"), ("overdue", "Просрочено выдач"), ("onhand", "Книг на руках"),
                         ("readers", "Читателей"), ("books", "Книг в фонде (экз.)")]:
            f, num = stat_card(cap)
            self.cards[key] = num
            row.addWidget(f)
        lay.addLayout(row)
        mid = QHBoxLayout()
        self.chart = BarChart("Выдачи по месяцам")
        mid.addWidget(self.chart, 1)
        right = QVBoxLayout()
        h = QLabel("Просроченные выдачи")
        h.setObjectName("h2")
        right.addWidget(h)
        self.table = make_table(["Читатель", "Книга", "Срок", "Дней"], [170, 230, 90])
        right.addWidget(self.table)
        mid.addLayout(right, 2)
        lay.addLayout(mid, 1)
        self.refresh()

    def focus_search(self):
        pass

    def refresh(self):
        today = date.today()
        with Session() as s:
            sv.refresh_overdue(s)
            self.cards["today"].setText(str(s.scalar(select(func.count(Loan.id)).where(Loan.issued_at == today))))
            self.cards["overdue"].setText(str(s.scalar(select(func.count(Loan.id)).where(Loan.returned_at.is_(None), Loan.due_at < today))))
            self.cards["onhand"].setText(str(s.scalar(select(func.count(Loan.id)).where(Loan.returned_at.is_(None)))))
            self.cards["readers"].setText(str(s.scalar(select(func.count(Reader.id)))))
            self.cards["books"].setText(str(s.scalar(select(func.coalesce(func.sum(Book.copies_total), 0)).where(Book.is_archived.is_(False)))))
            data = []
            y, m = today.year, today.month
            months = []
            for _ in range(6):
                months.append((y, m))
                m -= 1
                if m == 0:
                    y, m = y - 1, 12
            for (yy, mm) in reversed(months):
                start = date(yy, mm, 1)
                end = date(yy + (mm == 12), mm % 12 + 1, 1)
                n = s.scalar(select(func.count(Loan.id)).where(Loan.issued_at >= start, Loan.issued_at < end))
                data.append((RU_MONTHS[mm - 1], n))
            self.chart.set_data(data)
            q = (select(Loan).where(Loan.returned_at.is_(None), Loan.due_at < today).order_by(Loan.due_at).limit(12))
            fill_table(self.table, [Row(l.id, [l.reader.full_name, l.book.title, l.due_at, (today - l.due_at).days], fg="#B3261E")
                                    for l in s.scalars(q)])
