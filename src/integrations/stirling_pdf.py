"""
StirlingPDF HTTP client — PDF text extraction and OCR.

See: https://docs.stirlingpdf.com/API/
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

import httpx

from src.config.settings import (
    STIRLING_PDF_API_KEY,
    STIRLING_PDF_ENABLED,
    STIRLING_PDF_OCR_LANGUAGES,
    STIRLING_PDF_TIMEOUT_SECONDS,
    STIRLING_PDF_URL,
)

logger = logging.getLogger(__name__)

_CONVERT_PDF_TEXT = "/api/v1/convert/pdf/text"
_CONVERT_HTML_PDF = "/api/v1/convert/html/pdf"
_OCR_PDF = "/api/v1/misc/ocr-pdf"
_STATUS = "/api/v1/info/status"


def _base_url() -> str:
    return (STIRLING_PDF_URL or "").rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"User-Agent": "Owlynn/1.0"}
    if STIRLING_PDF_API_KEY:
        headers["X-API-KEY"] = STIRLING_PDF_API_KEY
    return headers


def is_configured() -> bool:
    return bool(STIRLING_PDF_ENABLED and STIRLING_PDF_URL)


def is_available() -> bool:
    """Lightweight health check against the StirlingPDF instance."""
    if not is_configured():
        return False
    try:
        with httpx.Client(timeout=5.0, headers=_headers()) as client:
            resp = client.get(f"{_base_url()}{_STATUS}")
            if resp.status_code == 200:
                return True
            # Some builds expose swagger before status — treat 2xx as alive.
            if 200 <= resp.status_code < 300:
                return True
    except Exception as e:
        logger.debug("StirlingPDF unavailable: %s", e)
    try:
        with httpx.Client(timeout=5.0, headers=_headers()) as client:
            resp = client.get(f"{_base_url()}/swagger-ui/index.html")
            return resp.status_code == 200
    except Exception as e:
        logger.debug("StirlingPDF swagger probe failed: %s", e)
    return False


_COMPOSE_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def ensure_available(timeout: float = 30.0) -> bool:
    """Start StirlingPDF container on demand if not running, wait until ready.

    Returns True if StirlingPDF is available (already running or just started).
    Returns False if it couldn't be started within timeout.
    """
    if is_available():
        return True

    logger.info("StirlingPDF not running — starting on demand...")
    compose_cmd: list[str] | None = None
    for cmd in (
        ["podman", "compose", "up", "-d", "stirling-pdf"],
        ["podman-compose", "up", "-d", "stirling-pdf"],
        ["docker", "compose", "up", "-d", "stirling-pdf"],
    ):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(_COMPOSE_PROJECT_ROOT),
            )
            if result.returncode == 0:
                compose_cmd = cmd
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if compose_cmd is None:
        logger.warning("StirlingPDF start failed — no compose backend available")
        return False

    logger.info("StirlingPDF container starting via %s...", compose_cmd[0])
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if is_available():
            logger.info("StirlingPDF ready after %.1fs", time.monotonic() - start)
            return True
        time.sleep(1.0)

    logger.warning("StirlingPDF didn't become ready within %ds", int(timeout))
    return False


def _post_file(
    endpoint: str,
    *,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
    filename: str = "upload.pdf",
    extra_fields: dict[str, str] | None = None,
) -> bytes:
    url = f"{_base_url()}{endpoint}"
    fields = dict(extra_fields or {})
    timeout = httpx.Timeout(STIRLING_PDF_TIMEOUT_SECONDS)

    if file_path is not None:
        path = Path(file_path)
        with path.open("rb") as fh:
            files = {"fileInput": (path.name, fh, "application/pdf")}
            with httpx.Client(timeout=timeout, headers=_headers()) as client:
                resp = client.post(url, files=files, data=fields)
    elif file_bytes is not None:
        files = {"fileInput": (filename, file_bytes, "application/pdf")}
        with httpx.Client(timeout=timeout, headers=_headers()) as client:
            resp = client.post(url, files=files, data=fields)
    else:
        raise ValueError("file_path or file_bytes required")

    resp.raise_for_status()
    return resp.content


def extract_text(
    *,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
    filename: str = "upload.pdf",
) -> str:
    """Extract plain text from a PDF via StirlingPDF."""
    raw = _post_file(
        _CONVERT_PDF_TEXT,
        file_path=file_path,
        file_bytes=file_bytes,
        filename=filename,
    )
    return raw.decode("utf-8", errors="replace")


def ocr_pdf(
    *,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
    filename: str = "upload.pdf",
) -> bytes:
    """Run OCR on a PDF; returns searchable PDF bytes."""
    return _post_file(
        _OCR_PDF,
        file_path=file_path,
        file_bytes=file_bytes,
        filename=filename,
        extra_fields={"languages": STIRLING_PDF_OCR_LANGUAGES},
    )


def ocr_then_extract(
    *,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
    filename: str = "upload.pdf",
) -> str:
    """OCR a scanned PDF, then extract text from the OCR output."""
    ocr_bytes = ocr_pdf(file_path=file_path, file_bytes=file_bytes, filename=filename)
    return extract_text(file_bytes=ocr_bytes, filename=f"ocr_{filename}")


def html_to_pdf(html_content: str, filename: str = "report.html") -> bytes:
    """Convert HTML string to PDF bytes via StirlingPDF."""
    return _post_file(
        _CONVERT_HTML_PDF,
        file_bytes=html_content.encode("utf-8"),
        filename=filename,
    )
