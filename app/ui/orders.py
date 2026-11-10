"""Вкладка «Заказы поставщикам» (ФТ-21…ФТ-23)."""
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QSplitter, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt
from sqlalchemy import select

from .. import services as sv
from ..models import PurchaseOrder, Session, Supplier
from .common import FormDialog, Row, button, confirm, fill_table, guard, info, make_table, selected_id
from .loans import pick_book


class SupplierDialog(FormDialog):
    def __init__(self, parent, user_id, supplier_id=None):
        super().__init__(parent, "Поставщик")
        self.user_id, self.supplier_id = user_id, supplier_id
        self.name, self.phone, self.address = QLineEdit(), QLineEdit(), QLineEdit()
        if supplier_id:
            with Session() as s:
                sp = s.get(Supplier, supplier_id)
                self.name.setText(sp.name)
                self.phone.setText(sp.phone)
                self.address.setText(sp.address)
        for l, w in [("Название *", self.name), ("Телефон", self.phone), ("Адрес", self.address)]:
            self.form.addRow(l, w)

    def save(self):
        with Session() as s:
            sv.save_supplier(s, self.supplier_id, dict(name=self.name.text(), phone=self.phone.text(), address=self.address.text()),
                             self.user_id)


class OrderDialog(FormDialog):
    def __init__(self, parent, user_id):
        super().__init__(parent, "Новый заказ книг")
        self.user_id, self.book_id = user_id, None
        self.supplier = QComboBox()
        with Session() as s:
            for sp in s.scalars(select(Supplier).order_by(Supplier.name)):
                self.supplier.addItem(sp.name, sp.id)
        self.book_btn = button("Выбрать книгу…")
        self.book_lbl = QLabel("не выбрана")
        row = QHBoxLayout()
        row.addWidget(self.book_btn)
        row.addWidget(self.book_lbl, 1)
        self.qty = QSpinBox()
        self.qty.setRange(1, 1000)
        self.qty.setValue(5)
        self.form.addRow("Поставщик", self.supplier)
        self.form.addRow("Книга", row)
        self.form.addRow("Количество", self.qty)
        self.book_btn.clicked.connect(self.pick)

    def pick(self):
        bid, label = pick_book(self)
        if bid:
            self.book_id = bid
            self.book_lbl.setText(label)

    def save(self):
        with Session() as s:
            sv.create_order(s, self.supplier.currentData(), self.book_id, self.qty.value(), self.user_id)


class OrdersTab(QWidget):
    def __init__(self, user):
        super().__init__()
        self.setObjectName("page")
        self.user = user
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        sp = QSplitter(Qt.Orientation.Vertical)
        lay.addWidget(sp)

        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        h = QLabel("Поставщики")
        h.setObjectName("h2")
        tl.addWidget(h)
        self.sup = make_table(["Название", "Телефон", "Адрес"], [240, 160])
        tl.addWidget(self.sup)
        bar = QHBoxLayout()
        bar.addStretch()
        sa, se = button("Добавить поставщика"), button("Изменить")
        bar.addWidget(se)
        bar.addWidget(sa)
        tl.addLayout(bar)
        sp.addWidget(top)

        bot = QWidget()
        bl = QVBoxLayout(bot)
        bl.setContentsMargins(0, 0, 0, 0)
        h2 = QLabel("Заказы книг")
        h2.setObjectName("h2")
        bl.addWidget(h2)
        self.orders = make_table(["№", "Дата", "Поставщик", "Книга", "Кол-во", "Статус"], [50, 95, 200, 320, 70])
        bl.addWidget(self.orders)
        bar2 = QHBoxLayout()
        bar2.addStretch()
        self.adv = button("Далее по статусу", primary=True)
        na = button("Создать заказ (Ctrl+N)")
        bar2.addWidget(self.adv)
        bar2.addWidget(na)
        bl.addLayout(bar2)
        sp.addWidget(bot)

        sa.clicked.connect(lambda: self._sup(None))
        se.clicked.connect(lambda: self._sup(selected_id(self.sup)))
        self.sup.doubleClicked.connect(lambda *_: self._sup(selected_id(self.sup)))
        na.clicked.connect(self.new_item)
        self.adv.clicked.connect(self.advance)
        self.orders.itemSelectionChanged.connect(self._sel)
        self.refresh()

    def focus_search(self):
        self.orders.setFocus()

    def _sup(self, sid):
        if SupplierDialog(self, self.user["id"], sid).exec():
            self.refresh()

    def new_item(self):
        with Session() as s:
            if not s.scalar(select(Supplier.id)):
                info(self, "Сначала добавьте поставщика.")
                return
        if OrderDialog(self, self.user["id"]).exec():
            self.refresh()

    def refresh(self):
        with Session() as s:
            fill_table(self.sup, [Row(x.id, [x.name, x.phone, x.address]) for x in s.scalars(select(Supplier).order_by(Supplier.name))])
            orders = list(s.scalars(select(PurchaseOrder).order_by(PurchaseOrder.id.desc())))
            fill_table(self.orders, [Row(o.id, [o.id, o.ordered_at, o.supplier.name, o.book.title, o.quantity, o.status],
                                         fg="#1B7F3B" if o.status == "получен" else None) for o in orders])
        self._sel()

    def _sel(self):
        oid = selected_id(self.orders)
        if oid is None:
            self.adv.setEnabled(False)
            return
        st = self.orders.item(self.orders.currentRow(), 5).text()
        self.adv.setEnabled(st != "получен")
        self.adv.setText({"создан": "Отметить отправленным", "отправлен": "Принять поставку"}.get(st, "Заказ получен"))

    def advance(self):
        oid = selected_id(self.orders)
        st = self.orders.item(self.orders.currentRow(), 5).text()
        if st == "отправлен" and not confirm(self, "Принять поставку? Книги будут добавлены в каталог."):
            return

        def do():
            with Session() as s:
                return sv.advance_order(s, oid, self.user["id"])
        if guard(self, do)[0]:
            self.refresh()
