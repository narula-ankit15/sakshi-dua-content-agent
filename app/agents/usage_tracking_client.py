from typing import Optional

from app.agents.llm_client import LLMClient
from app.storage.usage_store import UsageStore


def _is_rate_limit_error(e: Exception) -> bool:
    # Best-effort, SDK-version-agnostic: match on the error text rather than
    # a specific google-genai exception class, since that hierarchy isn't
    # guaranteed stable across SDK versions.
    text = str(e).lower()
    return any(marker in text for marker in ("429", "resource_exhausted", "quota", "rate limit"))


class ImageGenerationLimitExceeded(RuntimeError):
    """Raised instead of calling Gemini once today's AI image-gen cap is
    hit -- distinct from a generic/transient failure so callers can choose
    to surface it clearly instead of silently degrading (see
    Orchestrator._generate_hero_asset).
    """


class UsageTrackingLLMClient:
    """Wraps any LLMClient to record every call in UsageStore -- a thin
    decorator, not a new agent, so no content agent has to know usage is
    being tracked at all.
    """

    def __init__(self, inner: LLMClient, usage_store: UsageStore, purpose: str):
        self._inner = inner
        self._usage_store = usage_store
        self._purpose = purpose

    def generate_json(self, *, system: str, prompt: str) -> dict:
        try:
            result = self._inner.generate_json(system=system, prompt=prompt)
        except Exception as e:
            self._usage_store.record(self._purpose, status="rate_limited" if _is_rate_limit_error(e) else "error")
            raise
        self._usage_store.record(self._purpose, status="ok")
        return result


class UsageTrackingImageClient:
    """Same wrapping idea as UsageTrackingLLMClient, for ImageGenClient --
    image generation is its own (pricier) call type, so it's tracked under
    its own purpose rather than folded into content_generation's count, and
    (unlike text generation) is hard-capped per day since each call is a
    real cost regardless of whether the user keeps the result.
    """

    def __init__(self, inner, usage_store: UsageStore, purpose: str, daily_limit: Optional[int] = None):
        self._inner = inner
        self._usage_store = usage_store
        self._purpose = purpose
        self._daily_limit = daily_limit

    def generate_image(self, prompt: str) -> bytes:
        if self._daily_limit is not None and self._usage_store.count_today(self._purpose) >= self._daily_limit:
            # Blocked before ever reaching Gemini -- nothing to record here,
            # since (unlike the except branch below) no call was actually
            # made.
            raise ImageGenerationLimitExceeded(
                f"Daily AI image generation limit ({self._daily_limit}) reached. Try again tomorrow, or choose "
                "an existing photo instead."
            )
        try:
            result = self._inner.generate_image(prompt)
        except Exception as e:
            self._usage_store.record(self._purpose, status="rate_limited" if _is_rate_limit_error(e) else "error")
            raise
        self._usage_store.record(self._purpose, status="ok")
        return result
