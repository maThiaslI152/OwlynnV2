"""Loopback-only local API token for privileged routes (e.g. notebook run)."""

from __future__ import annotations

import os
import secrets
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from fastapi import FastAPI

RUN_TOKEN_HEADER = "X-Owlynn-Run-Token"

_DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
)


def cors_allowed_origins() -> list[str]:
    raw = os.getenv("OWLYNN_CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(_DEFAULT_CORS_ORIGINS)


def init_local_run_token(app: FastAPI) -> str:
    token = os.getenv("OWLYNN_LOCAL_RUN_TOKEN", "").strip()
    if not token:
        token = secrets.token_urlsafe(32)
    app.state.local_run_token = token
    return token


def get_local_run_token(app: FastAPI) -> str:
    token = getattr(app.state, "local_run_token", None)
    if not token:
        return init_local_run_token(app)
    return token


def is_loopback_client(request: Request) -> bool:
    if not request.client:
        return False
    host = (request.client.host or "").lower()
    import ipaddress

    if host == "testclient" or host == "localhost":
        return True

    try:
        ip = ipaddress.ip_address(host)
        # Only trust true loopback (127.x.x.x / ::1).
        # Removing ip.is_private — the RFC-1918 private range (10.x, 172.16.x, 192.168.x)
        # could allow access from VPN peers or shared-network devices if the server
        # were ever misconfigured to bind on 0.0.0.0 instead of 127.0.0.1.
        return ip.is_loopback
    except ValueError:
        return False


def verify_local_run_token(request: Request, token: str | None) -> None:
    """Reject missing/invalid tokens or non-loopback callers."""
    if not is_loopback_client(request):
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only available from localhost.",
        )
    expected = get_local_run_token(request.app)
    if not token:
        raise HTTPException(status_code=401, detail="Missing local run token.")
    if not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid local run token.")
