import json
import re
import sqlite3

from app.models import Channel, ContentLibraryEntry, ContentStatus, EmailDraft
from app.storage.content_library_store import ContentLibraryStore


def _pre_template_name_schema(db_path):
    # Mirrors the table shape before template_name/template_id existed, with
    # one row already in it -- simulates a real DB from before this migration.
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE content_library (
            creative_id TEXT PRIMARY KEY,
            topic_id TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            variant_label TEXT NOT NULL,
            content_json TEXT NOT NULL,
            asset_ids TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO content_library VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "comm-impact-email-camp-x-abc123",
            "comm-impact",
            "camp-x",
            "email",
            "primary",
            json.dumps({"subject_lines": ["Hi"], "html_body": "<p>hi</p>", "referenced_asset_ids": []}),
            json.dumps([]),
            "approved",
            "2026-01-01T00:00:00",
        ),
    )
    conn.commit()
    conn.close()


def _pre_template_id_schema(db_path):
    # Mirrors the table shape after template_name shipped but before
    # template_id existed -- the state of a real DB mid-way through this
    # feature history.
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE content_library (
            creative_id TEXT PRIMARY KEY,
            topic_id TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            variant_label TEXT NOT NULL,
            template_name TEXT NOT NULL DEFAULT 'Untitled Template',
            content_json TEXT NOT NULL,
            asset_ids TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.executemany(
        "INSERT INTO content_library VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "comm-impact-email-camp-x-abc123",
                "comm-impact",
                "camp-x",
                "email",
                "primary",
                "Launch Email",
                json.dumps({"subject_lines": ["Hi"], "html_body": "<p>hi</p>", "referenced_asset_ids": []}),
                json.dumps([]),
                "approved",
                "2026-01-01T00:00:00",
            ),
            (
                "comm-impact-whatsapp-camp-x-def456",
                "comm-impact",
                "camp-x",
                "whatsapp",
                "primary",
                "Launch WhatsApp",
                json.dumps({"message_variants": ["Hi"], "cta": None, "image_asset_id": None}),
                json.dumps([]),
                "approved",
                "2026-01-01T00:00:01",
            ),
        ],
    )
    conn.commit()
    conn.close()


def test_opening_a_pre_migration_db_backfills_template_name(tmp_path):
    db_path = tmp_path / "content_library.db"
    _pre_template_name_schema(str(db_path))

    store = ContentLibraryStore(str(db_path))

    entry = store.get("comm-impact-email-camp-x-abc123")
    assert entry is not None
    assert entry.template_name == "Untitled Template"
    assert re.fullmatch(r"E\d{4,5}", entry.template_id)
    assert entry.content_tag == ""

    # New saves against the migrated DB work normally too.
    store.save(
        ContentLibraryEntry(
            creative_id="comm-impact-email-camp-x-def456",
            topic_id="comm-impact",
            campaign_id="camp-x",
            channel=Channel.EMAIL,
            variant_label="primary",
            template_name="Diwali Offer",
            template_id="E1234",
            content_json=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>").model_dump(mode="json"),
            asset_ids=[],
            status=ContentStatus.APPROVED,
        )
    )
    assert store.get("comm-impact-email-camp-x-def456").template_name == "Diwali Offer"


def test_opening_a_db_with_template_name_but_no_template_id_backfills_with_correct_prefix(tmp_path):
    db_path = tmp_path / "content_library.db"
    _pre_template_id_schema(str(db_path))

    store = ContentLibraryStore(str(db_path))

    email_entry = store.get("comm-impact-email-camp-x-abc123")
    whatsapp_entry = store.get("comm-impact-whatsapp-camp-x-def456")
    # template_name (already present) must survive the migration untouched.
    assert email_entry.template_name == "Launch Email"
    assert whatsapp_entry.template_name == "Launch WhatsApp"
    assert re.fullmatch(r"E\d{4,5}", email_entry.template_id)
    assert re.fullmatch(r"WA\d{4,5}", whatsapp_entry.template_id)
    assert email_entry.template_id != whatsapp_entry.template_id
    # content_tag is even newer than template_id -- this DB predates it too.
    assert email_entry.content_tag == ""

    # New saves against the migrated DB can set content_tag normally.
    store.save(
        ContentLibraryEntry(
            creative_id="comm-impact-email-camp-x-ghi789",
            topic_id="comm-impact",
            campaign_id="camp-x",
            channel=Channel.EMAIL,
            variant_label="primary",
            template_name="Diwali Offer",
            template_id="E5678",
            content_tag="promotional_communication",
            content_json=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>").model_dump(mode="json"),
            asset_ids=[],
            status=ContentStatus.APPROVED,
        )
    )
    assert store.get("comm-impact-email-camp-x-ghi789").content_tag == "promotional_communication"


def _pre_request_json_schema(db_path):
    # Mirrors the table shape before request_json existed -- one real row
    # already in it, the state of a DB from before Edit shipped.
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE content_library (
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
        )
        """
    )
    conn.execute(
        "INSERT INTO content_library VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "comm-impact-email-camp-x-abc123",
            "comm-impact",
            "camp-x",
            "email",
            "primary",
            "Launch Email",
            "E1234",
            "promotional_communication",
            json.dumps({"subject_lines": ["Hi"], "html_body": "<p>hi</p>", "referenced_asset_ids": []}),
            json.dumps([]),
            "approved",
            "2026-01-01T00:00:00",
        ),
    )
    conn.commit()
    conn.close()


def test_opening_a_db_predating_request_json_backfills_it_as_none(tmp_path):
    db_path = tmp_path / "content_library.db"
    _pre_request_json_schema(str(db_path))

    store = ContentLibraryStore(str(db_path))

    entry = store.get("comm-impact-email-camp-x-abc123")
    assert entry is not None
    assert entry.request_json is None
    # A pre-existing draft saved before request_json existed just can't be
    # edited (Edit falls back to defaults) -- everything else survives.
    assert entry.template_name == "Launch Email"


def test_request_json_round_trips_through_sqlite(tmp_path):
    store = ContentLibraryStore(str(tmp_path / "content_library.db"))
    brief = {"topic_id": "comm-impact", "campaign_brief": {"purpose": "promo_sale"}}
    store.save(
        ContentLibraryEntry(
            creative_id="comm-impact-email-camp-x-abc123",
            topic_id="comm-impact",
            campaign_id="camp-x",
            channel=Channel.EMAIL,
            variant_label="primary",
            content_json=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>").model_dump(mode="json"),
            asset_ids=[],
            status=ContentStatus.APPROVED,
            request_json=brief,
        )
    )

    assert store.get("comm-impact-email-camp-x-abc123").request_json == brief


def test_generate_template_id_uses_brochure_prefix(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))

    template_id = store.generate_template_id(Channel.BROCHURE)

    assert re.fullmatch(r"BR\d{4,5}", template_id)


def _save_email(store, topic_id, campaign_id):
    store.save(
        ContentLibraryEntry(
            creative_id=f"{topic_id}-email-{campaign_id}-abc123",
            topic_id=topic_id,
            campaign_id=campaign_id,
            channel=Channel.EMAIL,
            variant_label="primary",
            content_json=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>").model_dump(mode="json"),
            asset_ids=[],
            status=ContentStatus.APPROVED,
        )
    )


def test_list_by_topics_with_empty_list_returns_every_topic(tmp_path):
    store = ContentLibraryStore(str(tmp_path / "content_library.db"))
    _save_email(store, "comm-impact", "camp-1")
    _save_email(store, "negotiation-101", "camp-2")

    results = store.list_by_topics([])

    assert {r.topic_id for r in results} == {"comm-impact", "negotiation-101"}


def test_list_by_topics_filters_to_the_given_topics_only(tmp_path):
    store = ContentLibraryStore(str(tmp_path / "content_library.db"))
    _save_email(store, "comm-impact", "camp-1")
    _save_email(store, "negotiation-101", "camp-2")
    _save_email(store, "leadership-basics", "camp-3")

    results = store.list_by_topics(["comm-impact", "negotiation-101"])

    assert {r.topic_id for r in results} == {"comm-impact", "negotiation-101"}


def test_list_by_topics_combines_with_channel_filter(tmp_path):
    store = ContentLibraryStore(str(tmp_path / "content_library.db"))
    _save_email(store, "comm-impact", "camp-1")

    assert store.list_by_topics(["comm-impact"], channel=Channel.EMAIL) != []
    assert store.list_by_topics(["comm-impact"], channel=Channel.WHATSAPP) == []
