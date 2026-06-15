#!/usr/bin/env python3
"""Manual smoke test for StirlingPDF Podman service (not run in CI)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.config.settings import STIRLING_PDF_API_KEY, STIRLING_PDF_URL
from src.integrations import stirling_pdf


def _podman_running(name: str) -> bool:
    try:
        out = subprocess.run(
            ["podman", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return name in (out.stdout or "")
    except FileNotFoundError:
        return False


def main() -> int:
    base = (STIRLING_PDF_URL or "").rstrip("/")
    if not base:
        print("STIRLING_PDF_URL not configured")
        return 1

    print(f"StirlingPDF URL: {base}")
    if _podman_running("owlynn_stirling_pdf"):
        print("Container owlynn_stirling_pdf: running")
    else:
        print("Container owlynn_stirling_pdf: not found (run: podman compose up -d)")

    headers = {"User-Agent": "Owlynn/1.0"}
    if STIRLING_PDF_API_KEY:
        headers["X-API-KEY"] = STIRLING_PDF_API_KEY

    try:
        with httpx.Client(timeout=10.0, headers=headers) as client:
            resp = client.get(f"{base}/swagger-ui/index.html")
            print(f"Swagger UI: HTTP {resp.status_code}")
    except Exception as e:
        print(f"Swagger UI probe failed: {e}")
        return 1

    if not stirling_pdf.is_available():
        print("StirlingPDF health check failed")
        return 1

    print("StirlingPDF health check: OK")
    print("Smoke test complete (upload a PDF via workspace watcher for full E2E).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
