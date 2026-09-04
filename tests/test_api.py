import pytest
from fastapi.testclient import TestClient

import base64

from app.agents.email_sender import SenderIdentity
from app.agents.insights_agent import InsightsAgent
from app.agents.library_agent import ContentLibraryAgent
from app.api.main import (
    app,
    get_asset_store,
    get_brochure_file_store,
    get_email_send_store,
    get_email_sender_registry,
    get_image_text_agent,
    get_insights_agent,
    get_lead_import_store,
    get_lead_store,
    get_library_agent,
    get_library_store,
    get_orchestrator,
    get_topic_store,
    get_usage_store,
)
from app.config import get_settings
from app.models import Asset, BrochureContent, BrochureDraft, CampaignRequest, Channel, EmailDraft, TopicSummary, WhatsAppDraft
from app.storage.brochure_file_store import BrochureFileStore
from app.storage.content_library_store import ContentLibraryStore
from app.storage.email_send_store import EmailSendStore
from app.storage.lead_import_store import LeadImportStore
from app.storage.lead_store import LeadStore
from app.storage.usage_store import UsageStore


class FakeOrchestrator:
    def __init__(self):
        self.last_request = None
        self.last_revise_call = None

    def run(self, request: CampaignRequest):
        self.last_request = request
        if request.topic_id == "topic-boom":
            raise RuntimeError("503 UNAVAILABLE: upstream model overloaded")
        return {"creative_ids": {"email": "comm-impact-email-camp-x-abc123"}, "status_notes": ["email: approved"]}

    def generate_drafts(self, request: CampaignRequest):
        self.last_request = request
        result = {}
        if request.email_brief is not None:
            result["email"] = {
                "draft": EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>", referenced_asset_ids=[]),
                "approved": True,
                "issues": [],
            }
        if request.whatsapp_brief is not None:
            result["whatsapp"] = {
                "draft": WhatsAppDraft(message_variants=["Hi there"], cta_variants=["Reserve now"], image_asset_id=None),
                "approved": True,
                "issues": [],
            }
        if request.brochure_brief is not None:
            result["brochure"] = {
                "draft": _fake_brochure_draft(),
                "approved": True,
                "issues": [],
            }
        return result

    def revise_email(self, **kwargs):
        self.last_revise_call = kwargs
        return {
            "draft": EmailDraft(subject_lines=["Shorter"], html_body="<p>shorter</p>", referenced_asset_ids=[]),
            "approved": True,
            "issues": [],
        }

    def revise_whatsapp(self, **kwargs):
        self.last_revise_call = kwargs
        return {
            "draft": WhatsAppDraft(message_variants=["Shorter message"], cta_variants=["Reserve now"], image_asset_id=None),
            "approved": True,
            "issues": [],
        }

    def revise_brochure(self, **kwargs):
        self.last_revise_call = kwargs
        return {"draft": _fake_brochure_draft(hero_title="Shorter Hero"), "approved": True, "issues": []}

    def generate_more_subject_lines(self, **kwargs):
        self.last_revise_call = kwargs
        return ["A fresh angle 🎯", "Another new hook ✨"]


def _fake_brochure_draft(hero_title: str = "Communicate with Impact") -> BrochureDraft:
    content = BrochureContent(
        hero_title=hero_title,
        hero_tagline="Say less, land more.",
        hero_description="A hands-on workshop.",
        hook_lines=["Teams lose deals from how ideas get said."],
        modules=[],
        methodology=["Role Plays"],
        outcomes=["Structure any message in under 60 seconds"],
        closing_line="Closing line.",
        positioning_tags=["Customised"],
    )
    return BrochureDraft(
        content=content,
        html="<html>brochure</html>",
        pdf_base64=base64.b64encode(b"pdf-bytes").decode(),
        png_base64=base64.b64encode(b"png-bytes").decode(),
        overflowed=False,
    )


class FakeAssetStore:
    def __init__(self):
        self.last_save_call = None
        self.last_upload_call = None

    def list_for_topic(self, topic_id: str) -> list:
        return [Asset(asset_id="a1", topic_id=topic_id, url="https://cdn/a1.jpg", kind="image", tags=["roleplay"])]

    def save_generated_asset(self, topic_id: str, image_bytes: bytes, tags: list) -> Asset:
        self.last_save_call = {"topic_id": topic_id, "image_bytes": image_bytes, "tags": tags}
        return Asset(
            asset_id="topic-x-img-template-abc123",
            topic_id=topic_id,
            url="http://127.0.0.1:8123/asset-files/topic-x/generated/topic-x-img-template-abc123.png",
            kind="image",
            tags=tags,
            width=64,
            height=32,
        )

    def save_uploaded_asset(self, topic_id: str, image_bytes: bytes, tags: list) -> Asset:
        if b"not-a-real-image" in image_bytes:
            raise ValueError("File is not a readable image")
        self.last_upload_call = {"topic_id": topic_id, "image_bytes": image_bytes, "tags": tags}
        return Asset(
            asset_id="topic-x-upload-def456",
            topic_id=topic_id,
            url="http://127.0.0.1:8123/asset-files/topic-x/generated/topic-x-upload-def456.jpg",
            kind="image",
            tags=tags,
            width=300,
            height=200,
        )


class FakeImageTextAgent:
    def __init__(self):
        self.last_campaign_brief = None

    def suggest(self, campaign_brief) -> list:
        self.last_campaign_brief = campaign_brief
        return ["Reserve Your Seat Today", "Limited Seats Left"]


class FakeEmailSender:
    def __init__(self, error: Exception = None, failing_recipients: dict[str, str] = None):
        self.last_call = None
        self._error = error
        self._failing_recipients = failing_recipients or {}

    def send(self, *, to: list[str], subject: str, html_body: str) -> dict[str, str]:
        if self._error:
            raise self._error
        self.last_call = {"to": to, "subject": subject, "html_body": html_body}
        return {addr: msg for addr, msg in self._failing_recipients.items() if addr in to}


class FakeEmailSenderRegistry:
    """None `sender` mirrors "nothing configured" (matches a real deployment
    with no EMAIL_SENDERS set); a given `sender` is exposed under `sender_id`
    (default "default"), same convention as the real registry's single-entry
    fallback path.
    """

    def __init__(self, sender=None, sender_id: str = "default", display_name: str = "Test Sender", email: str = "test@example.com"):
        self._sender = sender
        self._identity = SenderIdentity(id=sender_id, display_name=display_name, email=email, app_password="x")

    def is_configured(self) -> bool:
        return self._sender is not None

    def list_identities(self):
        return [] if self._sender is None else [self._identity]

    def get(self, sender_id):
        if self._sender is None:
            return None
        if sender_id is not None and sender_id != self._identity.id:
            return None
        return self._sender


class FakeTopicStore:
    def list_topics(self) -> list:
        return [
            TopicSummary(topic_id="comm-impact", topic_name="Communicate with Impact"),
            TopicSummary(topic_id="negotiation-101", topic_name="Negotiation 101"),
        ]


@pytest.fixture
def client(tmp_path):
    store = ContentLibraryStore(str(tmp_path / "content_library.db"))
    usage_store = UsageStore(str(tmp_path / "usage.db"))
    # Shares the content_library.db file/path, matching how EmailSendStore
    # is wired in production (get_email_send_store reuses content_library_db_path).
    email_send_store = EmailSendStore(str(tmp_path / "content_library.db"))
    brochure_file_store = BrochureFileStore(str(tmp_path / "brochures"), public_url_base="http://127.0.0.1:8123")
    fake_orchestrator = FakeOrchestrator()
    fake_asset_store = FakeAssetStore()
    fake_image_text_agent = FakeImageTextAgent()

    app.dependency_overrides[get_library_store] = lambda: store
    app.dependency_overrides[get_library_agent] = lambda: ContentLibraryAgent(store, brochure_file_store)
    app.dependency_overrides[get_orchestrator] = lambda: fake_orchestrator
    app.dependency_overrides[get_asset_store] = lambda: fake_asset_store
    app.dependency_overrides[get_topic_store] = lambda: FakeTopicStore()
    app.dependency_overrides[get_image_text_agent] = lambda: fake_image_text_agent
    app.dependency_overrides[get_insights_agent] = lambda: InsightsAgent(store, fake_asset_store)
    app.dependency_overrides[get_usage_store] = lambda: usage_store
    app.dependency_overrides[get_brochure_file_store] = lambda: brochure_file_store
    # Defaults to "not configured", matching a real deployment with no
    # EMAIL_SENDERS/GMAIL_ADDRESS set -- individual tests override this with
    # a FakeEmailSenderRegistry(FakeEmailSender(...)) when they need a
    # "configured" sender.
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry()
    app.dependency_overrides[get_email_send_store] = lambda: email_send_store
    app.dependency_overrides[get_lead_store] = lambda: LeadStore(str(tmp_path / "leads.db"))
    app.dependency_overrides[get_lead_import_store] = lambda: LeadImportStore(str(tmp_path / "leads.db"))
    test_client = TestClient(app)
    # Attached rather than added to the yielded tuple so every existing
    # `test_client, _, _ = client` call site keeps working unchanged.
    test_client.fake_asset_store = fake_asset_store
    test_client.fake_image_text_agent = fake_image_text_agent
    yield test_client, store, fake_orchestrator
    app.dependency_overrides.clear()


def test_health(client):
    test_client, _, _ = client
    resp = test_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def _campaign_brief_payload():
    return {
        "purpose": "promo_sale",
        "key_message": "drive signups",
        "cta_text": "Reserve a seat",
        "audience_tone": "consumers_premium",
    }


def test_run_campaign_returns_creative_ids(client):
    test_client, _, fake_orchestrator = client
    payload = {
        "campaign_id": "camp-x",
        "topic_id": "topic-x",
        "campaign_brief": _campaign_brief_payload(),
        "email_brief": {},
    }
    resp = test_client.post("/campaigns/run", json=payload)
    assert resp.status_code == 200
    assert resp.json()["creative_ids"] == {"email": "comm-impact-email-camp-x-abc123"}
    assert fake_orchestrator.last_request.topic_id == "topic-x"


def test_run_campaign_missing_channel_briefs_returns_422(client):
    test_client, _, _ = client
    payload = {"campaign_id": "camp-x", "topic_id": "topic-x", "campaign_brief": _campaign_brief_payload()}
    resp = test_client.post("/campaigns/run", json=payload)
    assert resp.status_code == 422


def test_run_campaign_upstream_failure_returns_502_with_cors_headers(client):
    test_client, _, _ = client
    payload = {
        "campaign_id": "camp-x",
        "topic_id": "topic-boom",
        "campaign_brief": _campaign_brief_payload(),
        "email_brief": {},
    }
    resp = test_client.post(
        "/campaigns/run", json=payload, headers={"Origin": "http://localhost:5174"}
    )
    assert resp.status_code == 502
    assert "upstream model overloaded" in resp.json()["detail"]
    # This is what a raw unhandled exception would fail to include, which is
    # what makes the browser report it as an opaque "CORS error" instead.
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5174"


def test_get_content_by_creative_id(client):
    test_client, store, _ = client
    creative_id = ContentLibraryAgent(store).save(
        topic_id="topic-x",
        campaign_id="camp-x",
        channel=Channel.EMAIL,
        variant_label="primary",
        content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"),
        asset_ids=[],
    )

    resp = test_client.get(f"/content-library/{creative_id}")
    assert resp.status_code == 200
    assert resp.json()["creative_id"] == creative_id


def test_get_content_missing_creative_id_returns_404(client):
    test_client, _, _ = client
    resp = test_client.get("/content-library/does-not-exist")
    assert resp.status_code == 404


def test_delete_content_removes_entry(client):
    test_client, store, _ = client
    creative_id = ContentLibraryAgent(store).save(
        topic_id="topic-x",
        campaign_id="camp-x",
        channel=Channel.EMAIL,
        variant_label="primary",
        content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"),
        asset_ids=[],
    )

    resp = test_client.delete(f"/content-library/{creative_id}")
    assert resp.status_code == 204
    assert store.get(creative_id) is None


def test_delete_content_missing_creative_id_returns_404(client):
    test_client, _, _ = client
    resp = test_client.delete("/content-library/does-not-exist")
    assert resp.status_code == 404


def test_rename_content_updates_template_name(client):
    test_client, store, _ = client
    creative_id = ContentLibraryAgent(store).save(
        topic_id="topic-x",
        campaign_id="camp-x",
        channel=Channel.EMAIL,
        variant_label="primary",
        content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"),
        asset_ids=[],
        template_name="Original Name",
    )

    resp = test_client.patch(f"/content-library/{creative_id}", json={"template_name": "New Name"})
    assert resp.status_code == 200
    assert resp.json()["template_name"] == "New Name"
    assert store.get(creative_id).template_name == "New Name"


def test_rename_content_missing_creative_id_returns_404(client):
    test_client, _, _ = client
    resp = test_client.patch("/content-library/does-not-exist", json={"template_name": "New Name"})
    assert resp.status_code == 404


def test_list_content_by_topic(client):
    test_client, store, _ = client
    agent = ContentLibraryAgent(store)
    agent.save(
        topic_id="topic-x", campaign_id="camp-x", channel=Channel.EMAIL,
        variant_label="primary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[],
    )

    resp = test_client.get("/content-library", params={"topic_id": "topic-x"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_content_includes_sent_count_per_entry(client):
    test_client, store, _ = client
    agent = ContentLibraryAgent(store)
    sent_id = agent.save(
        topic_id="topic-x", campaign_id="camp-x", channel=Channel.EMAIL,
        variant_label="primary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[],
    )
    unsent_id = agent.save(
        topic_id="topic-x", campaign_id="camp-x", channel=Channel.EMAIL,
        variant_label="secondary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[],
    )
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(FakeEmailSender())
    test_client.post(
        "/send-email",
        json={"to": ["a@example.com"], "subject": "Hi", "html_body": "<p>hi</p>", "creative_id": sent_id},
    )
    test_client.post(
        "/send-email",
        json={"to": ["b@example.com"], "subject": "Hi", "html_body": "<p>hi</p>", "creative_id": sent_id},
    )

    resp = test_client.get("/content-library", params={"topic_id": "topic-x"})
    assert resp.status_code == 200
    counts = {e["creative_id"]: e["sent_count"] for e in resp.json()}
    assert counts[sent_id] == 2
    assert counts[unsent_id] == 0


def test_list_content_with_no_topic_filter_returns_every_topic(client):
    test_client, store, _ = client
    agent = ContentLibraryAgent(store)
    agent.save(
        topic_id="topic-x", campaign_id="camp-x", channel=Channel.EMAIL,
        variant_label="primary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[],
    )
    agent.save(
        topic_id="topic-y", campaign_id="camp-y", channel=Channel.EMAIL,
        variant_label="primary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[],
    )

    resp = test_client.get("/content-library")
    assert resp.status_code == 200
    assert {e["topic_id"] for e in resp.json()} == {"topic-x", "topic-y"}


def test_list_content_with_multiple_topic_ids_filters_to_those_topics(client):
    test_client, store, _ = client
    agent = ContentLibraryAgent(store)
    agent.save(
        topic_id="topic-x", campaign_id="camp-x", channel=Channel.EMAIL,
        variant_label="primary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[],
    )
    agent.save(
        topic_id="topic-y", campaign_id="camp-y", channel=Channel.EMAIL,
        variant_label="primary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[],
    )
    agent.save(
        topic_id="topic-z", campaign_id="camp-z", channel=Channel.EMAIL,
        variant_label="primary", content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>"), asset_ids=[],
    )

    resp = test_client.get("/content-library", params=[("topic_id", "topic-x"), ("topic_id", "topic-y")])
    assert resp.status_code == 200
    assert {e["topic_id"] for e in resp.json()} == {"topic-x", "topic-y"}


def test_generate_campaign_returns_drafts_without_saving(client):
    test_client, store, _ = client
    payload = {
        "campaign_id": "camp-x",
        "topic_id": "topic-x",
        "campaign_brief": _campaign_brief_payload(),
        "email_brief": {},
        "whatsapp_brief": {},
        "brochure_brief": {},
    }
    resp = test_client.post("/campaigns/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"]["draft"]["subject_lines"] == ["Hi"]
    assert body["whatsapp"]["draft"]["message_variants"][0] == "Hi there"
    assert body["brochure"]["draft"]["content"]["hero_title"] == "Communicate with Impact"
    assert body["brochure"]["draft"]["pdf_base64"]
    # generation must not have touched the library
    assert store.list_by_topic("topic-x") == []


def test_revise_email_returns_updated_draft(client):
    test_client, _, fake_orchestrator = client
    payload = {
        "topic_id": "topic-x",
        "campaign_brief": _campaign_brief_payload(),
        "email_brief": {},
        "current_draft": {"subject_lines": ["Original"], "html_body": "<p>original</p>", "referenced_asset_ids": []},
        "instruction": "make it shorter",
    }
    resp = test_client.post("/campaigns/revise/email", json=payload)
    assert resp.status_code == 200
    assert resp.json()["draft"]["subject_lines"] == ["Shorter"]
    assert fake_orchestrator.last_revise_call["instruction"] == "make it shorter"


def test_revise_whatsapp_returns_updated_draft(client):
    test_client, _, _ = client
    payload = {
        "topic_id": "topic-x",
        "campaign_brief": _campaign_brief_payload(),
        "whatsapp_brief": {},
        "current_draft": {"message_variants": ["Original message"], "cta_variants": ["Reserve now"], "image_asset_id": None},
        "instruction": "make it shorter",
    }
    resp = test_client.post("/campaigns/revise/whatsapp", json=payload)
    assert resp.status_code == 200
    assert resp.json()["draft"]["message_variants"][0] == "Shorter message"


def test_revise_brochure_returns_updated_draft(client):
    test_client, _, fake_orchestrator = client
    payload = {
        "topic_id": "topic-x",
        "campaign_brief": _campaign_brief_payload(),
        "brochure_brief": {},
        "current_draft": _fake_brochure_draft().model_dump(mode="json"),
        "instruction": "punch up the hero",
    }
    resp = test_client.post("/campaigns/revise/brochure", json=payload)
    assert resp.status_code == 200
    assert resp.json()["draft"]["content"]["hero_title"] == "Shorter Hero"
    assert fake_orchestrator.last_revise_call["instruction"] == "punch up the hero"


def test_generate_more_subject_lines_returns_new_lines(client):
    test_client, _, fake_orchestrator = client
    payload = {
        "topic_id": "topic-x",
        "campaign_brief": _campaign_brief_payload(),
        "existing_subject_lines": ["Original subject"],
    }
    resp = test_client.post("/campaigns/generate-more-subject-lines", json=payload)
    assert resp.status_code == 200
    assert resp.json()["subject_lines"] == ["A fresh angle 🎯", "Another new hook ✨"]
    assert fake_orchestrator.last_revise_call["existing_subject_lines"] == ["Original subject"]


def test_save_email_persists_to_library(client):
    test_client, store, _ = client
    payload = {
        "topic_id": "topic-x",
        "campaign_id": "camp-x",
        "draft": {"subject_lines": ["Hi"], "html_body": "<p>hi</p>", "referenced_asset_ids": ["a1"]},
        "template_name": "Launch Announcement",
        "content_tag": "promotional_communication",
    }
    resp = test_client.post("/content-library/email", json=payload)
    assert resp.status_code == 200
    creative_id = resp.json()["creative_id"]
    assert creative_id.startswith("topic-x-email-camp-x-")

    saved = store.get(creative_id)
    assert saved is not None
    assert saved.content_json["subject_lines"] == ["Hi"]
    assert saved.asset_ids == ["a1"]
    assert saved.status.value == "approved"
    assert saved.template_name == "Launch Announcement"
    assert saved.content_tag == "promotional_communication"


def test_save_email_as_draft_persists_with_draft_status(client):
    test_client, store, _ = client
    payload = {
        "topic_id": "topic-x",
        "campaign_id": "camp-x",
        "draft": {"subject_lines": ["Hi"], "html_body": "<p>hi</p>", "referenced_asset_ids": []},
        "template_name": "Launch Announcement",
        "content_tag": "service",
        "as_draft": True,
    }
    resp = test_client.post("/content-library/email", json=payload)
    assert resp.status_code == 200
    saved = store.get(resp.json()["creative_id"])
    assert saved.status.value == "draft"


def test_save_email_persists_request_json_for_later_editing(client):
    test_client, store, _ = client
    payload = {
        "topic_id": "topic-x",
        "campaign_id": "camp-x",
        "draft": {"subject_lines": ["Hi"], "html_body": "<p>hi</p>", "referenced_asset_ids": []},
        "template_name": "Launch Announcement",
        "content_tag": "promotional_communication",
        "request_json": {"topic_id": "topic-x", "campaign_brief": {"purpose": "promo_sale"}},
    }
    resp = test_client.post("/content-library/email", json=payload)
    assert resp.status_code == 200
    saved = store.get(resp.json()["creative_id"])
    assert saved.request_json == {"topic_id": "topic-x", "campaign_brief": {"purpose": "promo_sale"}}


def test_update_email_overwrites_content_and_keeps_creative_id(client):
    test_client, store, _ = client
    create_payload = {
        "topic_id": "topic-x",
        "campaign_id": "camp-x",
        "draft": {"subject_lines": ["Old"], "html_body": "<p>old</p>", "referenced_asset_ids": []},
        "template_name": "Original",
        "content_tag": "service",
        "as_draft": True,
    }
    creative_id = test_client.post("/content-library/email", json=create_payload).json()["creative_id"]

    update_payload = {
        "topic_id": "topic-x",
        "campaign_id": "camp-x",
        "draft": {"subject_lines": ["New"], "html_body": "<p>new</p>", "referenced_asset_ids": ["a1"]},
        "template_name": "Renamed",
        "content_tag": "promotional_communication",
        "as_draft": False,
    }
    resp = test_client.put(f"/content-library/email/{creative_id}", json=update_payload)
    assert resp.status_code == 200
    assert resp.json()["creative_id"] == creative_id

    saved = store.get(creative_id)
    assert saved.content_json["subject_lines"] == ["New"]
    assert saved.asset_ids == ["a1"]
    assert saved.template_name == "Renamed"
    assert saved.status.value == "approved"


def test_update_email_missing_creative_id_returns_404(client):
    test_client, _, _ = client
    payload = {
        "topic_id": "topic-x",
        "campaign_id": "camp-x",
        "draft": {"subject_lines": ["Hi"], "html_body": "<p>hi</p>", "referenced_asset_ids": []},
        "template_name": "Whatever",
        "content_tag": "service",
    }
    resp = test_client.put("/content-library/email/does-not-exist", json=payload)
    assert resp.status_code == 404


def test_duplicate_content_creates_a_new_draft_entry(client):
    test_client, store, _ = client
    create_payload = {
        "topic_id": "topic-x",
        "campaign_id": "camp-x",
        "draft": {"subject_lines": ["Hi"], "html_body": "<p>hi</p>", "referenced_asset_ids": ["a1"]},
        "template_name": "Launch Announcement",
        "content_tag": "promotional_communication",
    }
    creative_id = test_client.post("/content-library/email", json=create_payload).json()["creative_id"]

    resp = test_client.post(f"/content-library/{creative_id}/duplicate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["creative_id"] != creative_id
    assert body["template_name"] == "Launch Announcement (Copy)"
    assert body["status"] == "draft"
    assert body["content_json"]["subject_lines"] == ["Hi"]

    assert store.get(creative_id).status.value == "approved"  # original untouched


def test_duplicate_content_missing_creative_id_returns_404(client):
    test_client, _, _ = client
    resp = test_client.post("/content-library/does-not-exist/duplicate")
    assert resp.status_code == 404


def test_save_whatsapp_persists_to_library(client):
    test_client, store, _ = client
    payload = {
        "topic_id": "topic-x",
        "campaign_id": "camp-x",
        "draft": {"message_variants": ["Hi there"], "cta_variants": ["Reserve now"], "image_asset_id": "a1"},
        "template_name": "Reminder Nudge",
        "content_tag": "service",
    }
    resp = test_client.post("/content-library/whatsapp", json=payload)
    assert resp.status_code == 200
    creative_id = resp.json()["creative_id"]

    saved = store.get(creative_id)
    assert saved is not None
    assert saved.content_json["message_variants"][0] == "Hi there"
    assert saved.asset_ids == ["a1"]
    assert saved.status.value == "approved"
    assert saved.template_name == "Reminder Nudge"
    assert saved.content_tag == "service"


def test_save_whatsapp_as_draft_persists_with_draft_status(client):
    test_client, store, _ = client
    payload = {
        "topic_id": "topic-x",
        "campaign_id": "camp-x",
        "draft": {"message_variants": ["Hi there"], "cta_variants": ["Reserve now"], "image_asset_id": None},
        "template_name": "Reminder Nudge",
        "content_tag": "promotional_communication",
        "as_draft": True,
    }
    resp = test_client.post("/content-library/whatsapp", json=payload)
    assert resp.status_code == 200
    saved = store.get(resp.json()["creative_id"])
    assert saved.status.value == "draft"


def test_save_brochure_persists_files_and_swaps_base64_for_urls(client):
    test_client, store, _ = client
    payload = {
        "topic_id": "topic-x",
        "campaign_id": "camp-x",
        "draft": _fake_brochure_draft().model_dump(mode="json"),
        "template_name": "Launch Brochure",
        "content_tag": "promotional_communication",
    }
    resp = test_client.post("/content-library/brochure", json=payload)
    assert resp.status_code == 200
    creative_id = resp.json()["creative_id"]
    assert creative_id.startswith("topic-x-brochure-camp-x-")

    saved = store.get(creative_id)
    assert saved is not None
    assert "pdf_base64" not in saved.content_json
    assert saved.content_json["pdf_url"].endswith(f"{creative_id}.pdf")
    assert saved.template_id.startswith("BR")


def test_list_assets(client):
    test_client, _, _ = client
    resp = test_client.get("/assets", params={"topic_id": "topic-x"})
    assert resp.status_code == 200
    assert resp.json()[0]["asset_id"] == "a1"
    assert resp.json()[0]["url"] == "https://cdn/a1.jpg"


def test_list_topics(client):
    test_client, _, _ = client
    resp = test_client.get("/topics")
    assert resp.status_code == 200
    assert resp.json() == [
        {"topic_id": "comm-impact", "topic_name": "Communicate with Impact"},
        {"topic_id": "negotiation-101", "topic_name": "Negotiation 101"},
    ]


def test_get_insights_returns_composition_analytics_for_saved_content(client):
    test_client, _, _ = client
    test_client.post(
        "/content-library/email",
        json={
            "topic_id": "topic-x",
            "campaign_id": "camp-1",
            "draft": {"subject_lines": ["Reserve your seat today ✨"], "html_body": "<p>hi</p>", "referenced_asset_ids": []},
            "template_name": "Test Email",
            "content_tag": "promotional_communication",
        },
    )

    resp = test_client.get("/insights", params={"topic_id": "topic-x"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["topic_id"] == "topic-x"
    assert body["email"]["count"] == 1
    assert body["email"]["emoji_usage_rate"] == 1.0
    assert body["whatsapp"]["count"] == 0


def test_get_usage_on_empty_store_is_zero(client):
    test_client, _, _ = client
    resp = test_client.get("/usage")
    assert resp.status_code == 200
    body = resp.json()
    limit = get_settings().max_daily_ai_images
    assert body == {
        "requests_today": 0,
        "rate_limited_today": False,
        "daily_cap": None,
        "remaining_today": None,
        "requests_by_purpose": {},
        "last_request_at": None,
        "images_generated_today": 0,
        "image_generation_daily_limit": limit,
        "images_remaining_today": limit,
    }


def test_set_usage_cap_then_get_usage_reflects_it(client):
    test_client, _, _ = client
    resp = test_client.put("/usage/cap", json={"daily_cap": 100})
    assert resp.status_code == 200
    assert resp.json()["daily_cap"] == 100
    assert resp.json()["remaining_today"] == 100

    resp = test_client.get("/usage")
    assert resp.json()["daily_cap"] == 100


def test_set_usage_cap_to_null_clears_it(client):
    test_client, _, _ = client
    test_client.put("/usage/cap", json={"daily_cap": 50})
    resp = test_client.put("/usage/cap", json={"daily_cap": None})
    assert resp.json()["daily_cap"] is None
    assert resp.json()["remaining_today"] is None


def test_save_generated_asset_returns_new_asset(client):
    test_client, _, _ = client
    tiny_png_base64 = base64.b64encode(b"not-real-png-bytes-but-fine-for-a-fake-store").decode()
    resp = test_client.post(
        "/assets/generated",
        json={"topic_id": "topic-x", "image_base64": f"data:image/png;base64,{tiny_png_base64}", "tags": ["image-template"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["asset_id"] == "topic-x-img-template-abc123"
    assert body["tags"] == ["image-template"]
    assert test_client.fake_asset_store.last_save_call["topic_id"] == "topic-x"
    assert test_client.fake_asset_store.last_save_call["tags"] == ["image-template"]


def test_save_generated_asset_rejects_invalid_base64(client):
    test_client, _, _ = client
    resp = test_client.post("/assets/generated", json={"topic_id": "topic-x", "image_base64": "%%%not-base64%%%", "tags": []})
    assert resp.status_code == 400


def test_upload_asset_returns_new_asset(client):
    test_client, _, _ = client
    resp = test_client.post(
        "/assets/upload",
        data={"topic_id": "topic-x", "tags": "uploaded,team-photo"},
        files={"file": ("photo.jpg", b"fake-jpeg-bytes", "image/jpeg")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["asset_id"] == "topic-x-upload-def456"
    assert body["width"] == 300
    assert body["height"] == 200
    assert test_client.fake_asset_store.last_upload_call["topic_id"] == "topic-x"
    assert test_client.fake_asset_store.last_upload_call["tags"] == ["uploaded", "team-photo"]


def test_upload_asset_rejects_non_image_file(client):
    test_client, _, _ = client
    resp = test_client.post(
        "/assets/upload",
        data={"topic_id": "topic-x", "tags": ""},
        files={"file": ("notes.txt", b"this is not-a-real-image, just text", "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_asset_rejects_empty_file(client):
    test_client, _, _ = client
    resp = test_client.post(
        "/assets/upload",
        data={"topic_id": "topic-x", "tags": ""},
        files={"file": ("empty.jpg", b"", "image/jpeg")},
    )
    assert resp.status_code == 400


def test_upload_asset_rejects_oversized_file(client):
    test_client, _, _ = client
    too_big = b"x" * (10 * 1024 * 1024 + 1)
    resp = test_client.post(
        "/assets/upload",
        data={"topic_id": "topic-x", "tags": ""},
        files={"file": ("huge.jpg", too_big, "image/jpeg")},
    )
    assert resp.status_code == 400


def test_suggest_overlay_text_returns_suggestions(client):
    test_client, _, _ = client
    resp = test_client.post("/assets/suggest-overlay-text", json={"campaign_brief": _campaign_brief_payload()})
    assert resp.status_code == 200
    assert resp.json() == {"suggestions": ["Reserve Your Seat Today", "Limited Seats Left"]}
    assert test_client.fake_image_text_agent.last_campaign_brief.key_message == "drive signups"


def test_list_email_senders_returns_empty_when_not_configured(client):
    test_client, _, _ = client
    resp = test_client.get("/email-senders")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_email_senders_never_includes_app_password(client):
    test_client, _, _ = client
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(
        FakeEmailSender(), sender_id="sakshi", display_name="Sakshi Dua", email="sakshidua.imagecoach@gmail.com"
    )

    resp = test_client.get("/email-senders")

    assert resp.status_code == 200
    assert resp.json() == [{"id": "sakshi", "display_name": "Sakshi Dua", "email": "sakshidua.imagecoach@gmail.com"}]


def test_send_email_returns_503_when_not_configured(client):
    test_client, _, _ = client
    resp = test_client.post(
        "/send-email", json={"to": ["recipient@example.com"], "subject": "Hi", "html_body": "<p>hi</p>"}
    )
    assert resp.status_code == 503


def test_send_email_sends_from_the_requested_sender_id(client):
    test_client, _, _ = client
    fake_sender = FakeEmailSender()
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(
        fake_sender, sender_id="sakshi", display_name="Sakshi Dua", email="sakshidua.imagecoach@gmail.com"
    )

    resp = test_client.post(
        "/send-email",
        json={"to": ["recipient@example.com"], "subject": "Hi", "html_body": "<p>hi</p>", "sender_id": "sakshi"},
    )

    assert resp.status_code == 200
    assert fake_sender.last_call is not None


def test_send_email_rejects_an_unknown_sender_id(client):
    test_client, _, _ = client
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(
        FakeEmailSender(), sender_id="sakshi"
    )

    resp = test_client.post(
        "/send-email",
        json={"to": ["recipient@example.com"], "subject": "Hi", "html_body": "<p>hi</p>", "sender_id": "does-not-exist"},
    )

    assert resp.status_code == 400


def test_send_email_succeeds_when_configured(client):
    test_client, _, _ = client
    fake_sender = FakeEmailSender()
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(fake_sender)

    resp = test_client.post(
        "/send-email",
        json={"to": ["recipient@example.com"], "subject": "Join us", "html_body": "<p>Hello</p>"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"results": [{"to": "recipient@example.com", "sent": True, "error": None}]}
    assert fake_sender.last_call == {
        "to": ["recipient@example.com"],
        "subject": "Join us",
        "html_body": "<p>Hello</p>",
    }


def test_send_email_sends_to_every_recipient_individually(client):
    test_client, _, _ = client
    fake_sender = FakeEmailSender()
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(fake_sender)

    resp = test_client.post(
        "/send-email",
        json={"to": ["a@example.com", "b@example.com", "c@example.com"], "subject": "Hi", "html_body": "<p>hi</p>"},
    )

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert {r["to"]: r["sent"] for r in results} == {"a@example.com": True, "b@example.com": True, "c@example.com": True}
    assert fake_sender.last_call["to"] == ["a@example.com", "b@example.com", "c@example.com"]


def test_send_email_dedupes_case_insensitively_and_trims_whitespace(client):
    test_client, _, _ = client
    fake_sender = FakeEmailSender()
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(fake_sender)

    resp = test_client.post(
        "/send-email",
        json={"to": [" a@example.com ", "A@example.com", "b@example.com"], "subject": "Hi", "html_body": "<p>hi</p>"},
    )

    assert resp.status_code == 200
    assert fake_sender.last_call["to"] == ["a@example.com", "b@example.com"]


def test_send_email_partial_failure_reports_per_recipient_and_only_records_successes(client):
    test_client, store, _ = client
    fake_sender = FakeEmailSender(failing_recipients={"bad@example.com": "mailbox unavailable"})
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(fake_sender)

    resp = test_client.post(
        "/send-email",
        json={
            "to": ["good@example.com", "bad@example.com"],
            "subject": "Hi",
            "html_body": "<p>hi</p>",
            "creative_id": "creative-partial",
        },
    )

    assert resp.status_code == 200
    results = {r["to"]: r for r in resp.json()["results"]}
    assert results["good@example.com"]["sent"] is True
    assert results["bad@example.com"]["sent"] is False
    assert results["bad@example.com"]["error"] == "mailbox unavailable"

    sends_resp = test_client.get("/content-library/creative-partial/sends")
    records = sends_resp.json()
    assert len(records) == 1
    assert records[0]["to_email"] == "good@example.com"


def test_send_email_mixes_malformed_addresses_into_results_without_blocking_valid_ones(client):
    test_client, _, _ = client
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(FakeEmailSender())

    resp = test_client.post(
        "/send-email",
        json={"to": ["good@example.com", "not-an-email"], "subject": "Hi", "html_body": "<p>hi</p>"},
    )

    assert resp.status_code == 200
    results = {r["to"]: r for r in resp.json()["results"]}
    assert results["good@example.com"]["sent"] is True
    assert results["not-an-email"]["sent"] is False
    assert "valid email" in results["not-an-email"]["error"]


def test_send_email_rejects_when_every_address_is_malformed(client):
    test_client, _, _ = client
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(FakeEmailSender())

    resp = test_client.post("/send-email", json={"to": ["not-an-email"], "subject": "Hi", "html_body": "<p>hi</p>"})

    assert resp.status_code == 400


def test_send_email_rejects_more_than_fifty_recipients(client):
    test_client, _, _ = client
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(FakeEmailSender())

    resp = test_client.post(
        "/send-email",
        json={"to": [f"user{i}@example.com" for i in range(51)], "subject": "Hi", "html_body": "<p>hi</p>"},
    )

    assert resp.status_code == 422


def test_send_email_returns_502_when_sender_raises(client):
    test_client, _, _ = client
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(FakeEmailSender(error=RuntimeError("SMTP AUTH failed")))

    resp = test_client.post(
        "/send-email", json={"to": ["recipient@example.com"], "subject": "Hi", "html_body": "<p>hi</p>"}
    )

    assert resp.status_code == 502


def test_send_email_with_creative_id_is_recorded_and_listable(client):
    test_client, _, _ = client
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(FakeEmailSender())

    resp = test_client.post(
        "/send-email",
        json={
            "to": ["attendee@example.com"],
            "subject": "Hi",
            "html_body": "<p>hi</p>",
            "creative_id": "comm-impact-email-camp-1-abc123",
        },
    )
    assert resp.status_code == 200

    sends_resp = test_client.get("/content-library/comm-impact-email-camp-1-abc123/sends")
    assert sends_resp.status_code == 200
    records = sends_resp.json()
    assert len(records) == 1
    assert records[0]["to_email"] == "attendee@example.com"
    assert records[0]["sent_at"] is not None


def test_send_email_without_creative_id_is_not_recorded_anywhere(client):
    test_client, _, _ = client
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(FakeEmailSender())

    resp = test_client.post(
        "/send-email", json={"to": ["attendee@example.com"], "subject": "Hi", "html_body": "<p>hi</p>"}
    )
    assert resp.status_code == 200

    # Nothing to look up by, but a send with no creative_id must not leak
    # into some other creative_id's history either.
    sends_resp = test_client.get("/content-library/some-other-creative-id/sends")
    assert sends_resp.json() == []


def test_send_email_failure_is_not_recorded(client):
    test_client, _, _ = client
    app.dependency_overrides[get_email_sender_registry] = lambda: FakeEmailSenderRegistry(FakeEmailSender(error=RuntimeError("SMTP AUTH failed")))

    test_client.post(
        "/send-email",
        json={"to": ["attendee@example.com"], "subject": "Hi", "html_body": "<p>hi</p>", "creative_id": "creative-x"},
    )

    sends_resp = test_client.get("/content-library/creative-x/sends")
    assert sends_resp.json() == []


def test_list_email_sends_for_unknown_creative_id_is_empty(client):
    test_client, _, _ = client
    resp = test_client.get("/content-library/never-sent/sends")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_lead_and_list_round_trip(client):
    test_client, _, _ = client
    resp = test_client.post(
        "/leads",
        json={"name": "Asha Rao", "phone": "9876543210", "email": "asha@example.com", "organization": "Acme Corp", "remarks": "Met at conference"},
    )
    assert resp.status_code == 200
    lead = resp.json()
    assert lead["name"] == "Asha Rao"
    assert lead["id"].startswith("lead-")

    list_resp = test_client.get("/leads")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_create_lead_requires_a_name(client):
    test_client, _, _ = client
    resp = test_client.post("/leads", json={"name": "", "phone": "123"})
    assert resp.status_code == 422


def test_list_leads_search_matches_name_or_organization(client):
    test_client, _, _ = client
    test_client.post("/leads", json={"name": "Asha Rao", "organization": "Acme Corp"})
    test_client.post("/leads", json={"name": "Vikram Singh", "organization": "Globex Inc"})

    resp = test_client.get("/leads", params={"search": "asha"})
    assert [l["name"] for l in resp.json()] == ["Asha Rao"]

    resp = test_client.get("/leads", params={"search": "globex"})
    assert [l["name"] for l in resp.json()] == ["Vikram Singh"]


def test_list_leads_search_matches_phone_or_remarks(client):
    test_client, _, _ = client
    test_client.post("/leads", json={"name": "Asha Rao", "phone": "9876543210", "remarks": "Met at conference"})
    test_client.post("/leads", json={"name": "Vikram Singh", "phone": "9900112233", "remarks": "Referred by a colleague"})

    resp = test_client.get("/leads", params={"search": "98765"})
    assert [l["name"] for l in resp.json()] == ["Asha Rao"]

    resp = test_client.get("/leads", params={"search": "referred"})
    assert [l["name"] for l in resp.json()] == ["Vikram Singh"]


def test_update_lead_overwrites_fields(client):
    test_client, _, _ = client
    lead = test_client.post("/leads", json={"name": "Asha Rao", "organization": "Acme Corp"}).json()

    resp = test_client.put(
        f"/leads/{lead['id']}",
        json={"name": "Asha Mehta", "organization": "Globex Inc", "remarks": "Changed org"},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["name"] == "Asha Mehta"
    assert updated["organization"] == "Globex Inc"
    assert updated["remarks"] == "Changed org"

    listed = test_client.get("/leads").json()
    assert listed[0]["name"] == "Asha Mehta"


def test_update_lead_missing_id_returns_404(client):
    test_client, _, _ = client
    resp = test_client.put("/leads/does-not-exist", json={"name": "Someone"})
    assert resp.status_code == 404


def test_delete_lead_removes_it(client):
    test_client, _, _ = client
    lead = test_client.post("/leads", json={"name": "Asha Rao"}).json()

    resp = test_client.delete(f"/leads/{lead['id']}")
    assert resp.status_code == 204
    assert test_client.get("/leads").json() == []


def test_delete_lead_missing_id_returns_404(client):
    test_client, _, _ = client
    resp = test_client.delete("/leads/does-not-exist")
    assert resp.status_code == 404


def test_import_leads_csv_creates_leads_and_reports_skipped(client):
    test_client, _, _ = client
    csv_content = "Name,Phone,Email,Organization,Remarks\nAsha Rao,9876543210,asha@example.com,Acme Corp,Met at conference\n,noname@example.com,,,\n"

    resp = test_client.post(
        "/leads/import",
        files={"file": ("leads.csv", csv_content, "text/csv")},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 1
    assert body["skipped"] == [{"row": 3, "reason": "Missing name"}]

    leads = test_client.get("/leads").json()
    assert len(leads) == 1
    assert leads[0]["name"] == "Asha Rao"


def test_import_leads_csv_without_name_column_returns_400(client):
    test_client, _, _ = client
    csv_content = "Phone,Email\n9876543210,asha@example.com\n"

    resp = test_client.post(
        "/leads/import",
        files={"file": ("leads.csv", csv_content, "text/csv")},
    )

    assert resp.status_code == 400


def test_import_leads_csv_rejects_empty_file(client):
    test_client, _, _ = client
    resp = test_client.post("/leads/import", files={"file": ("leads.csv", "", "text/csv")})
    assert resp.status_code == 400


def test_import_leads_csv_records_history_batch(client):
    test_client, _, _ = client
    csv_content = "Name,Email\nAsha Rao,asha@example.com\n,noname@example.com\n"

    test_client.post("/leads/import", files={"file": ("my-leads.csv", csv_content, "text/csv")})

    history = test_client.get("/leads/import-history").json()
    assert len(history) == 1
    batch = history[0]
    assert batch["filename"] == "my-leads.csv"
    assert batch["imported_count"] == 1
    assert batch["failed_count"] == 1
    assert batch["total_rows"] == 2
    assert batch["status"] == "error"


def test_import_history_lists_newest_batch_first(client):
    test_client, _, _ = client
    test_client.post("/leads/import", files={"file": ("first.csv", "Name\nA\n", "text/csv")})
    test_client.post("/leads/import", files={"file": ("second.csv", "Name\nB\n", "text/csv")})

    history = test_client.get("/leads/import-history").json()
    assert [b["filename"] for b in history] == ["second.csv", "first.csv"]


def test_download_lead_import_report_returns_csv(client):
    test_client, _, _ = client
    csv_content = "Name,Email\nAsha Rao,asha@example.com\n,noname@example.com\n"
    test_client.post("/leads/import", files={"file": ("leads.csv", csv_content, "text/csv")})
    batch_id = test_client.get("/leads/import-history").json()[0]["id"]

    resp = test_client.get(f"/leads/import-history/{batch_id}/report")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "Missing name" in resp.text


def test_download_lead_import_report_missing_batch_returns_404(client):
    test_client, _, _ = client
    resp = test_client.get("/leads/import-history/does-not-exist/report")
    assert resp.status_code == 404


def test_download_lead_import_template_returns_csv(client):
    test_client, _, _ = client
    resp = test_client.get("/leads/import-template")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "Name,Phone,Email,Organization,Remarks" in resp.text
