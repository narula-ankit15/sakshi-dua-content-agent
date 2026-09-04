import pytest

from app.agents.asset_agent import AssetAgent
from app.agents.brochure_agent import BrochureContentAgent
from app.agents.compliance_agent import ComplianceAgent
from app.agents.email_agent import EmailContentAgent
from app.agents.hero_image_agent import HeroImageAgent
from app.agents.library_agent import ContentLibraryAgent
from app.agents.orchestrator import Orchestrator
from app.agents.topic_context_agent import TopicContextAgent
from app.agents.usage_tracking_client import ImageGenerationLimitExceeded
from app.agents.whatsapp_agent import WhatsAppContentAgent
from app.models import (
    Asset,
    AudienceTone,
    BrochureBrief,
    CampaignBrief,
    CampaignRequest,
    EmailBrief,
    EmailImagery,
    HeroImageSource,
    Purpose,
    Topic,
    TopicModule,
    WhatsAppBrief,
)
from app.rendering.email_renderer import EmailRenderer
from app.storage.content_library_store import ContentLibraryStore


def _email_renderer() -> EmailRenderer:
    # Real (not faked) EmailRenderer -- unlike BrochureRenderer, it's pure
    # Jinja rendering with no external process, so there's no need to fake it.
    return EmailRenderer(trainer_name="Sakshi Dua", trainer_contact="sakshi@example.com")


class RoutingFakeLLMClient:
    """Returns a different canned response depending on which content
    agent is calling (email vs whatsapp vs brochure), matched by a keyword
    unique to each agent's system prompt -- lets one fake drive the whole
    orchestrator test without hitting Gemini.
    """

    def generate_json(self, *, system: str, prompt: str) -> dict:
        if "email" in system.lower():
            return {
                "subject_lines": ["Come join Communicate with Impact", "Reserve your seat"],
                "eyebrow": "Workshop",
                "headline": "Come join Communicate with Impact",
                "intro_text": "This weekend only.",
                "bullet_line": None,
                "items": [],
                "closing_text": "See you there.",
            }
        if "whatsapp" in system.lower():
            return {
                "message_variants": [
                    "Come join Communicate with Impact this weekend!",
                    "Communicate with Impact is waiting for you!",
                ],
                "cta_variants": ["Reserve now", "Reserve now"],
                "image_asset_id": None,
            }
        return {
            "hero_title": "Communicate with Impact",
            "hero_tagline": "Say less, land more.",
            "hero_description": "A hands-on workshop for teams whose ideas keep getting lost in the delivery.",
            "hook_lines": ["Teams lose deals from how ideas get said."],
            "closing_line": "Communication is the multiplier on everything else your team does well.",
        }


class FakeTopicStore:
    def get(self, topic_id: str) -> Topic:
        return Topic(
            topic_id=topic_id,
            topic_name="Communicate with Impact",
            tagline="Say less, land more.",
            hook_description="Hook",
            modules=[TopicModule(module_number=1, title="Structuring Your Message", bullets=["The framework"])],
            methodology=["Role Plays"],
            outcomes=["Structure any message in under 60 seconds"],
            closing_line="Closing",
            positioning_tags=["Customised"],
        )


class FakeAssetStore:
    def __init__(self):
        self.generated: list = []

    def list_for_topic(self, topic_id: str) -> list:
        return [
            Asset(asset_id="a1", topic_id=topic_id, url="https://cdn/a1.jpg", kind="image", tags=["roleplay"]),
            Asset(asset_id="a2", topic_id=topic_id, url="https://cdn/a2.jpg", kind="image", tags=["group"]),
            *self.generated,
        ]

    def save_generated_asset(self, topic_id: str, image_bytes: bytes, tags: list) -> Asset:
        asset = Asset(
            asset_id=f"ai-hero-{len(self.generated) + 1}",
            topic_id=topic_id,
            url=f"https://cdn/ai-hero-{len(self.generated) + 1}.png",
            kind="image",
            tags=tags,
        )
        self.generated.append(asset)
        return asset


class FakeBrochureRenderer:
    def render(self, content, layout=None, hero_photo_url=None, gallery_photo_urls=None):
        return {"html": "<html>brochure</html>", "pdf_bytes": b"pdf-bytes", "png_bytes": b"png-bytes", "overflowed": False}


class FakeImageGenClient:
    def generate_image(self, prompt: str) -> bytes:
        return b"fake-png-bytes"


def _build_orchestrator(tmp_path) -> Orchestrator:
    context_agent = TopicContextAgent(FakeTopicStore())
    asset_agent = AssetAgent(FakeAssetStore())
    llm = RoutingFakeLLMClient()
    email_agent = EmailContentAgent(llm, _email_renderer())
    whatsapp_agent = WhatsAppContentAgent(llm)
    brochure_agent = BrochureContentAgent(llm, FakeBrochureRenderer())
    compliance_agent = ComplianceAgent()
    library_agent = ContentLibraryAgent(ContentLibraryStore(str(tmp_path / "content_library.db")))
    hero_image_agent = HeroImageAgent(FakeImageGenClient())
    return Orchestrator(
        context_agent,
        asset_agent,
        email_agent,
        whatsapp_agent,
        brochure_agent,
        compliance_agent,
        library_agent,
        hero_image_agent,
        trainer_name="Sakshi Dua",
        trainer_contact="sakshi@example.com",
    )


def _campaign_brief() -> CampaignBrief:
    return CampaignBrief(
        purpose=Purpose.PROMO_SALE,
        key_message="drive signups",
        cta_text="Reserve a seat",
        audience_tone=AudienceTone.CONSUMERS_PREMIUM,
    )


def test_orchestrator_runs_all_three_channels_and_saves_approved_drafts(tmp_path):
    orchestrator = _build_orchestrator(tmp_path)
    request = CampaignRequest(
        campaign_id="camp-001",
        topic_id="comm-impact",
        campaign_brief=_campaign_brief(),
        email_brief=EmailBrief(),
        whatsapp_brief=WhatsAppBrief(),
        brochure_brief=BrochureBrief(),
    )

    result = orchestrator.run(request)

    assert set(result["creative_ids"].keys()) == {"email", "whatsapp", "brochure"}
    assert result["creative_ids"]["email"].startswith("comm-impact-email-camp-001-")
    assert result["creative_ids"]["whatsapp"].startswith("comm-impact-whatsapp-camp-001-")
    assert result["creative_ids"]["brochure"].startswith("comm-impact-brochure-camp-001-")
    assert any("email: approved" in note for note in result["status_notes"])
    assert any("brochure: approved" in note for note in result["status_notes"])


def test_orchestrator_only_runs_requested_channel(tmp_path):
    orchestrator = _build_orchestrator(tmp_path)
    request = CampaignRequest(
        campaign_id="camp-002",
        topic_id="comm-impact",
        campaign_brief=_campaign_brief(),
        email_brief=EmailBrief(),
    )

    result = orchestrator.run(request)

    assert list(result["creative_ids"].keys()) == ["email"]


def test_generate_drafts_does_not_save_to_library(tmp_path):
    store = ContentLibraryStore(str(tmp_path / "content_library.db"))
    context_agent = TopicContextAgent(FakeTopicStore())
    asset_agent = AssetAgent(FakeAssetStore())
    llm = RoutingFakeLLMClient()
    orchestrator = Orchestrator(
        context_agent,
        asset_agent,
        EmailContentAgent(llm, _email_renderer()),
        WhatsAppContentAgent(llm),
        BrochureContentAgent(llm, FakeBrochureRenderer()),
        ComplianceAgent(),
        ContentLibraryAgent(store),
        HeroImageAgent(FakeImageGenClient()),
        trainer_name="Sakshi Dua",
    )
    request = CampaignRequest(
        campaign_id="camp-003",
        topic_id="comm-impact",
        campaign_brief=_campaign_brief(),
        email_brief=EmailBrief(),
        whatsapp_brief=WhatsAppBrief(),
        brochure_brief=BrochureBrief(),
    )

    result = orchestrator.generate_drafts(request)

    assert set(result.keys()) == {"email", "whatsapp", "brochure"}
    assert result["email"]["approved"] is True
    assert result["brochure"]["approved"] is True
    assert result["brochure"]["draft"].content.modules[0].title == "Structuring Your Message"
    # the whole point: nothing gets persisted until an explicit save call
    assert store.list_by_topic("comm-impact") == []


class RevisingFakeLLMClient:
    """Returns the normal canned response for a first-pass generate, but a
    distinguishable response once the prompt shows this is a revise call
    (identified by the CURRENT DRAFT marker the agent's revise() adds).
    """

    def generate_json(self, *, system: str, prompt: str) -> dict:
        is_revise = "CURRENT DRAFT" in prompt
        if "email" in system.lower():
            if is_revise:
                return {
                    "subject_lines": ["Shorter subject"],
                    "eyebrow": None,
                    "headline": "Shorter headline",
                    "intro_text": "Shorter revised body.",
                    "bullet_line": None,
                    "items": [],
                    "closing_text": "Short closing.",
                }
            return {
                "subject_lines": ["Come join Communicate with Impact", "Reserve your seat"],
                "eyebrow": "Workshop",
                "headline": "Come join Communicate with Impact",
                "intro_text": "This weekend only.",
                "bullet_line": None,
                "items": [],
                "closing_text": "See you there.",
            }
        if "whatsapp" in system.lower():
            if is_revise:
                return {
                    "message_variants": ["Shorter revised message!"],
                    "cta_variants": ["Reserve now"],
                    "image_asset_id": None,
                }
            return {
                "message_variants": ["Come join this weekend!"],
                "cta_variants": ["Reserve now"],
                "image_asset_id": None,
            }
        if is_revise:
            return {
                "hero_title": "Shorter Hero Title",
                "hero_tagline": "Short.",
                "hero_description": "Short description.",
                "hook_lines": ["Short hook."],
                "closing_line": "Short closing.",
            }
        return {
            "hero_title": "Communicate with Impact",
            "hero_tagline": "Say less, land more.",
            "hero_description": "A hands-on workshop.",
            "hook_lines": ["Teams lose deals from how ideas get said."],
            "closing_line": "Closing line.",
        }


def _build_revising_orchestrator(tmp_path):
    store = ContentLibraryStore(str(tmp_path / "content_library.db"))
    context_agent = TopicContextAgent(FakeTopicStore())
    asset_agent = AssetAgent(FakeAssetStore())
    llm = RevisingFakeLLMClient()
    orchestrator = Orchestrator(
        context_agent,
        asset_agent,
        EmailContentAgent(llm, _email_renderer()),
        WhatsAppContentAgent(llm),
        BrochureContentAgent(llm, FakeBrochureRenderer()),
        ComplianceAgent(),
        ContentLibraryAgent(store),
        HeroImageAgent(FakeImageGenClient()),
        trainer_name="Sakshi Dua",
    )
    return orchestrator, store


def test_revise_email_applies_instruction_without_saving(tmp_path):
    orchestrator, store = _build_revising_orchestrator(tmp_path)
    campaign_brief = _campaign_brief()
    original = orchestrator.generate_drafts(
        CampaignRequest(
            campaign_id="camp-004", topic_id="comm-impact", campaign_brief=campaign_brief, email_brief=EmailBrief()
        )
    )["email"]["draft"]

    revised = orchestrator.revise_email(
        topic_id="comm-impact",
        campaign_brief=campaign_brief,
        email_brief=EmailBrief(),
        current_draft=original,
        instruction="make it shorter",
    )

    assert revised["draft"].subject_lines == ["Shorter subject"]
    assert "Shorter revised body" in revised["draft"].html_body
    assert store.list_by_topic("comm-impact") == []


def test_generate_drafts_email_defaults_to_a_real_photo_hero_not_ai_generation(tmp_path):
    orchestrator = _build_orchestrator(tmp_path)
    request = CampaignRequest(
        campaign_id="camp-005", topic_id="comm-impact", campaign_brief=_campaign_brief(), email_brief=EmailBrief()
    )

    result = orchestrator.generate_drafts(request)["email"]

    # HeroImageSource.SELECTED_PHOTO is the default -- no paid image-gen
    # call unless the user explicitly opts in, so the hero is just the top
    # auto-searched real photo (FakeAssetStore's "a1").
    assert result["draft"].referenced_asset_ids[0] == "a1"


def test_generate_drafts_email_ai_generates_hero_when_explicitly_requested(tmp_path):
    orchestrator = _build_orchestrator(tmp_path)
    request = CampaignRequest(
        campaign_id="camp-005b",
        topic_id="comm-impact",
        campaign_brief=_campaign_brief(),
        email_brief=EmailBrief(hero_image_source=HeroImageSource.AI_GENERATED),
    )

    result = orchestrator.generate_drafts(request)["email"]

    assert result["draft"].referenced_asset_ids[0].startswith("ai-hero-")


def test_generate_drafts_email_lets_daily_image_limit_exceeded_propagate(tmp_path):
    # Explicitly asking for AI generation while the daily cap is already hit
    # must be a clear, visible failure -- not silently degrade to a heroless
    # email, unlike other (transient) image-gen failures.
    class LimitExceededImageGenClient:
        def generate_image(self, prompt: str) -> bytes:
            raise ImageGenerationLimitExceeded("Daily AI image generation limit (10) reached.")

    context_agent = TopicContextAgent(FakeTopicStore())
    asset_agent = AssetAgent(FakeAssetStore())
    llm = RoutingFakeLLMClient()
    orchestrator = Orchestrator(
        context_agent,
        asset_agent,
        EmailContentAgent(llm, _email_renderer()),
        WhatsAppContentAgent(llm),
        BrochureContentAgent(llm, FakeBrochureRenderer()),
        ComplianceAgent(),
        ContentLibraryAgent(ContentLibraryStore(str(tmp_path / "content_library.db"))),
        HeroImageAgent(LimitExceededImageGenClient()),
        trainer_name="Sakshi Dua",
    )
    request = CampaignRequest(
        campaign_id="camp-005c",
        topic_id="comm-impact",
        campaign_brief=_campaign_brief(),
        email_brief=EmailBrief(hero_image_source=HeroImageSource.AI_GENERATED),
    )

    with pytest.raises(ImageGenerationLimitExceeded):
        orchestrator.generate_drafts(request)


def test_generate_drafts_email_skips_hero_generation_when_text_only(tmp_path):
    orchestrator = _build_orchestrator(tmp_path)
    request = CampaignRequest(
        campaign_id="camp-006",
        topic_id="comm-impact",
        campaign_brief=_campaign_brief(),
        email_brief=EmailBrief(imagery=EmailImagery.TEXT_ONLY),
    )

    result = orchestrator.generate_drafts(request)["email"]

    assert result["draft"].referenced_asset_ids == []


def test_revise_email_reuses_existing_ai_generated_hero_without_regenerating(tmp_path):
    orchestrator, _ = _build_revising_orchestrator(tmp_path)
    campaign_brief = _campaign_brief()
    ai_brief = EmailBrief(hero_image_source=HeroImageSource.AI_GENERATED)
    original = orchestrator.generate_drafts(
        CampaignRequest(
            campaign_id="camp-007", topic_id="comm-impact", campaign_brief=campaign_brief, email_brief=ai_brief
        )
    )["email"]["draft"]
    hero_id = original.referenced_asset_ids[0]

    revised = orchestrator.revise_email(
        topic_id="comm-impact",
        campaign_brief=campaign_brief,
        email_brief=ai_brief,
        current_draft=original,
        instruction="make it shorter",
    )

    # Same hero asset_id carried through, not a freshly generated one --
    # revising copy shouldn't burn another paid image-generation call.
    assert revised["draft"].referenced_asset_ids[0] == hero_id


def test_revise_email_does_not_duplicate_hero_into_the_gallery(tmp_path):
    # SELECTED_PHOTO mode: the hero (candidates[0]) must not also reappear
    # as a gallery thumbnail once revise() re-resolves candidate_assets.
    orchestrator, _ = _build_revising_orchestrator(tmp_path)
    campaign_brief = _campaign_brief()
    email_brief = EmailBrief(selected_asset_ids=["a1", "a2"])
    original = orchestrator.generate_drafts(
        CampaignRequest(
            campaign_id="camp-007b", topic_id="comm-impact", campaign_brief=campaign_brief, email_brief=email_brief
        )
    )["email"]["draft"]
    assert original.referenced_asset_ids[0] == "a1"

    revised = orchestrator.revise_email(
        topic_id="comm-impact",
        campaign_brief=campaign_brief,
        email_brief=email_brief,
        current_draft=original,
        instruction="make it shorter",
    )

    assert revised["draft"].referenced_asset_ids.count("a1") == 1


def test_revise_whatsapp_applies_instruction_without_saving(tmp_path):
    orchestrator, store = _build_revising_orchestrator(tmp_path)
    campaign_brief = _campaign_brief()
    original = orchestrator.generate_drafts(
        CampaignRequest(
            campaign_id="camp-005",
            topic_id="comm-impact",
            campaign_brief=campaign_brief,
            whatsapp_brief=WhatsAppBrief(),
        )
    )["whatsapp"]["draft"]

    revised = orchestrator.revise_whatsapp(
        topic_id="comm-impact",
        campaign_brief=campaign_brief,
        whatsapp_brief=WhatsAppBrief(),
        current_draft=original,
        instruction="make it shorter",
    )

    assert "Shorter revised message!" in revised["draft"].message_variants[0]
    assert store.list_by_topic("comm-impact") == []


def test_revise_brochure_only_touches_hero_hook_closing(tmp_path):
    orchestrator, store = _build_revising_orchestrator(tmp_path)
    campaign_brief = _campaign_brief()
    original = orchestrator.generate_drafts(
        CampaignRequest(
            campaign_id="camp-006",
            topic_id="comm-impact",
            campaign_brief=campaign_brief,
            brochure_brief=BrochureBrief(),
        )
    )["brochure"]["draft"]

    revised = orchestrator.revise_brochure(
        topic_id="comm-impact",
        campaign_brief=campaign_brief,
        brochure_brief=BrochureBrief(),
        current_draft=original,
        instruction="punch up the hero",
    )

    assert revised["draft"].content.hero_title == "Shorter Hero Title"
    # modules are still pulled straight from the topic, untouched by revise
    assert revised["draft"].content.modules[0].title == "Structuring Your Message"
    assert store.list_by_topic("comm-impact") == []


def test_generate_more_subject_lines_returns_new_lines_only(tmp_path):
    orchestrator = _build_orchestrator(tmp_path)

    more = orchestrator.generate_more_subject_lines(
        topic_id="comm-impact",
        campaign_brief=_campaign_brief(),
        existing_subject_lines=["Come join Communicate with Impact", "Reserve your seat"],
    )

    assert more == ["Come join Communicate with Impact", "Reserve your seat"]


def test_email_candidate_assets_uses_selected_ids_in_order_when_given(tmp_path):
    orchestrator = _build_orchestrator(tmp_path)
    email_brief = EmailBrief(selected_asset_ids=["a2", "a1"])

    assets = orchestrator._email_candidate_assets("comm-impact", _campaign_brief(), email_brief)

    assert [a.asset_id for a in assets] == ["a2", "a1"]


def test_email_candidate_assets_falls_back_to_tag_search_when_none_selected(tmp_path):
    orchestrator = _build_orchestrator(tmp_path)
    email_brief = EmailBrief()

    assets = orchestrator._email_candidate_assets("comm-impact", _campaign_brief(), email_brief)

    assert {a.asset_id for a in assets} == {"a1", "a2"}


def test_whatsapp_candidate_assets_uses_selected_id_when_given(tmp_path):
    orchestrator = _build_orchestrator(tmp_path)
    whatsapp_brief = WhatsAppBrief(selected_asset_id="a2")

    assets = orchestrator._whatsapp_candidate_assets("comm-impact", _campaign_brief(), whatsapp_brief)

    assert [a.asset_id for a in assets] == ["a2"]


def test_whatsapp_candidate_assets_falls_back_to_tag_search_when_none_selected(tmp_path):
    orchestrator = _build_orchestrator(tmp_path)
    whatsapp_brief = WhatsAppBrief()

    assets = orchestrator._whatsapp_candidate_assets("comm-impact", _campaign_brief(), whatsapp_brief)

    assert {a.asset_id for a in assets} == {"a1", "a2"}


def test_brochure_candidate_assets_returns_topic_photo_bank(tmp_path):
    orchestrator = _build_orchestrator(tmp_path)

    assets = orchestrator._brochure_candidate_assets("comm-impact", _campaign_brief(), BrochureBrief())

    assert {a.asset_id for a in assets} == {"a1", "a2"}


def test_brochure_candidate_assets_uses_selected_ids_in_order_when_given(tmp_path):
    orchestrator = _build_orchestrator(tmp_path)
    brochure_brief = BrochureBrief(selected_asset_ids=["a2", "a1"])

    assets = orchestrator._brochure_candidate_assets("comm-impact", _campaign_brief(), brochure_brief)

    assert [a.asset_id for a in assets] == ["a2", "a1"]
