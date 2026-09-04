from app.agents.insights_agent import InsightsAgent
from app.agents.library_agent import ContentLibraryAgent
from app.models import Asset, Channel, EmailDraft, WhatsAppDraft
from app.storage.content_library_store import ContentLibraryStore


class FakeAssetStore:
    def __init__(self, assets: list[Asset]):
        self._assets = assets

    def list_for_topic(self, topic_id: str) -> list[Asset]:
        return [a for a in self._assets if a.topic_id == topic_id]


def _build_agent(tmp_path, assets: list[Asset] = ()):
    store = ContentLibraryStore(str(tmp_path / "content_library.db"))
    library_agent = ContentLibraryAgent(store)
    insights_agent = InsightsAgent(store, FakeAssetStore(list(assets)))
    return library_agent, insights_agent


def test_email_insights_on_empty_topic_are_all_zero(tmp_path):
    _, insights_agent = _build_agent(tmp_path)

    result = insights_agent.compute("comm-empty")

    assert result.email.count == 0
    assert result.email.avg_subject_words == 0.0
    assert result.email.emoji_usage_rate == 0.0
    assert result.email.top_words == []
    assert result.email.image_usage_rate == 0.0
    assert result.email.content_tag_distribution == {}


def test_email_insights_compute_length_emoji_and_words(tmp_path):
    library_agent, insights_agent = _build_agent(tmp_path)
    library_agent.save(
        topic_id="comm-impact",
        campaign_id="camp-1",
        channel=Channel.EMAIL,
        variant_label="primary",
        content=EmailDraft(
            subject_lines=["Reserve your seat today", "Limited seats ✨ closing soon"],
            html_body="<p>hi</p>",
            referenced_asset_ids=[],
        ),
        asset_ids=[],
        content_tag="promotional_communication",
    )
    library_agent.save(
        topic_id="comm-impact",
        campaign_id="camp-2",
        channel=Channel.EMAIL,
        variant_label="primary",
        content=EmailDraft(subject_lines=["Your workshop reminder update"], html_body="<p>hi</p>", referenced_asset_ids=[]),
        asset_ids=[],
        content_tag="service",
    )

    result = insights_agent.compute("comm-impact")

    assert result.email.count == 2
    # 3 subject lines total: "Reserve your seat today" (4 words), "Limited
    # seats ✨ closing soon" (5 words incl. the emoji token), "Your workshop
    # reminder update" (4 words) -> avg = 13/3
    assert result.email.avg_subject_words == round(13 / 3, 1)
    assert result.email.emoji_usage_rate == round(1 / 3, 2)
    assert result.email.content_tag_distribution == {"promotional_communication": 1, "service": 1}


def test_email_insights_image_usage_and_top_asset_tags(tmp_path):
    assets = [
        Asset(asset_id="a1", topic_id="comm-impact", url="https://cdn/a1.jpg", kind="image", tags=["roleplay", "group"]),
        Asset(asset_id="a2", topic_id="comm-impact", url="https://cdn/a2.jpg", kind="image", tags=["roleplay", "feedback"]),
    ]
    library_agent, insights_agent = _build_agent(tmp_path, assets)
    library_agent.save(
        topic_id="comm-impact",
        campaign_id="camp-1",
        channel=Channel.EMAIL,
        variant_label="primary",
        content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>", referenced_asset_ids=["a1", "a2"]),
        asset_ids=["a1", "a2"],
    )
    library_agent.save(
        topic_id="comm-impact",
        campaign_id="camp-2",
        channel=Channel.EMAIL,
        variant_label="primary",
        content=EmailDraft(subject_lines=["Hi"], html_body="<p>hi</p>", referenced_asset_ids=[]),
        asset_ids=[],
    )

    result = insights_agent.compute("comm-impact")

    assert result.email.image_usage_rate == 0.5
    tags = {t.tag: t.count for t in result.email.top_asset_tags}
    assert tags["roleplay"] == 2
    assert tags["group"] == 1
    assert tags["feedback"] == 1


def test_whatsapp_insights_compute_length_and_cta_frequency(tmp_path):
    library_agent, insights_agent = _build_agent(tmp_path)
    library_agent.save(
        topic_id="comm-impact",
        campaign_id="camp-1",
        channel=Channel.WHATSAPP,
        variant_label="primary",
        content=WhatsAppDraft(
            message_variants=["Reserve your seat this weekend", "Join us this weekend for the workshop"],
            cta_variants=["Reserve your seat", "Reserve your seat"],
            image_asset_id=None,
        ),
        asset_ids=[],
    )
    library_agent.save(
        topic_id="comm-impact",
        campaign_id="camp-2",
        channel=Channel.WHATSAPP,
        variant_label="primary",
        content=WhatsAppDraft(message_variants=["Call now for details"], cta_variants=["Call now"], image_asset_id="a1"),
        asset_ids=["a1"],
    )

    result = insights_agent.compute("comm-impact")

    assert result.whatsapp.count == 2
    assert result.whatsapp.image_usage_rate == 0.5
    ctas = {c.cta: c.count for c in result.whatsapp.top_cta_phrases}
    assert ctas["Reserve your seat"] == 2
    assert ctas["Call now"] == 1


def test_insights_only_considers_the_given_topic(tmp_path):
    library_agent, insights_agent = _build_agent(tmp_path)
    library_agent.save(
        topic_id="negotiation-101",
        campaign_id="camp-1",
        channel=Channel.EMAIL,
        variant_label="primary",
        content=EmailDraft(subject_lines=["Not this topic"], html_body="<p>hi</p>", referenced_asset_ids=[]),
        asset_ids=[],
    )

    result = insights_agent.compute("comm-impact")

    assert result.email.count == 0
    assert result.whatsapp.count == 0
