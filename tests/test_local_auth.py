"""Tests for loopback notebook run token and CORS helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.local_auth import (
    cors_allowed_origins,
    init_local_run_token,
    is_loopback_client,
    verify_local_run_token,
)
from src.api.server import app

client = TestClient(app)


def test_cors_origins_restrict_localhost():
    origins = cors_allowed_origins()
    assert "http://127.0.0.1:5173" in origins
    assert "*" not in origins


def test_notebook_run_requires_token():
    resp = client.post(
        "/api/notebook/run",
        json={"code": "print(1)", "project_id": "default", "thread_id": "t"},
    )
    assert resp.status_code == 401


def test_notebook_run_with_token():
    token_resp = client.get("/api/local-run-token")
    assert token_resp.status_code == 200
    token = token_resp.json()["token"]
    resp = client.post(
        "/api/notebook/run",
        headers={"X-Owlynn-Run-Token": token},
        json={
            "code": "print('hello-api')",
            "project_id": "default",
            "thread_id": "test-notebook-api",
        },
    )
    assert resp.status_code == 200
    assert "hello-api" in resp.json()["output"]


def test_is_loopback_client():
    req = MagicMock()
    req.client.host = "127.0.0.1"
    assert is_loopback_client(req) is True
    req.client.host = "8.8.8.8"
    assert is_loopback_client(req) is False


def test_verify_local_run_token_rejects_bad_token():
    from fastapi import FastAPI

    mini = FastAPI()
    init_local_run_token(mini)
    req = MagicMock()
    req.app = mini
    req.client.host = "127.0.0.1"
    with pytest.raises(Exception):
        verify_local_run_token(req, "wrong-token")
