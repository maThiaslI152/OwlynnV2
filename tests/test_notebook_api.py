"""Tests for POST /api/notebook/run."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


def test_notebook_run_api_executes_code():
    resp = client.post(
        "/api/notebook/run",
        json={
            "code": "print('hello-api')",
            "project_id": "default",
            "thread_id": "test-notebook-api",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "hello-api" in data["output"]


def test_notebook_run_api_rejects_empty_code():
    resp = client.post(
        "/api/notebook/run",
        json={"code": "", "project_id": "default", "thread_id": "test-empty"},
    )
    assert resp.status_code == 422
