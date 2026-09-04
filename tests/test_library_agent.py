import base64
import re

from app.agents.library_agent import ContentLibraryAgent
from app.models import BrochureContent, BrochureDraft, Channel, ContentStatus, EmailDraft, TopicModule, WhatsAppDraft
from app.storage.brochure_file_store import BrochureFileStore
from app.storage.content_library_store import ContentLibraryStore


def test_save_assigns_creative_id_and_round_trips_through_sqlite(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)

    draft = EmailDraft(subject_lines=["Hi", "Hello"], html_body="<p>hi</p>", referenced_asset_ids=["asset-1"])

    creative_id = agent.save(
        topic_id="comm-impact",
        campaign_id="camp-001",
        channel=Channel.EMAIL,
        variant_label="primary",
        content=draft,
        asset_ids=["asset-1"],
    )

    assert creative_id.startswith("comm-impact-email-camp-001-")

    fetched = store.get(creative_id)
    assert fetched is not None
    assert fetched.topic_id == "comm-impact"
    assert fetched.content_json["subject_lines"] == ["Hi", "Hello"]
    assert fetched.asset_ids == ["asset-1"]


def test_list_by_topic_filters_by_channel(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)

    email_draft = EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>")
    agent.save(
        topic_id="comm-impact", campaign_id="camp-001", channel=Channel.EMAIL,
        variant_label="primary", content=email_draft, asset_ids=[],
    )
    agent.save(
        topic_id="comm-impact", campaign_id="camp-001", channel=Channel.EMAIL,
        variant_label="subject_b", content=email_draft, asset_ids=[],
    )

    results = store.list_by_topic("comm-impact", channel=Channel.EMAIL)
    assert len(results) == 2

    results_other_channel = store.list_by_topic("comm-impact", channel=Channel.WHATSAPP)
    assert results_other_channel == []


def test_get_missing_creative_id_returns_none(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    assert store.get("does-not-exist") is None


def test_delete_removes_entry_and_reports_success(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)

    draft = EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>")
    creative_id = agent.save(
        topic_id="comm-impact", campaign_id="camp-001", channel=Channel.EMAIL,
        variant_label="primary", content=draft, asset_ids=[],
    )

    assert agent.delete(creative_id) is True
    assert store.get(creative_id) is None


def test_delete_missing_creative_id_returns_false(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)

    assert agent.delete("does-not-exist") is False


def test_save_assigns_template_id_with_channel_prefix(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)

    email_id = agent.save(
        topic_id="comm-impact", campaign_id="camp-001", channel=Channel.EMAIL,
        variant_label="primary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[],
    )
    whatsapp_id = agent.save(
        topic_id="comm-impact", campaign_id="camp-001", channel=Channel.WHATSAPP,
        variant_label="primary", content=WhatsAppDraft(message_variants=["Hi", "Hey"]), asset_ids=[],
    )

    email_entry = store.get(email_id)
    whatsapp_entry = store.get(whatsapp_id)
    assert re.fullmatch(r"E\d{4,5}", email_entry.template_id)
    assert re.fullmatch(r"WA\d{4,5}", whatsapp_entry.template_id)
    assert email_entry.template_id != whatsapp_entry.template_id


def test_save_generates_unique_template_ids_across_many_saves(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)

    ids = []
    for i in range(15):
        creative_id = agent.save(
            topic_id="comm-impact", campaign_id=f"camp-{i}", channel=Channel.EMAIL,
            variant_label="primary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[],
        )
        ids.append(store.get(creative_id).template_id)

    assert len(set(ids)) == len(ids)


def test_rename_updates_template_name(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)

    creative_id = agent.save(
        topic_id="comm-impact", campaign_id="camp-001", channel=Channel.EMAIL,
        variant_label="primary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[],
        template_name="Original Name",
    )

    renamed = agent.rename(creative_id, "New Name")
    assert renamed.template_name == "New Name"
    assert store.get(creative_id).template_name == "New Name"


def test_rename_missing_creative_id_returns_none(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)

    assert agent.rename("does-not-exist", "New Name") is None


def _brochure_draft(sample_topic):
    content = BrochureContent(
        hero_title=sample_topic.topic_name,
        hero_tagline=sample_topic.tagline,
        hero_description=sample_topic.hook_description,
        hook_lines=["Why this workshop matters."],
        modules=[TopicModule(**m.model_dump()) for m in sample_topic.modules],
        methodology=sample_topic.methodology,
        outcomes=sample_topic.outcomes,
        closing_line=sample_topic.closing_line,
        positioning_tags=sample_topic.positioning_tags,
    )
    return BrochureDraft(
        content=content,
        html="<html>brochure</html>",
        pdf_base64=base64.b64encode(b"pdf-bytes").decode(),
        png_base64=base64.b64encode(b"png-bytes").decode(),
        overflowed=False,
    )


def test_save_brochure_persists_pdf_and_png_files_and_swaps_base64_for_urls(tmp_path, sample_topic):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    file_store = BrochureFileStore(str(tmp_path / "brochures"), public_url_base="http://127.0.0.1:8123")
    agent = ContentLibraryAgent(store, file_store)

    creative_id = agent.save(
        topic_id="comm-impact",
        campaign_id="camp-001",
        channel=Channel.BROCHURE,
        variant_label="primary",
        content=_brochure_draft(sample_topic),
        asset_ids=[],
    )

    saved = store.get(creative_id)
    assert saved.template_id.startswith("BR")
    assert "pdf_base64" not in saved.content_json
    assert "png_base64" not in saved.content_json
    assert saved.content_json["pdf_url"] == f"http://127.0.0.1:8123/brochure-files/comm-impact/{creative_id}.pdf"
    assert saved.content_json["png_url"] == f"http://127.0.0.1:8123/brochure-files/comm-impact/{creative_id}.png"

    pdf_path = tmp_path / "brochures" / "comm-impact" / f"{creative_id}.pdf"
    png_path = tmp_path / "brochures" / "comm-impact" / f"{creative_id}.png"
    assert pdf_path.read_bytes() == b"pdf-bytes"
    assert png_path.read_bytes() == b"png-bytes"


def test_save_without_request_json_round_trips_as_none(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)

    creative_id = agent.save(
        topic_id="comm-impact", campaign_id="camp-001", channel=Channel.EMAIL,
        variant_label="primary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[],
    )

    assert store.get(creative_id).request_json is None


def test_save_persists_request_json_for_later_editing(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)
    brief = {"topic_id": "comm-impact", "campaign_brief": {"purpose": "promo_sale", "key_message": "Hi"}}

    creative_id = agent.save(
        topic_id="comm-impact", campaign_id="camp-001", channel=Channel.EMAIL,
        variant_label="primary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[],
        request_json=brief,
    )

    assert store.get(creative_id).request_json == brief


def test_update_overwrites_content_but_preserves_identity_and_created_at(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)

    creative_id = agent.save(
        topic_id="comm-impact", campaign_id="camp-001", channel=Channel.EMAIL,
        variant_label="primary", content=EmailDraft(subject_lines=["Old"], html_body="<p>old</p>"), asset_ids=[],
        template_name="Original Name", status=ContentStatus.DRAFT,
    )
    original = store.get(creative_id)

    updated = agent.update(
        creative_id,
        content=EmailDraft(subject_lines=["New"], html_body="<p>new</p>"), asset_ids=["asset-9"],
        status=ContentStatus.APPROVED, request_json={"topic_id": "comm-impact"},
    )

    assert updated.creative_id == creative_id
    assert updated.template_id == original.template_id
    assert updated.created_at == original.created_at
    assert updated.template_name == "Original Name"  # unchanged when not passed
    assert updated.content_json["subject_lines"] == ["New"]
    assert updated.asset_ids == ["asset-9"]
    assert updated.status == ContentStatus.APPROVED
    assert updated.request_json == {"topic_id": "comm-impact"}
    assert store.get(creative_id).content_json["subject_lines"] == ["New"]


def test_update_missing_creative_id_returns_none(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)

    result = agent.update(
        "does-not-exist",
        content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[], status=ContentStatus.DRAFT,
    )
    assert result is None


def test_duplicate_creates_a_new_draft_entry_with_copied_content(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)

    original_id = agent.save(
        topic_id="comm-impact", campaign_id="camp-001", channel=Channel.EMAIL,
        variant_label="primary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=["a-1"],
        template_name="Launch Email", status=ContentStatus.APPROVED, request_json={"topic_id": "comm-impact"},
    )

    copy = agent.duplicate(original_id)

    assert copy.creative_id != original_id
    assert copy.template_id != store.get(original_id).template_id
    assert copy.template_name == "Launch Email (Copy)"
    assert copy.status == ContentStatus.DRAFT
    assert copy.content_json["subject_lines"] == ["Hi"]
    assert copy.asset_ids == ["a-1"]
    assert copy.request_json == {"topic_id": "comm-impact"}
    # The original is untouched.
    assert store.get(original_id).status == ContentStatus.APPROVED


def test_duplicate_missing_creative_id_returns_none(tmp_path):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    agent = ContentLibraryAgent(store)

    assert agent.duplicate("does-not-exist") is None


def test_update_brochure_reuses_same_creative_id_for_file_urls(tmp_path, sample_topic):
    db_path = tmp_path / "content_library.db"
    store = ContentLibraryStore(str(db_path))
    file_store = BrochureFileStore(str(tmp_path / "brochures"), public_url_base="http://127.0.0.1:8123")
    agent = ContentLibraryAgent(store, file_store)

    creative_id = agent.save(
        topic_id="comm-impact", campaign_id="camp-001", channel=Channel.BROCHURE,
        variant_label="primary", content=_brochure_draft(sample_topic), asset_ids=[], status=ContentStatus.DRAFT,
    )

    updated_draft = _brochure_draft(sample_topic)
    updated_draft.content.hero_title = "Updated Title"
    updated = agent.update(creative_id, content=updated_draft, asset_ids=[], status=ContentStatus.DRAFT)

    assert updated.content_json["pdf_url"] == f"http://127.0.0.1:8123/brochure-files/comm-impact/{creative_id}.pdf"
    assert updated.content_json["content"]["hero_title"] == "Updated Title"
