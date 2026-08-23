"""Tests for vendored offline Chart.js static serving."""

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


class _DummyWatcher:
    def stop(self):
        return None

    def join(self):
        return None


class _DummyAgent:
    async def astream_events(self, _input_data, config=None, version="v2"):
        if False:
            yield {}


def test_chartjs_vendor_file_exists():
    root = Path(__file__).resolve().parents[1]
    chart_js = root / "assets" / "vendor" / "chart.umd.min.js"
    version_file = root / "assets" / "vendor" / "VERSION"
    assert chart_js.is_file()
    assert chart_js.stat().st_size > 100_000
    assert version_file.read_text(encoding="utf-8").strip() == "4.4.1"


def test_vendor_chartjs_endpoint_returns_200():
    from src.api.server import app

    with (
        patch("src.api.server.init_agent", autospec=True) as init_agent_mock,
        patch("src.api.server.start_watcher", autospec=True) as watcher_mock,
    ):
        init_agent_mock.return_value = _DummyAgent()
        watcher_mock.return_value = _DummyWatcher()

        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.get("/vendor/chart.umd.min.js")
            assert resp.status_code == 200
            assert "Chart" in resp.text or len(resp.content) > 100_000
            assert "javascript" in resp.headers.get("content-type", "").lower()
