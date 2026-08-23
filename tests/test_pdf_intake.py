"""Tests for unified PDF intake (StirlingPDF + PyMuPDF fallback)."""

from __future__ import annotations

from unittest.mock import patch

import fitz

from src.pdf import intake


def _minimal_pdf_bytes(text: str = "Hello Owlynn PDF") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _write_temp_pdf(tmp_path, text: str = "Hello Owlynn PDF") -> str:
    path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()
    return str(path)


@patch("src.pdf.intake.stirling_pdf.is_available", return_value=True)
@patch("src.pdf.intake.stirling_pdf.is_configured", return_value=True)
@patch(
    "src.pdf.intake.stirling_pdf.extract_text",
    return_value="Stirling extracted text with enough characters to skip OCR pass.",
)
def test_stirling_success_from_bytes(_cfg, _avail, _extract):
    data = _minimal_pdf_bytes()
    result = intake.extract_pdf_text_from_bytes(data)
    assert result == "Stirling extracted text with enough characters to skip OCR pass."


@patch("src.pdf.intake.stirling_pdf.is_available", return_value=True)
@patch("src.pdf.intake.stirling_pdf.is_configured", return_value=True)
@patch(
    "src.pdf.intake.stirling_pdf.ocr_then_extract",
    return_value="OCR text result",
)
@patch("src.pdf.intake.stirling_pdf.extract_text", return_value="x")
@patch("src.pdf.intake.STIRLING_PDF_MIN_TEXT_CHARS", 50)
def test_stirling_ocr_when_text_below_threshold(_extract, _ocr, _cfg, _avail):
    data = _minimal_pdf_bytes()
    result = intake.extract_pdf_text_from_bytes(data)
    assert result == "OCR text result"
    _ocr.assert_called_once()


@patch("src.pdf.intake.stirling_pdf.is_available", return_value=False)
@patch("src.pdf.intake.stirling_pdf.is_configured", return_value=True)
def test_stirling_unavailable_falls_back_to_pymupdf(_cfg, _avail, tmp_path):
    path = _write_temp_pdf(tmp_path, "PyMuPDF fallback text")
    result = intake.extract_pdf_text_from_path(path)
    assert "PyMuPDF fallback text" in result


@patch("src.pdf.intake.stirling_pdf.is_configured", return_value=False)
def test_stirling_disabled_uses_pymupdf(_cfg, tmp_path):
    path = _write_temp_pdf(tmp_path, "Direct PyMuPDF")
    result = intake.extract_pdf_text_from_path(path)
    assert "Direct PyMuPDF" in result


@patch("src.pdf.intake.stirling_pdf.is_available", return_value=True)
@patch("src.pdf.intake.stirling_pdf.is_configured", return_value=True)
@patch(
    "src.pdf.intake.stirling_pdf.extract_text",
    side_effect=RuntimeError("connection refused"),
)
def test_stirling_error_falls_back_to_pymupdf(_extract, _cfg, _avail, tmp_path):
    path = _write_temp_pdf(tmp_path, "Error fallback text")
    result = intake.extract_pdf_text_from_path(path)
    assert "Error fallback text" in result


@patch("src.pdf.intake.stirling_pdf.is_available", return_value=True)
@patch("src.pdf.intake.stirling_pdf.is_configured", return_value=True)
@patch(
    "src.pdf.intake.stirling_pdf.extract_text",
    return_value="Page content with sufficient length to bypass the OCR threshold check.",
)
def test_path_extraction_page_markers(_extract, _cfg, _avail, tmp_path):
    path = _write_temp_pdf(tmp_path)
    # page_markers only affects PyMuPDF fallback formatting; Stirling returns as-is
    result = intake.extract_pdf_text_from_path(path, page_markers=True)
    assert "Page content with sufficient length" in result


@patch("src.integrations.stirling_pdf.STIRLING_PDF_URL", "http://localhost:8090")
@patch("src.integrations.stirling_pdf.STIRLING_PDF_ENABLED", True)
def test_stirling_is_configured():
    from src.integrations import stirling_pdf

    assert stirling_pdf.is_configured() is True


@patch("src.integrations.stirling_pdf.STIRLING_PDF_ENABLED", False)
def test_stirling_not_configured_when_disabled():
    from src.integrations import stirling_pdf

    assert stirling_pdf.is_configured() is False
