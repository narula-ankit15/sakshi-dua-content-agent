from app.agents.email_agent import EmailContentAgent
from app.agents.whatsapp_agent import WhatsAppContentAgent
from app.models import Asset, EmailBrief, EmailLayout, WhatsAppBrief
from app.rendering.email_renderer import EmailRenderer


class FakeLLMClient:
    """Returns a canned response and records the last prompt/system it was
    called with, so tests can assert on what the agent actually sent.
    """

    def __init__(self, response: dict):
        self._response = response
        self.last_system = None
        self.last_prompt = None

    def generate_json(self, *, system: str, prompt: str) -> dict:
        self.last_system = system
        self.last_prompt = prompt
        return self._response


def _email_content_response(**overrides) -> dict:
    base = {
        "subject_lines": ["Reserve your seat for Communicate with Impact", "Book this weekend's workshop"],
        "eyebrow": "Workshop",
        "headline": "Communicate with Impact",
        "intro_text": "A hands-on session for your team.",
        "bullet_line": None,
        "items": [],
        "closing_text": "See you there.",
    }
    base.update(overrides)
    return base


def test_email_agent_parses_llm_response_into_content_and_draft(
    sample_campaign_brief, sample_email_brief, sample_topic
):
    fake_llm = FakeLLMClient(_email_content_response())
    renderer = EmailRenderer(trainer_name="Sakshi Dua", trainer_contact="sakshi@example.com")
    agent = EmailContentAgent(fake_llm, renderer)

    draft = agent.generate(campaign_brief=sample_campaign_brief, email_brief=sample_email_brief, topic=sample_topic)

    assert len(draft.subject_lines) == 2
    assert draft.content.headline == "Communicate with Impact"
    assert "Communicate with Impact" in draft.html_body
    # topic content the model must not hallucinate should actually reach the prompt
    assert "Structuring Your Message" in fake_llm.last_prompt
    assert "Role Plays" in fake_llm.last_prompt
    # cta_text lives on the shared campaign brief, not the email brief
    assert "Reserve your seat" in fake_llm.last_prompt
    # unlike the old freeform-HTML design, the LLM never needs to know
    # about images/asset_ids at all -- that's resolved entirely by code
    assert "asset_id" not in fake_llm.last_prompt.lower()


def test_email_agent_zips_hero_and_item_assets_into_referenced_ids_in_render_order(
    sample_campaign_brief, sample_topic, sample_assets
):
    hero_asset = Asset(
        asset_id="ai-hero-1", topic_id="comm-impact", url="https://cdn/hero.png", kind="image", tags=["ai_generated_hero"]
    )
    email_brief = EmailBrief(layout=EmailLayout.HERO_THREE_COLUMN)
    fake_llm = FakeLLMClient(
        _email_content_response(
            items=[
                {"title": "A", "text": "a", "cta_text": None},
                {"title": "B", "text": "b", "cta_text": None},
            ]
        )
    )
    renderer = EmailRenderer(trainer_name="Sakshi Dua")
    agent = EmailContentAgent(fake_llm, renderer)

    draft = agent.generate(
        campaign_brief=sample_campaign_brief,
        email_brief=email_brief,
        topic=sample_topic,
        hero_asset=hero_asset,
        item_assets=sample_assets,
    )

    # Hero always first, deterministic code choice -- then items in the
    # order they were resolved, regardless of what the LLM wrote.
    assert draft.referenced_asset_ids == ["ai-hero-1"] + [a.asset_id for a in sample_assets]
    assert "hero.png" in draft.html_body
    for asset in sample_assets:
        assert asset.url in draft.html_body


def test_email_agent_layout_guidance_reaches_prompt(sample_campaign_brief, sample_topic):
    email_brief = EmailBrief(layout=EmailLayout.EVENT)
    fake_llm = FakeLLMClient(_email_content_response(bullet_line="Saturday, 10am"))
    renderer = EmailRenderer(trainer_name="")
    agent = EmailContentAgent(fake_llm, renderer)

    agent.generate(campaign_brief=sample_campaign_brief, email_brief=email_brief, topic=sample_topic)

    assert "LAYOUT: Event" in fake_llm.last_prompt
    assert "EXACTLY 3" in fake_llm.last_prompt


def test_email_agent_workshop_highlights_pulls_topic_content_verbatim_not_from_llm(
    sample_campaign_brief, sample_topic
):
    email_brief = EmailBrief(layout=EmailLayout.WORKSHOP_HIGHLIGHTS)
    fake_llm = FakeLLMClient(_email_content_response())
    renderer = EmailRenderer(trainer_name="")
    agent = EmailContentAgent(fake_llm, renderer)

    draft = agent.generate(campaign_brief=sample_campaign_brief, email_brief=email_brief, topic=sample_topic)

    # Modules/methodology/outcomes come from the Topic record verbatim, the
    # same "structured facts reproduced exactly" principle Brochure uses --
    # not something the fake LLM response above ever provided.
    assert draft.content.modules == sample_topic.modules
    assert draft.content.methodology == sample_topic.methodology
    assert draft.content.outcomes == sample_topic.outcomes


def test_email_agent_revise_edits_copy_and_rerenders(sample_campaign_brief, sample_email_brief, sample_topic):
    renderer = EmailRenderer(trainer_name="")
    fake_llm = FakeLLMClient(_email_content_response())
    agent = EmailContentAgent(fake_llm, renderer)
    current = agent.generate(campaign_brief=sample_campaign_brief, email_brief=sample_email_brief, topic=sample_topic)

    fake_llm._response = _email_content_response(headline="Shorter Headline", intro_text="Short.")
    revised = agent.revise(
        campaign_brief=sample_campaign_brief,
        email_brief=sample_email_brief,
        topic=sample_topic,
        current_draft=current,
        instruction="make it shorter",
    )

    assert revised.content.headline == "Shorter Headline"
    assert "Shorter Headline" in revised.html_body
    assert "CURRENT DRAFT" in fake_llm.last_prompt
    assert "make it shorter" in fake_llm.last_prompt


def test_email_agent_generates_more_subject_lines_without_touching_rest_of_draft(
    sample_campaign_brief, sample_topic
):
    fake_llm = FakeLLMClient({"subject_lines": ["A fresh angle 🎯", "Another new hook ✨", "Third option 🧠"]})
    renderer = EmailRenderer(trainer_name="")
    agent = EmailContentAgent(fake_llm, renderer)

    existing = ["Reserve your seat for Communicate with Impact", "Book this weekend's workshop"]
    more = agent.generate_more_subject_lines(
        campaign_brief=sample_campaign_brief, topic=sample_topic, existing_subject_lines=existing
    )

    assert more == ["A fresh angle 🎯", "Another new hook ✨", "Third option 🧠"]
    # the existing lines must be shown to the model so it doesn't repeat them
    assert "Reserve your seat for Communicate with Impact" in fake_llm.last_prompt
    assert "Structuring Your Message" in fake_llm.last_prompt


def test_whatsapp_agent_selects_image_when_required(
    sample_campaign_brief, sample_whatsapp_brief, sample_topic, sample_assets
):
    fake_llm = FakeLLMClient(
        {
            "message_variants": [
                "Reserve your seat for Communicate with Impact this weekend! 🎯",
                "Your team's next communication upgrade starts here ✨",
            ],
            "cta_variants": ["Reserve your seat", "Reserve your seat"],
            "image_asset_id": "asset-roleplay-1",
        }
    )
    agent = WhatsAppContentAgent(fake_llm)

    draft = agent.generate(
        campaign_brief=sample_campaign_brief,
        whatsapp_brief=sample_whatsapp_brief,
        topic=sample_topic,
        candidate_assets=sample_assets,
    )

    assert len(draft.message_variants) == 2
    assert draft.image_asset_id == "asset-roleplay-1"
    assert "asset-roleplay-1" in fake_llm.last_prompt
    # the prompt should ask for at least 2 variants, not a single message
    assert "message_variants" in fake_llm.last_prompt
    # the prompt should push for a line-broken, partly-bold message, not a
    # single flowing paragraph -- this is what backs the WhatsApp-style
    # formatting (details as separate lines, key facts in *bold*).
    assert "FORMATTING" in fake_llm.last_prompt
    assert "single asterisks" in fake_llm.last_prompt


def test_whatsapp_agent_forces_selected_asset_id_even_if_llm_picks_differently(
    sample_campaign_brief, sample_topic, sample_assets
):
    whatsapp_brief = WhatsAppBrief(cta_required=True, image_required=True, selected_asset_id="asset-group-1")
    # LLM ignores the instruction and picks the other candidate -- the agent
    # must still force it back to the user's explicit pick.
    fake_llm = FakeLLMClient(
        {
            "message_variants": ["Join us for Communicate with Impact.", "Reserve your seat today."],
            "cta_variants": ["Reserve your seat", "Reserve your seat"],
            "image_asset_id": "asset-roleplay-1",
        }
    )
    agent = WhatsAppContentAgent(fake_llm)

    draft = agent.generate(
        campaign_brief=sample_campaign_brief,
        whatsapp_brief=whatsapp_brief,
        topic=sample_topic,
        candidate_assets=[a for a in sample_assets if a.asset_id == "asset-group-1"],
    )

    assert draft.image_asset_id == "asset-group-1"
    assert "explicitly picked" in fake_llm.last_prompt
    assert "asset-group-1" in fake_llm.last_prompt


def test_whatsapp_agent_skips_asset_selection_when_image_not_required(
    sample_campaign_brief, sample_topic, sample_assets
):
    whatsapp_brief = WhatsAppBrief(cta_required=True, image_required=False)
    # LLM misbehaves and returns an id anyway -- the agent must still null it out.
    fake_llm = FakeLLMClient(
        {
            "message_variants": ["Join us for Communicate with Impact."],
            "cta_variants": ["Reserve your seat"],
            "image_asset_id": "asset-roleplay-1",
        }
    )
    agent = WhatsAppContentAgent(fake_llm)

    draft = agent.generate(
        campaign_brief=sample_campaign_brief,
        whatsapp_brief=whatsapp_brief,
        topic=sample_topic,
        candidate_assets=sample_assets,
    )

    assert draft.image_asset_id is None
    # candidate assets should never have been shown to the model at all
    assert "asset-roleplay-1" not in fake_llm.last_prompt


def test_whatsapp_agent_nulls_cta_when_not_required(sample_campaign_brief, sample_topic, sample_assets):
    whatsapp_brief = WhatsAppBrief(cta_required=False, image_required=False)
    # LLM misbehaves and returns cta_variants anyway -- the agent must still null it out.
    fake_llm = FakeLLMClient(
        {
            "message_variants": ["Join us for Communicate with Impact."],
            "cta_variants": ["Reserve now"],
            "image_asset_id": None,
        }
    )
    agent = WhatsAppContentAgent(fake_llm)

    draft = agent.generate(
        campaign_brief=sample_campaign_brief,
        whatsapp_brief=whatsapp_brief,
        topic=sample_topic,
        candidate_assets=sample_assets,
    )

    assert draft.cta_variants is None


def test_whatsapp_agent_assigns_one_cta_per_variant_when_two_options_given(
    sample_campaign_brief, sample_topic, sample_assets
):
    whatsapp_brief = WhatsAppBrief(cta_required=True, image_required=False, secondary_cta_text="Call now")
    fake_llm = FakeLLMClient(
        {
            "message_variants": ["Variant one copy.", "Variant two copy.", "Variant three copy."],
            "cta_variants": ["Reserve your seat", "Call now", "Reserve your seat"],
            "image_asset_id": None,
        }
    )
    agent = WhatsAppContentAgent(fake_llm)

    draft = agent.generate(
        campaign_brief=sample_campaign_brief,
        whatsapp_brief=whatsapp_brief,
        topic=sample_topic,
        candidate_assets=sample_assets,
    )

    assert draft.cta_variants == ["Reserve your seat", "Call now", "Reserve your seat"]
    # both CTA options should reach the prompt so the model can assign them
    assert "Reserve your seat" in fake_llm.last_prompt
    assert "Call now" in fake_llm.last_prompt


def test_whatsapp_agent_rebuilds_cta_variants_when_llm_returns_wrong_length(
    sample_campaign_brief, sample_topic, sample_assets
):
    whatsapp_brief = WhatsAppBrief(cta_required=True, image_required=False, secondary_cta_text="Call now")
    # LLM only returns 1 cta_variant despite 2 message_variants -- the agent
    # must rebuild the list itself rather than trust the model's count.
    fake_llm = FakeLLMClient(
        {
            "message_variants": ["Variant one copy.", "Variant two copy."],
            "cta_variants": ["Reserve your seat"],
            "image_asset_id": None,
        }
    )
    agent = WhatsAppContentAgent(fake_llm)

    draft = agent.generate(
        campaign_brief=sample_campaign_brief,
        whatsapp_brief=whatsapp_brief,
        topic=sample_topic,
        candidate_assets=sample_assets,
    )

    assert draft.cta_variants == ["Reserve your seat", "Call now"]
