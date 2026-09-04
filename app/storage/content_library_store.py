import json
import random
import sqlite3
from pathlib import Path
from typing import Optional

from app.models import Channel, ContentLibraryEntry, ContentStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS content_library (
    creative_id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    variant_label TEXT NOT NULL,
    template_name TEXT NOT NULL DEFAULT 'Untitled Template',
    template_id TEXT NOT NULL DEFAULT '',
    content_tag TEXT NOT NULL DEFAULT '',
    content_json TEXT NOT NULL,
    asset_ids TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_COLUMNS = (
    "creative_id",
    "topic_id",
    "campaign_id",
    "channel",
    "variant_label",
    "template_name",
    "template_id",
    "content_tag",
    "content_json",
    "asset_ids",
    "status",
    "created_at",
    "request_json",
)


class ContentLibraryStore:
    """Raw sqlite3 + hand-written SQL, not an ORM. The schema mirrors
    ContentLibraryEntry field-for-field, so a later move to Postgres is
    swapping the connection (and a couple of SQL dialect quirks like a
    native JSON column) rather than redesigning anything.
    """

    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        conn = self._connect()
        try:
            conn.execute(SCHEMA)
            self._ensure_column(conn, "template_name", "template_name TEXT NOT NULL DEFAULT 'Untitled Template'")
            added_template_id = self._ensure_column(conn, "template_id", "template_id TEXT NOT NULL DEFAULT ''")
            if added_template_id:
                self._backfill_template_ids(conn)
            self._ensure_column(conn, "content_tag", "content_tag TEXT NOT NULL DEFAULT ''")
            # Nullable (no DEFAULT ''): unlike the other backfilled columns
            # this one's absence is meaningful -- it distinguishes "saved
            # before Edit existed" (None, edit falls back to defaults) from
            # "saved with nothing to say" (won't happen in practice, but
            # NULL vs '' keeps the distinction possible).
            self._ensure_column(conn, "request_json", "request_json TEXT")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, column: str, ddl: str) -> bool:
        # A DB created before this column existed won't have it --
        # CREATE TABLE IF NOT EXISTS is a no-op on an existing table, so add
        # it by hand. Returns True if the column was just added, so a caller
        # can backfill existing rows only when that's actually needed.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(content_library)")}
        if column in columns:
            return False
        conn.execute(f"ALTER TABLE content_library ADD COLUMN {ddl}")
        return True

    @classmethod
    def _backfill_template_ids(cls, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT creative_id, channel FROM content_library WHERE template_id = ''").fetchall()
        if not rows:
            return
        used = {r[0] for r in conn.execute("SELECT template_id FROM content_library WHERE template_id != ''")}
        for creative_id, channel_value in rows:
            template_id = cls._pick_unique_id(channel_value, used)
            used.add(template_id)
            conn.execute("UPDATE content_library SET template_id = ? WHERE creative_id = ?", (template_id, creative_id))

    _TEMPLATE_ID_PREFIXES = {"email": "E", "whatsapp": "WA", "brochure": "BR"}

    @classmethod
    def _random_template_id(cls, channel_value: str) -> str:
        # E for email, WA for whatsapp, BR for brochure -- matches the
        # channel at a glance without having to open the card.
        prefix = cls._TEMPLATE_ID_PREFIXES.get(channel_value, "X")
        length = random.choice([4, 5])
        digits = random.randint(10 ** (length - 1), 10**length - 1)
        return f"{prefix}{digits}"

    @classmethod
    def _pick_unique_id(cls, channel_value: str, used: set) -> str:
        for _ in range(50):
            candidate = cls._random_template_id(channel_value)
            if candidate not in used:
                return candidate
        raise RuntimeError("Could not generate a unique template_id")

    def generate_template_id(self, channel: Channel) -> str:
        for _ in range(50):
            candidate = self._random_template_id(channel.value)
            if not self.template_id_exists(candidate):
                return candidate
        raise RuntimeError("Could not generate a unique template_id")

    def template_id_exists(self, template_id: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute("SELECT 1 FROM content_library WHERE template_id = ?", (template_id,)).fetchone()
        finally:
            conn.close()
        return row is not None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def save(self, entry: ContentLibraryEntry) -> None:
        conn = self._connect()
        try:
            conn.execute(
                f"INSERT OR REPLACE INTO content_library ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * len(_COLUMNS))})",
                (
                    entry.creative_id,
                    entry.topic_id,
                    entry.campaign_id,
                    entry.channel.value,
                    entry.variant_label,
                    entry.template_name,
                    entry.template_id,
                    entry.content_tag,
                    json.dumps(entry.content_json),
                    json.dumps(entry.asset_ids),
                    entry.status.value,
                    entry.created_at.isoformat(),
                    json.dumps(entry.request_json) if entry.request_json is not None else None,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, creative_id: str) -> Optional[ContentLibraryEntry]:
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM content_library WHERE creative_id = ?", (creative_id,)
            ).fetchone()
        finally:
            conn.close()
        return self._row_to_entry(row) if row else None

    def rename_template_name(self, creative_id: str, template_name: str) -> Optional[ContentLibraryEntry]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "UPDATE content_library SET template_name = ? WHERE creative_id = ?", (template_name, creative_id)
            )
            conn.commit()
        finally:
            conn.close()
        return self.get(creative_id) if cursor.rowcount > 0 else None

    def delete(self, creative_id: str) -> bool:
        conn = self._connect()
        try:
            cursor = conn.execute("DELETE FROM content_library WHERE creative_id = ?", (creative_id,))
            conn.commit()
        finally:
            conn.close()
        return cursor.rowcount > 0

    def list_by_topic(self, topic_id: str, channel: Optional[Channel] = None) -> list[ContentLibraryEntry]:
        return self.list_by_topics([topic_id], channel=channel)

    def list_by_topics(self, topic_ids: list[str], channel: Optional[Channel] = None) -> list[ContentLibraryEntry]:
        """Empty topic_ids means "no topic filter" -- the Browse Library page
        uses this to show content across every topic until the user actively
        selects one or more topic chips to narrow it down.
        """
        query = f"SELECT {', '.join(_COLUMNS)} FROM content_library"
        clauses: list[str] = []
        params: list[str] = []
        if topic_ids:
            clauses.append(f"topic_id IN ({', '.join('?' * len(topic_ids))})")
            params.extend(topic_ids)
        if channel is not None:
            clauses.append("channel = ?")
            params.append(channel.value)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        conn = self._connect()
        try:
            rows = conn.execute(query, params).fetchall()
        finally:
            conn.close()
        return [self._row_to_entry(r) for r in rows]

    @staticmethod
    def _row_to_entry(row) -> ContentLibraryEntry:
        (
            creative_id,
            topic_id,
            campaign_id,
            channel,
            variant_label,
            template_name,
            template_id,
            content_tag,
            content_json,
            asset_ids,
            status,
            created_at,
            request_json,
        ) = row
        return ContentLibraryEntry(
            creative_id=creative_id,
            topic_id=topic_id,
            campaign_id=campaign_id,
            channel=Channel(channel),
            variant_label=variant_label,
            template_name=template_name,
            template_id=template_id,
            content_tag=content_tag,
            content_json=json.loads(content_json),
            asset_ids=json.loads(asset_ids),
            status=ContentStatus(status),
            created_at=created_at,
            request_json=json.loads(request_json) if request_json is not None else None,
        )
