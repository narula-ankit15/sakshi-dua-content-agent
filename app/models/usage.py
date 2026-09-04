from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UsageSummary(BaseModel):
    """Reflects requests this app itself made to Gemini, not a live pull
    from Google -- the Gemini API has no endpoint that exposes your
    account's actual quota/usage, so `daily_cap` is a number you supply
    yourself (see PUT /usage/cap) rather than something fetched.
    """

    requests_today: int
    rate_limited_today: bool
    daily_cap: Optional[int] = None
    remaining_today: Optional[int] = None
    requests_by_purpose: dict[str, int]
    last_request_at: Optional[datetime] = None
    # AI hero-image generation has its own fixed daily ceiling (see
    # Settings.max_daily_ai_images), separate from the user-configurable
    # overall daily_cap above -- broken out here so it's visible on its own.
    images_generated_today: int = 0
    image_generation_daily_limit: Optional[int] = None
    images_remaining_today: Optional[int] = None
