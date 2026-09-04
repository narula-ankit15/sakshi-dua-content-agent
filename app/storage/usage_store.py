import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models import UsageSummary

# The purpose string UsageTrackingImageClient records AI hero-image
# generation calls under -- the canonical spelling lives here since this is
# the module that has to interpret it (see summary()'s images_today calc).
IMAGE_GENERATION_PURPOSE = "hero_image_generation"


class UsageStore:
    """Tracks every Gemini API call this app itself makes, so 'requests
    today' is real and locally verifiable. Gemini's API has no endpoint that
    exposes your account's actual quota/usage, so this can only ever
    reflect requests made through this app, compared against a cap you
    supply yourself (`set_daily_cap`), never a live pull from Google.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gemini_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    requested_at TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record(self, purpose: str, status: str = "ok") -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO gemini_requests (requested_at, purpose, status) VALUES (?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), purpose, status),
            )

    def count_today(self, purpose: str) -> int:
        # Same UTC-day boundary as summary() -- used to enforce a hard cap
        # (e.g. AI image generation) *before* a call is made, not just to
        # report on it afterwards.
        start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM gemini_requests WHERE requested_at >= ? AND purpose = ?",
                (start_of_day, purpose),
            ).fetchone()
        return row["c"] if row else 0

    def set_daily_cap(self, cap: Optional[int]) -> None:
        with self._connect() as conn:
            if cap is None:
                conn.execute("DELETE FROM usage_settings WHERE key = 'daily_cap'")
            else:
                conn.execute(
                    "INSERT INTO usage_settings (key, value) VALUES ('daily_cap', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(cap),),
                )

    @staticmethod
    def _read_daily_cap(conn: sqlite3.Connection) -> Optional[int]:
        row = conn.execute("SELECT value FROM usage_settings WHERE key = 'daily_cap'").fetchone()
        return int(row["value"]) if row else None

    def summary(self, image_generation_daily_limit: Optional[int] = None) -> UsageSummary:
        # UTC day boundary -- simplest unambiguous definition of "today"
        # for a backend with no notion of the browser's timezone.
        start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT purpose, status, requested_at FROM gemini_requests WHERE requested_at >= ? ORDER BY requested_at",
                (start_of_day,),
            ).fetchall()
            cap = self._read_daily_cap(conn)

        by_purpose: dict[str, int] = {}
        rate_limited = False
        last_at: Optional[str] = None
        for row in rows:
            by_purpose[row["purpose"]] = by_purpose.get(row["purpose"], 0) + 1
            if row["status"] == "rate_limited":
                rate_limited = True
            last_at = row["requested_at"]

        total = len(rows)
        remaining = max(0, cap - total) if cap is not None else None
        images_today = by_purpose.get(IMAGE_GENERATION_PURPOSE, 0)
        images_remaining = (
            max(0, image_generation_daily_limit - images_today) if image_generation_daily_limit is not None else None
        )

        return UsageSummary(
            requests_today=total,
            rate_limited_today=rate_limited,
            daily_cap=cap,
            remaining_today=remaining,
            requests_by_purpose=by_purpose,
            last_request_at=datetime.fromisoformat(last_at) if last_at else None,
            images_generated_today=images_today,
            image_generation_daily_limit=image_generation_daily_limit,
            images_remaining_today=images_remaining,
        )
