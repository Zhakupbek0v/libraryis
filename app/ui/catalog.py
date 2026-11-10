"""Вкладка «Каталог книг» (ФТ-1…ФТ-6, ФТ-17, ФТ-19, ФТ-20)."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QSpinBox, QVBoxLayout, QWidget)

from .. import services as sv
from ..models import Book, Session
from .common import (Debounce, FormDialog, Row, button, confirm, fill_table, guard, info, make_table, selected_id)


class BookDialog(FormDialog):
    def __init__(self, parent, user_id, book_id=None):
        super().__init__(parent, "Редактирование книги" if book_id else "Новая книга")
        self.user_id, self.book_id = user_id, book_id
        self.isbn, self.title_e, self.author = QLineEdit(), QLineEdit(), QLineEdit()
        self.genre = QComboBox()
        self.genre.setEditable(True)
        self.publisher, self.year = QLineEdit(), QLineEdit()
        self.year.setPlaceholderText("например, 2021")
        self.copies = QSpinBox()
        self.copies.setRange(0, 9999)
        self.copies.setValue(1)
        self.isbn.setPlaceholderText("10 или 13 цифр, дефисы допускаются")
        with Session() as s:
            self.genre.addItems([""] + sv.genres(s))
            if book_id:
                b = s.get(Book, book_id)
                self.isbn.setText(b.isbn)
                self.title_e.setText(b.title)
                self.author.setText(b.author)
                self.genre.setCurrentText(b.genre)
                self.publisher.setText(b.publisher)
                self.year.setText(str(b.year or ""))
                self.copies.setValue(b.copies_total)
        for label, w in [("ISBN *", self.isbn), ("Название *", self.title_e), ("Автор *", self.author), ("Жанр", self.genre),
                         ("Издательство", self.publisher), ("Год издания", self.year), ("Экземпляров всего", self.copies)]:
            self.form.addRow(label, w)

    def save(self):
        data = dict(isbn=self.isbn.text(), title=self.title_e.text(), author=self.author.text(), genre=self.genre.currentText(),
                    publisher=self.publisher.text(), year=self.year.text(), copies_total=self.copies.value())
        with Session() as s:
            if self.book_id:
                sv.update_book(s, self.book_id, data, self.user_id)
            else:
                sv.add_book(s, data, self.user_id)


class ImportReportDialog(QDialog):
    def __init__(self, parent, res):
        super().__init__(parent)
        self.setWindowTitle("Результат импорта")
        self.resize(560, 360)
        lay = QVBoxLayout(self)
        lbl = QLabel(f"Добавлено книг: <b>{res.added}</b>. Строк с ошибками: <b>{len(res.errors)}</b>.")
        lay.addWidget(lbl)
        if res.errors:
            t = make_table(["Строка в файле", "Причина"], [110])
            fill_table(t, [Row(i, [n, msg]) for i, (n, msg) in enumerate(res.errors)])
            lay.addWidget(t)
        b = button("Закрыть", primary=True)
        b.clicked.connect(self.accept)
        lay.addWidget(b, alignment=Qt.AlignmentFlag.AlignRight)


class CatalogTab(QWidget):
    def __init__(self, user):
        super().__init__()
        self.setObjectName("page")
        self.user = user
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        g = QGridLayout()
        self.f_title, self.f_author, self.f_year, self.f_isbn = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        self.f_title.setPlaceholderText("Название (Ctrl+F)")
        self.f_author.setPlaceholderText("Автор")
        self.f_year.setPlaceholderText("Год")
        self.f_year.setMaximumWidth(80)
        self.f_isbn.setPlaceholderText("ISBN")
        self.f_genre = QComboBox()
        self.f_avail = QCheckBox("Только в наличии")
        self.f_arch = QCheckBox("Показать списанные")
        self.f_arch.setVisible(user["role"] == "head")
        reset = button("Сбросить")
        g.addWidget(self.f_title, 0, 0)
        g.addWidget(self.f_author, 0, 1)
        g.addWidget(self.f_genre, 0, 2)
        g.addWidget(self.f_year, 0, 3)
        g.addWidget(self.f_isbn, 0, 4)
        g.addWidget(self.f_avail, 0, 5)
        g.addWidget(self.f_arch, 0, 6)
        g.addWidget(reset, 0, 7)
        g.setColumnStretch(0, 3)
        g.setColumnStretch(1, 2)
        lay.addLayout(g)
        self.table = make_table(["Название", "Автор", "Жанр", "Издательство", "Год", "ISBN", "Всего", "В наличии"],
                                [300, 190, 115, 130, 65, 130, 75])
        lay.addWidget(self.table)
        bar = QHBoxLayout()
        self.count = QLabel()
        self.count.setObjectName("hint")
        add, edit = button("Добавить (Ctrl+N)", primary=True), button("Изменить")
        self.btn_arch = button("Списать", danger=True)
        imp, tpl = button("Импорт из Excel/CSV…"), button("Шаблон файла…")
        bar.addWidget(self.count)
        bar.addStretch()
        bar.addWidget(tpl)
        bar.addWidget(imp)
        bar.addWidget(edit)
        if user["role"] == "head":
            bar.addWidget(self.btn_arch)  # списание — право заведующего (раздел 4.8 ТЗ)
        bar.addWidget(add)
        lay.addLayout(bar)

        self.deb = Debounce(self.refresh)
        for w in (self.f_title, self.f_author, self.f_year, self.f_isbn):
            w.textChanged.connect(self.deb)
        self.f_genre.currentIndexChanged.connect(self.deb)
        self.f_avail.toggled.connect(self.deb)
        self.f_arch.toggled.connect(self.deb)
        reset.clicked.connect(self.reset)
        add.clicked.connect(self.new_item)
        edit.clicked.connect(self.edit_item)
        self.table.doubleClicked.connect(self.edit_item)
        self.btn_arch.clicked.connect(self.archive)
        imp.clicked.connect(self.do_import)
        tpl.clicked.connect(self.save_template)
        self.table.itemSelectionChanged.connect(self._sel)
        self._load_genres()
        self.refresh()

    def _load_genres(self):
        cur = self.f_genre.currentText()
        self.f_genre.blockSignals(True)
        self.f_genre.clear()
        self.f_genre.addItem("Все жанры", "")
        with Session() as s:
            for g in sv.genres(s):
                self.f_genre.addItem(g, g)
        i = self.f_genre.findText(cur)
        self.f_genre.setCurrentIndex(max(i, 0))
        self.f_genre.blockSignals(False)

    def focus_search(self):
        self.f_title.setFocus()
        self.f_title.selectAll()

    def reset(self):
        for w in (self.f_title, self.f_author, self.f_year, self.f_isbn):
            w.clear()
        self.f_genre.setCurrentIndex(0)
        self.f_avail.setChecked(False)

    def refresh(self):
        def load():
            with Session() as s:
                return sv.search_books(s, self.f_title.text(), self.f_author.text(), self.f_genre.currentData() or "",
                                       self.f_year.text(), self.f_isbn.text(), self.f_avail.isChecked(),
                                       self.f_arch.isChecked())
        ok, books = guard(self, load)
        if not ok:
            return
        rows = []
        for b in books:
            if b.is_archived:
                rows.append(Row(b.id, [b.title + " (списана)", b.author, b.genre, b.publisher, b.year, b.isbn, b.copies_total,
                                       b.copies_available], fg="#8A93A6", italic=True))
            else:
                bg = "#FDECEA" if b.copies_available == 0 else None  # ФТ-20: сразу видно, что экземпляров нет
                rows.append(Row(b.id, [b.title, b.author, b.genre, b.publisher, b.year, b.isbn, b.copies_total,
                                       b.copies_available], bg=bg))
        fill_table(self.table, rows)
        free = sum(b.copies_available for b in books)
        self.count.setText(f"Найдено названий: {len(books)} · свободных экземпляров: {free}")
        self._sel()

    def _sel(self):
        bid = selected_id(self.table)
        if bid is None:
            self.btn_arch.setEnabled(False)
            return
        archived = "(списана)" in self.table.item(self.table.currentRow(), 0).text()
        self.btn_arch.setText("Восстановить" if archived else "Списать")
        self.btn_arch.setEnabled(True)

    def new_item(self):
        if BookDialog(self, self.user["id"]).exec():
            self._load_genres()
            self.refresh()

    def edit_item(self, *_):
        bid = selected_id(self.table)
        if bid and BookDialog(self, self.user["id"], bid).exec():
            self._load_genres()
            self.refresh()

    def archive(self):
        bid = selected_id(self.table)
        if not bid:
            return
        archived = "(списана)" in self.table.item(self.table.currentRow(), 0).text()
        if not confirm(self, "Восстановить книгу в каталоге?" if archived else
                       "Списать книгу? Она исчезнет из каталога выдачи, история выдач сохранится."):
            return

        def do():
            with Session() as s:
                sv.archive_book(s, bid, self.user["id"], not archived)
        if guard(self, do)[0]:
            self.refresh()

    def do_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите файл каталога", "", "Excel и CSV (*.xlsx *.csv)")
        if not path:
            return

        def do():
            with Session() as s:
                return sv.import_books(s, path, self.user["id"])
        ok, res = guard(self, do)
        if ok:
            ImportReportDialog(self, res).exec()
            self._load_genres()
            self.refresh()

    def save_template(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить шаблон", "шаблон_каталога.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["ISBN", "Название", "Автор", "Жанр", "Издательство", "Год", "Количество"])
        ws.append(["9785170000001", "Пример книги", "Иван Иванов", "Роман", "Эксмо", 2023, 3])
        for col, w in zip("ABCDEFG", (18, 34, 24, 16, 18, 8, 12)):
            ws.column_dimensions[col].width = w
        wb.save(path)
        info(self, "Шаблон сохранён. Заполните его и загрузите кнопкой «Импорт из Excel/CSV».")
