"""Tests for cloud privacy helpers."""

from src.agent.cloud.cloud_privacy import cloud_user_fingerprint


def test_cloud_user_fingerprint_opaque():
    a = cloud_user_fingerprint("thread-abc")
    b = cloud_user_fingerprint("thread-xyz")
    assert a != b
    assert "thread-abc" not in (a or "")
    assert len(a or "") == 20


def test_cloud_user_fingerprint_none():
    assert cloud_user_fingerprint(None) is None
