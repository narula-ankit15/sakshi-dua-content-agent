import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.models import EmailSendRecord


class EmailSendStore:
    """Records who a saved email template has actually been sent to.
    Shares the content-library SQLite file (a send record only ever makes
    sense attached to a creative_id there) rather than its own db file.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS email_sends (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creative_id TEXT NOT NULL,
                    to_email TEXT NOT NULL,
                    sent_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_email_sends_creative_id ON email_sends (creative_id)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record(self, creative_id: str, to_email: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO email_sends (creative_id, to_email, sent_at) VALUES (?, ?, ?)",
                (creative_id, to_email, datetime.now(timezone.utc).isoformat()),
            )

    def list_for_creative(self, creative_id: str) -> list[EmailSendRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT to_email, sent_at FROM email_sends WHERE creative_id = ? ORDER BY sent_at DESC",
                (creative_id,),
            ).fetchall()
        return [EmailSendRecord(to_email=row["to_email"], sent_at=row["sent_at"]) for row in rows]

    def counts_for_creatives(self, creative_ids: list[str]) -> dict[str, int]:
        """One query for the whole library grid, not one per card -- {creative_id: count},
        with entries that have zero sends simply absent (caller treats a
        missing key as 0)."""
        if not creative_ids:
            return {}
        with self._connect() as conn:
            placeholders = ", ".join("?" * len(creative_ids))
            rows = conn.execute(
                f"SELECT creative_id, COUNT(*) AS n FROM email_sends WHERE creative_id IN ({placeholders}) "
                "GROUP BY creative_id",
                creative_ids,
            ).fetchall()
        return {row["creative_id"]: row["n"] for row in rows}
