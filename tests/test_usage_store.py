from datetime import datetime, timedelta, timezone

from app.storage.usage_store import IMAGE_GENERATION_PURPOSE, UsageStore


def test_summary_on_empty_store_is_all_zero(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))

    summary = store.summary()

    assert summary.requests_today == 0
    assert summary.rate_limited_today is False
    assert summary.daily_cap is None
    assert summary.remaining_today is None
    assert summary.requests_by_purpose == {}
    assert summary.last_request_at is None


def test_record_counts_by_purpose_and_status(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))
    store.record("content_generation", status="ok")
    store.record("content_generation", status="ok")
    store.record("embedding", status="ok")
    store.record("content_generation", status="rate_limited")

    summary = store.summary()

    assert summary.requests_today == 4
    assert summary.requests_by_purpose == {"content_generation": 3, "embedding": 1}
    assert summary.rate_limited_today is True
    assert summary.last_request_at is not None


def test_daily_cap_can_be_set_cleared_and_computes_remaining(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))
    store.record("content_generation")
    store.record("content_generation")

    store.set_daily_cap(10)
    summary = store.summary()
    assert summary.daily_cap == 10
    assert summary.remaining_today == 8

    store.set_daily_cap(None)
    summary = store.summary()
    assert summary.daily_cap is None
    assert summary.remaining_today is None


def test_remaining_never_goes_negative_when_over_cap(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))
    for _ in range(5):
        store.record("content_generation")
    store.set_daily_cap(3)

    summary = store.summary()

    assert summary.requests_today == 5
    assert summary.remaining_today == 0


def test_count_today_counts_only_matching_purpose_from_today(tmp_path):
    db_path = str(tmp_path / "usage.db")
    store = UsageStore(db_path)
    store.record(IMAGE_GENERATION_PURPOSE, status="ok")
    store.record(IMAGE_GENERATION_PURPOSE, status="error")
    store.record("content_generation", status="ok")

    assert store.count_today(IMAGE_GENERATION_PURPOSE) == 2
    assert store.count_today("content_generation") == 1
    assert store.count_today("some_other_purpose") == 0


def test_summary_reports_image_generation_breakdown_against_a_given_limit(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))
    store.record(IMAGE_GENERATION_PURPOSE, status="ok")
    store.record(IMAGE_GENERATION_PURPOSE, status="ok")
    store.record("content_generation", status="ok")

    summary = store.summary(image_generation_daily_limit=10)

    assert summary.images_generated_today == 2
    assert summary.image_generation_daily_limit == 10
    assert summary.images_remaining_today == 8


def test_summary_image_fields_default_to_zero_and_none_without_a_limit(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))

    summary = store.summary()

    assert summary.images_generated_today == 0
    assert summary.image_generation_daily_limit is None
    assert summary.images_remaining_today is None


def test_summary_images_remaining_never_goes_negative_when_over_limit(tmp_path):
    store = UsageStore(str(tmp_path / "usage.db"))
    for _ in range(12):
        store.record(IMAGE_GENERATION_PURPOSE, status="ok")

    summary = store.summary(image_generation_daily_limit=10)

    assert summary.images_generated_today == 12
    assert summary.images_remaining_today == 0


def test_requests_from_before_today_are_not_counted(tmp_path):
    db_path = str(tmp_path / "usage.db")
    store = UsageStore(db_path)
    store.record("content_generation")

    # Backdate the one real row to yesterday, directly via sqlite, to
    # simulate a request made before the UTC day boundary.
    import sqlite3

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE gemini_requests SET requested_at = ?", (yesterday,))
    conn.commit()
    conn.close()

    summary = store.summary()

    assert summary.requests_today == 0
