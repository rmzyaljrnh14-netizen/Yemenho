"""Tests for the export builders and report helpers (pure, no DB)."""
from __future__ import annotations

import io

from openpyxl import load_workbook

from app.services import analytics, export

COLUMNS = ["المستشفى", "المؤشر", "القيمة"]
ROWS = [["هيئة المستشفى الجمهوري (تجريبي)", "تغطية التدقيق", "90"], ["مستشفى آخر", "العدوى", "—"]]


def test_fmt_value_never_invents_a_number():
    assert analytics.fmt_value(None) == "—"
    assert analytics.fmt_value(90.0) == "90"
    assert analytics.fmt_value(2.5) == "2.5"
    assert analytics.fmt_value(2.50) == "2.5"


def test_excel_has_title_header_and_rows():
    content = export.build_excel(title="تقرير", subtitle="الفترة: 2025-06", columns=COLUMNS, rows=ROWS)
    wb = load_workbook(io.BytesIO(content))
    ws = wb.active
    assert ws.sheet_view.rightToLeft is True
    values = [c for row in ws.iter_rows(values_only=True) for c in row if c is not None]
    assert "تقرير" in values
    assert "المستشفى" in values
    assert any("هيئة المستشفى الجمهوري" in str(v) for v in values)


def test_excel_includes_every_data_row():
    content = export.build_excel(title="ت", subtitle="س", columns=COLUMNS, rows=ROWS)
    wb = load_workbook(io.BytesIO(content))
    ws = wb.active
    all_text = "\n".join(str(c) for row in ws.iter_rows(values_only=True) for c in row if c)
    assert "مستشفى آخر" in all_text
    assert "العدوى" in all_text


def test_pdf_starts_with_pdf_magic_and_contains_rows():
    content = export.build_pdf(title="تقرير", subtitle="الفترة: 2025-06", columns=COLUMNS, rows=ROWS, note="تجريبي")
    assert content[:5] == b"%PDF-"
    assert len(content) > 1000


def test_arabic_shaping_does_not_crash_on_mixed_text():
    out = export._shape_ar("مؤشر IPC-HAND 2025")
    assert isinstance(out, str)
    assert out
    assert export._shape_ar(None) == ""
