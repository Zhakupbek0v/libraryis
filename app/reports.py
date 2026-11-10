"""Справки и отчёты (ФТ-24…ФТ-29): формирование, экспорт в PDF и Excel, HTML для печати."""
from __future__ import annotations

import html
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select

from .models import Book, Loan, Reader


def fmt(d) -> str:
    if isinstance(d, (date, datetime)):
        return d.strftime("%d.%m.%Y")
    return "" if d is None else str(d)


@dataclass
class Report:
    title: str
    headers: list
    rows: list
    lines: list = field(default_factory=list)  # пояснительные строки под заголовком


# ---------------------------------------------------------------- построение
def debtors(s) -> Report:
    """ФТ-25: должники и просроченные выдачи."""
    today = date.today()
    q = (select(Loan).join(Reader).join(Book)
         .where(Loan.returned_at.is_(None), Loan.due_at < today).order_by(Loan.due_at))
    rows = [[l.reader.full_name, l.reader.ticket_number, l.reader.phone, l.book.title, fmt(l.issued_at),
             fmt(l.due_at), (today - l.due_at).days] for l in s.scalars(q)]
    return Report("Список должников", ["Читатель", "Билет", "Телефон", "Книга", "Выдана", "Срок возврата", "Дней просрочки"],
                  rows, [f"По состоянию на {fmt(today)}. Всего просроченных выдач: {len(rows)}"])


def loans_period(s, d1: date, d2: date) -> Report:
    """ФТ-26: выдачи за период."""
    q = (select(Loan).join(Reader).join(Book).where(Loan.issued_at >= d1, Loan.issued_at <= d2)
         .order_by(Loan.issued_at))
    rows = [[fmt(l.issued_at), l.reader.full_name, l.book.title, fmt(l.due_at), fmt(l.returned_at) or "—", l.status]
            for l in s.scalars(q)]
    return Report("Выдачи за период", ["Дата выдачи", "Читатель", "Книга", "Срок возврата", "Возвращена", "Статус"], rows,
                  [f"Период: {fmt(d1)} – {fmt(d2)}. Всего выдач: {len(rows)}"])


def top_books(s, limit: int = 10) -> Report:
    """ФТ-27: самые популярные книги."""
    q = (select(Book.title, Book.author, func.count(Loan.id).label("n")).join(Loan, Loan.book_id == Book.id)
         .group_by(Book.id).order_by(func.count(Loan.id).desc(), Book.title).limit(limit))
    rows = [[i + 1, t, a, n] for i, (t, a, n) in enumerate(s.execute(q))]
    return Report(f"Самые популярные книги (топ-{limit})", ["№", "Название", "Автор", "Число выдач"], rows,
                  [f"Сформирован {fmt(date.today())}"])


def fund_state(s) -> Report:
    """ФТ-28: состояние фонда."""
    q = (select(Book.genre, func.count(Book.id), func.sum(Book.copies_total), func.sum(Book.copies_available))
         .where(Book.is_archived.is_(False)).group_by(Book.genre).order_by(Book.genre))
    rows, tt, tc, ta = [], 0, 0, 0
    for g, titles, total, avail in s.execute(q):
        total, avail = total or 0, avail or 0
        rows.append([g or "Без жанра", titles, total, total - avail, avail])
        tt, tc, ta = tt + titles, tc + total, ta + avail
    rows.append(["ИТОГО", tt, tc, tc - ta, ta])
    return Report("Состояние фонда", ["Жанр", "Названий", "Всего экз.", "Выдано", "Свободно"], rows,
                  [f"По состоянию на {fmt(date.today())}"])


def reader_certificate(s, reader_id: int) -> Report:
    """ФТ-24: справка о читателе."""
    r = s.get(Reader, reader_id)
    loans = list(s.scalars(select(Loan).where(Loan.reader_id == reader_id).order_by(Loan.issued_at.desc())))
    on_hand = [l for l in loans if l.returned_at is None]
    rows = [[l.book.title, l.book.author, fmt(l.issued_at), fmt(l.due_at), fmt(l.returned_at) or "—", l.status]
            for l in loans]
    lines = [f"Читатель: {r.full_name}", f"Читательский билет № {r.ticket_number}",
             f"Дата рождения: {fmt(r.birth_date)}. Телефон: {r.phone or '—'}. Адрес: {r.address or '—'}",
             f"Зарегистрирован: {fmt(r.registered_at)}. Статус: {'заблокирован' if r.is_blocked else 'активен'}",
             f"Книг на руках: {len(on_hand)}. Всего взято за время обслуживания: {len(loans)}"]
    return Report("Справка о читателе", ["Книга", "Автор", "Выдана", "Срок возврата", "Возвращена", "Статус"], rows, lines)


# ---------------------------------------------------------------- экспорт
def _find_font():
    cands = [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\times.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
             "/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"]
    bold = {r"C:\Windows\Fonts\arial.ttf": r"C:\Windows\Fonts\arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf":
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"}
    for c in cands:
        if os.path.exists(c):
            b = bold.get(c)
            return c, (b if b and os.path.exists(b) else c)
    raise RuntimeError("Не найден шрифт с поддержкой кириллицы для PDF")


def export_pdf(rep: Report, path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    reg, bold = _find_font()
    pdfmetrics.registerFont(TTFont("LIS", reg))
    pdfmetrics.registerFont(TTFont("LIS-B", bold))
    wide = len(rep.headers) > 5
    page = landscape(A4) if wide else A4
    doc = SimpleDocTemplate(str(path), pagesize=page, leftMargin=36, rightMargin=36, topMargin=40, bottomMargin=40,
                            title=rep.title)
    h = ParagraphStyle("h", fontName="LIS-B", fontSize=16, spaceAfter=6)
    t = ParagraphStyle("t", fontName="LIS", fontSize=10, leading=14)
    cell = ParagraphStyle("c", fontName="LIS", fontSize=8.5, leading=10.5)
    cellb = ParagraphStyle("cb", parent=cell, fontName="LIS-B", textColor=colors.white)
    story = [Paragraph("Библиотека · LibraryIS", ParagraphStyle("s", fontName="LIS", fontSize=9, textColor=colors.grey)),
             Paragraph(html.escape(rep.title), h)]
    story += [Paragraph(html.escape(x), t) for x in rep.lines]
    story.append(Spacer(1, 10))
    data = [[Paragraph(html.escape(str(x)), cellb) for x in rep.headers]]
    for r in rep.rows:
        data.append([Paragraph(html.escape(str(x)), cell) for x in r])
    if rep.rows:
        tbl = Table(data, repeatRows=1)
        tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C5AA0")),
                                 ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C2D0")),
                                 ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5FA")]),
                                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                 ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story.append(tbl)
    else:
        story.append(Paragraph("Нет данных для отображения.", t))
    story += [Spacer(1, 14), Paragraph(f"Сформировано: {datetime.now():%d.%m.%Y %H:%M}", t)]

    def footer(canvas, d):
        canvas.setFont("LIS", 8)
        canvas.drawCentredString(page[0] / 2, 22, f"Стр. {d.page}")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def export_xlsx(rep: Report, path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = rep.title[:31]
    ws["A1"] = rep.title
    ws["A1"].font = Font(size=14, bold=True)
    r0 = 2
    for line in rep.lines:
        ws.cell(row=r0, column=1, value=line)
        r0 += 1
    r0 += 1
    thin = Side(style="thin", color="B8C2D0")
    for c, h in enumerate(rep.headers, 1):
        cell = ws.cell(row=r0, column=c, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2C5AA0")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
    for i, row in enumerate(rep.rows, r0 + 1):
        for c, v in enumerate(row, 1):
            cell = ws.cell(row=i, column=c, value=v)
            cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for c in range(1, len(rep.headers) + 1):
        width = max([len(str(rep.headers[c - 1]))] + [len(str(r[c - 1])) for r in rep.rows] or [10])
        ws.column_dimensions[get_column_letter(c)].width = min(max(width + 3, 10), 55)
    ws.freeze_panes = ws.cell(row=r0 + 1, column=1)
    wb.save(path)


def to_html(rep: Report) -> str:
    e = html.escape
    head = "".join(f"<th style='border:1px solid #888;padding:4px;background:#e8edf5'>{e(str(h))}</th>" for h in rep.headers)
    body = "".join("<tr>" + "".join(f"<td style='border:1px solid #888;padding:4px'>{e(str(x))}</td>" for x in r) + "</tr>"
                   for r in rep.rows)
    lines = "".join(f"<p style='margin:2px 0'>{e(l)}</p>" for l in rep.lines)
    return (f"<h2>{e(rep.title)}</h2>{lines}<br><table cellspacing='0' width='100%'>"
            f"<tr>{head}</tr>{body}</table><p>Сформировано: {datetime.now():%d.%m.%Y %H:%M}</p>")
