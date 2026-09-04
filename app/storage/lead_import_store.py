import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models import LeadImportBatch


class LeadImportStore:
    """Records each CSV upload so the Leads page can show a processing
    history, not just the leads that came out of it. Shares the leads
    sqlite file (a separate table) rather than a second db path/volume
    entry -- this is just an audit trail alongside that data, not a
    distinct domain.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lead_import_batches (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    imported_count INTEGER NOT NULL,
                    skipped_json TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record(self, *, filename: str, imported_count: int, skipped: list[dict]) -> LeadImportBatch:
        batch = LeadImportBatch(
            id=f"import-{uuid.uuid4().hex[:12]}",
            created_at=datetime.now(timezone.utc),
            filename=filename,
            imported_count=imported_count,
            skipped=skipped,
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO lead_import_batches (id, created_at, filename, imported_count, skipped_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (batch.id, batch.created_at.isoformat(), batch.filename, batch.imported_count, json.dumps(batch.skipped)),
            )
        return batch

    def list(self, limit: int = 20) -> list[LeadImportBatch]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, filename, imported_count, skipped_json FROM lead_import_batches "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            LeadImportBatch(
                id=r["id"], created_at=r["created_at"], filename=r["filename"],
                imported_count=r["imported_count"], skipped=json.loads(r["skipped_json"]),
            )
            for r in rows
        ]

    def get(self, batch_id: str) -> Optional[LeadImportBatch]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, created_at, filename, imported_count, skipped_json FROM lead_import_batches WHERE id = ?",
                (batch_id,),
            ).fetchone()
        if row is None:
            return None
        return LeadImportBatch(
            id=row["id"], created_at=row["created_at"], filename=row["filename"],
            imported_count=row["imported_count"], skipped=json.loads(row["skipped_json"]),
        )
