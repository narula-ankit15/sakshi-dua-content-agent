import pytest

from app.agents.usage_tracking_client import (
    ImageGenerationLimitExceeded,
    UsageTrackingImageClient,
    UsageTrackingLLMClient,
)
from app.storage.usage_store import UsageStore


class FakeLLMClient:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    def generate_json(self, *, system: str, prompt: str) -> dict:
        if self._error:
            raise self._error
        return self._result


def test_llm_client_records_ok_and_passes_result_through(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))
    inner = FakeLLMClient(result={"hi": "there"})
    client = UsageTrackingLLMClient(inner, store, purpose="content_generation")

    result = client.generate_json(system="sys", prompt="prompt")

    assert result == {"hi": "there"}
    summary = store.summary()
    assert summary.requests_today == 1
    assert summary.requests_by_purpose == {"content_generation": 1}
    assert summary.rate_limited_today is False


def test_llm_client_records_rate_limited_and_reraises(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))
    inner = FakeLLMClient(error=RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded"))
    client = UsageTrackingLLMClient(inner, store, purpose="content_generation")

    with pytest.raises(RuntimeError):
        client.generate_json(system="sys", prompt="prompt")

    summary = store.summary()
    assert summary.requests_today == 1
    assert summary.rate_limited_today is True


def test_llm_client_records_generic_error_as_error_not_rate_limited(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))
    inner = FakeLLMClient(error=ValueError("invalid json"))
    client = UsageTrackingLLMClient(inner, store, purpose="content_generation")

    with pytest.raises(ValueError):
        client.generate_json(system="sys", prompt="prompt")

    summary = store.summary()
    assert summary.requests_today == 1
    assert summary.rate_limited_today is False


class FakeImageGenClient:
    def __init__(self, result: bytes = b"png-bytes", error=None):
        self._result = result
        self._error = error
        self.calls = 0

    def generate_image(self, prompt: str) -> bytes:
        self.calls += 1
        if self._error:
            raise self._error
        return self._result


def test_image_client_records_ok_and_passes_bytes_through(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))
    inner = FakeImageGenClient(result=b"real-bytes")
    client = UsageTrackingImageClient(inner, store, purpose="hero_image_generation", daily_limit=10)

    result = client.generate_image("a prompt")

    assert result == b"real-bytes"
    assert store.summary().requests_by_purpose == {"hero_image_generation": 1}


def test_image_client_blocks_the_call_once_daily_limit_is_reached(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))
    inner = FakeImageGenClient()
    client = UsageTrackingImageClient(inner, store, purpose="hero_image_generation", daily_limit=2)

    client.generate_image("p1")
    client.generate_image("p2")
    with pytest.raises(ImageGenerationLimitExceeded):
        client.generate_image("p3")

    # The blocked 3rd call never reached the inner client, and wasn't
    # recorded as a real request (only the 2 real calls were).
    assert inner.calls == 2
    assert store.summary().requests_by_purpose == {"hero_image_generation": 2}


def test_image_client_with_no_daily_limit_never_blocks(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))
    inner = FakeImageGenClient()
    client = UsageTrackingImageClient(inner, store, purpose="hero_image_generation", daily_limit=None)

    for _ in range(15):
        client.generate_image("p")

    assert inner.calls == 15


def test_image_client_records_rate_limited_error_and_reraises(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))
    inner = FakeImageGenClient(error=RuntimeError("429 RESOURCE_EXHAUSTED"))
    client = UsageTrackingImageClient(inner, store, purpose="hero_image_generation", daily_limit=10)

    with pytest.raises(RuntimeError):
        client.generate_image("p")

    summary = store.summary()
    assert summary.rate_limited_today is True
    assert summary.requests_by_purpose == {"hero_image_generation": 1}
