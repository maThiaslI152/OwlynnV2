"""
Unified PDF text intake — StirlingPDF primary, PyMuPDF fallback.
"""

from __future__ import annotations

import logging

from src.config.settings import STIRLING_PDF_MIN_TEXT_CHARS
from src.integrations import stirling_pdf

logger = logging.getLogger(__name__)


def _extract_with_pymupdf_path(path: str, *, page_markers: bool) -> str:
    import fitz

    doc = fitz.open(path)
    try:
        if page_markers:
            parts: list[str] = []
            for i, page in enumerate(doc):
                parts.append(f"--- Page {i + 1} ---\n{page.get_text()}\n")
            return "".join(parts)
        return "\n\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _extract_with_pymupdf_bytes(data: bytes) -> str:
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return "\n\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _stirling_extract(
    *,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
    filename: str = "upload.pdf",
) -> str:
    text = stirling_pdf.extract_text(
        file_path=file_path, file_bytes=file_bytes, filename=filename
    )
    if len(text.strip()) < STIRLING_PDF_MIN_TEXT_CHARS:
        logger.info(
            "[pdf/intake] Stirling text below threshold (%d chars) — running OCR",
            STIRLING_PDF_MIN_TEXT_CHARS,
        )
        text = stirling_pdf.ocr_then_extract(
            file_path=file_path, file_bytes=file_bytes, filename=filename
        )
    return text


def extract_pdf_text_from_path(path: str, *, page_markers: bool = False) -> str:
    """Extract text from a PDF file on disk."""
    if stirling_pdf.is_configured() and stirling_pdf.is_available():
        try:
            text = _stirling_extract(file_path=path)
            if text.strip():
                return text
            logger.warning("[pdf/intake] Stirling returned empty text for %s", path)
        except Exception as e:
            logger.warning(
                "[pdf/intake] Stirling extraction failed for %s: %s — falling back to PyMuPDF",
                path,
                e,
            )
    elif stirling_pdf.is_configured():
        logger.warning(
            "[pdf/intake] StirlingPDF configured but unreachable — using PyMuPDF for %s",
            path,
        )

    return _extract_with_pymupdf_path(path, page_markers=page_markers)


def extract_pdf_text_from_bytes(data: bytes, *, filename: str = "upload.pdf") -> str:
    """Extract text from PDF bytes (chat attachments)."""
    if stirling_pdf.is_configured() and stirling_pdf.is_available():
        try:
            text = _stirling_extract(file_bytes=data, filename=filename)
            if text.strip():
                return text
            logger.warning("[pdf/intake] Stirling returned empty text for %s", filename)
        except Exception as e:
            logger.warning(
                "[pdf/intake] Stirling extraction failed for %s: %s — falling back to PyMuPDF",
                filename,
                e,
            )
    elif stirling_pdf.is_configured():
        logger.warning(
            "[pdf/intake] StirlingPDF configured but unreachable — using PyMuPDF for %s",
            filename,
        )

    return _extract_with_pymupdf_bytes(data)
