"""Tests for Excel import of product data."""
import io
import pytest


def _make_excel(rows: list[dict]) -> bytes:
    """Helper: create an Excel file in memory from a list of dicts."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    if rows:
        ws.append(list(rows[0].keys()))
        for row in rows:
            ws.append(list(row.values()))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_excel_basic():
    from importer import parse_product_excel
    data = _make_excel([
        {"url": "https://shopee.vn/product-1-i.123.456", "affiliate": "https://s.shopee.vn/abc"},
        {"url": "https://shopee.vn/product-2-i.789.012", "affiliate": "https://s.shopee.vn/def"},
    ])
    result = parse_product_excel(data)
    assert len(result) == 2
    assert result[0]["url"] == "https://shopee.vn/product-1-i.123.456"
    assert result[0]["affiliate"] == "https://s.shopee.vn/abc"
    assert result[1]["url"] == "https://shopee.vn/product-2-i.789.012"


def test_parse_excel_missing_affiliate():
    from importer import parse_product_excel
    data = _make_excel([
        {"url": "https://shopee.vn/product-1-i.123.456"},
    ])
    result = parse_product_excel(data)
    assert len(result) == 1
    assert result[0]["affiliate"] == ""


def test_parse_excel_skips_empty_rows():
    from importer import parse_product_excel
    data = _make_excel([
        {"url": "https://shopee.vn/product-1-i.123.456", "affiliate": ""},
        {"url": "", "affiliate": ""},
        {"url": "https://shopee.vn/product-2-i.789.012", "affiliate": "https://s.shopee.vn/def"},
    ])
    result = parse_product_excel(data)
    assert len(result) == 2


def test_parse_excel_extracts_title_from_url():
    from importer import parse_product_excel
    data = _make_excel([
        {"url": "https://shopee.vn/Áo-Thun-Nữ-Thắt-Eo-i.123.456", "affiliate": ""},
    ])
    result = parse_product_excel(data)
    assert result[0]["title"] == "Áo Thun Nữ Thắt Eo"
