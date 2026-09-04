import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models import Lead


class LeadStore:
    """Raw sqlite3, same pattern as ContentLibraryStore -- a trainer's
    prospective-client list, independent of any topic/campaign.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    organization TEXT NOT NULL DEFAULT '',
                    remarks TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_name ON leads (name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_organization ON leads (organization)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, *, name: str, phone: str = "", email: str = "", organization: str = "", remarks: str = "") -> Lead:
        lead = Lead(
            id=f"lead-{uuid.uuid4().hex[:12]}",
            name=name,
            phone=phone,
            email=email,
            organization=organization,
            remarks=remarks,
            created_at=datetime.now(timezone.utc),
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO leads (id, name, phone, email, organization, remarks, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (lead.id, lead.name, lead.phone, lead.email, lead.organization, lead.remarks, lead.created_at.isoformat()),
            )
        return lead

    def list(self, search: Optional[str] = None) -> list[Lead]:
        # One open text box that matches across every field a trainer might
        # recall a lead by -- name, org, and phone are the obvious ones, but
        # remarks/email catch it too (e.g. searching a referrer's name that
        # only appears in the remarks text).
        query = "SELECT id, name, phone, email, organization, remarks, created_at FROM leads"
        params: list[str] = []
        if search:
            like = f"%{search}%"
            query += " WHERE name LIKE ? OR phone LIKE ? OR email LIKE ? OR organization LIKE ? OR remarks LIKE ?"
            params = [like, like, like, like, like]
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            Lead(
                id=r["id"], name=r["name"], phone=r["phone"], email=r["email"],
                organization=r["organization"], remarks=r["remarks"], created_at=r["created_at"],
            )
            for r in rows
        ]

    def get(self, lead_id: str) -> Optional[Lead]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name, phone, email, organization, remarks, created_at FROM leads WHERE id = ?",
                (lead_id,),
            ).fetchone()
        if row is None:
            return None
        return Lead(
            id=row["id"], name=row["name"], phone=row["phone"], email=row["email"],
            organization=row["organization"], remarks=row["remarks"], created_at=row["created_at"],
        )

    def update(
        self, lead_id: str, *, name: str, phone: str = "", email: str = "", organization: str = "", remarks: str = ""
    ) -> Optional[Lead]:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE leads SET name = ?, phone = ?, email = ?, organization = ?, remarks = ? WHERE id = ?",
                (name, phone, email, organization, remarks, lead_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get(lead_id)

    def delete(self, lead_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        return cursor.rowcount > 0
