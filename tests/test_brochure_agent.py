import base64

from app.agents.brochure_agent import BrochureContentAgent


class FakeLLMClient:
    def __init__(self, response: dict):
        self._response = response
        self.last_system = None
        self.last_prompt = None

    def generate_json(self, *, system: str, prompt: str) -> dict:
        self.last_system = system
        self.last_prompt = prompt
        return self._response


class FakeRenderer:
    def __init__(self):
        self.last_content = None
        self.last_layout = None
        self.last_hero_photo_url = None
        self.last_gallery_photo_urls = None

    def render(self, content, layout=None, hero_photo_url=None, gallery_photo_urls=None):
        self.last_content = content
        self.last_layout = layout
        self.last_hero_photo_url = hero_photo_url
        self.last_gallery_photo_urls = gallery_photo_urls
        return {"html": "<html>rendered</html>", "pdf_bytes": b"pdf-bytes", "png_bytes": b"png-bytes", "overflowed": False}


_HERO_RESPONSE = {
    "hero_title": "Communicate with Impact",
    "hero_tagline": "Say less, land more.",
    "hero_description": "A hands-on workshop for teams whose ideas keep getting lost in the delivery.",
    "hook_lines": ["Teams lose deals from how ideas get said.", "This workshop closes that gap."],
    "closing_line": "Communication is the multiplier on everything else your team does well.",
}


def test_generate_copies_modules_methodology_outcomes_verbatim_from_topic(sample_campaign_brief, sample_topic, sample_assets):
    fake_llm = FakeLLMClient(_HERO_RESPONSE)
    renderer = FakeRenderer()
    agent = BrochureContentAgent(fake_llm, renderer)

    draft = agent.generate(campaign_brief=sample_campaign_brief, topic=sample_topic, candidate_assets=sample_assets)

    # Modules/methodology/outcomes/positioning_tags are never sent through
    # the LLM -- they must match the Topic record exactly.
    assert draft.content.modules == sample_topic.modules
    assert draft.content.methodology == sample_topic.methodology
    assert draft.content.outcomes == sample_topic.outcomes
    assert draft.content.positioning_tags == sample_topic.positioning_tags
    assert draft.content.hero_title == "Communicate with Impact"
    # topic content must reach the prompt so the LLM's hero/hook/closing
    # copy is actually grounded in it
    assert "Structuring Your Message" in fake_llm.last_prompt


def test_generate_renders_using_first_candidate_asset_as_hero_and_rest_as_gallery(
    sample_campaign_brief, sample_topic, sample_assets
):
    fake_llm = FakeLLMClient(_HERO_RESPONSE)
    renderer = FakeRenderer()
    agent = BrochureContentAgent(fake_llm, renderer)

    draft = agent.generate(campaign_brief=sample_campaign_brief, topic=sample_topic, candidate_assets=sample_assets)

    assert renderer.last_hero_photo_url == sample_assets[0].url
    assert renderer.last_gallery_photo_urls == [a.url for a in sample_assets[1:]]
    assert draft.referenced_asset_ids == [a.asset_id for a in sample_assets]
    assert draft.html == "<html>rendered</html>"
    assert base64.b64decode(draft.pdf_base64) == b"pdf-bytes"
    assert base64.b64decode(draft.png_base64) == b"png-bytes"
    assert draft.overflowed is False


def test_generate_with_no_candidate_assets_renders_without_a_hero_photo(sample_campaign_brief, sample_topic):
    fake_llm = FakeLLMClient(_HERO_RESPONSE)
    renderer = FakeRenderer()
    agent = BrochureContentAgent(fake_llm, renderer)

    draft = agent.generate(campaign_brief=sample_campaign_brief, topic=sample_topic, candidate_assets=[])

    assert renderer.last_hero_photo_url is None
    assert renderer.last_gallery_photo_urls == []
    assert draft.referenced_asset_ids == []


def test_revise_only_touches_hero_hook_closing_not_topic_content(sample_campaign_brief, sample_topic, sample_assets):
    fake_llm = FakeLLMClient(_HERO_RESPONSE)
    renderer = FakeRenderer()
    agent = BrochureContentAgent(fake_llm, renderer)

    current = agent.generate(campaign_brief=sample_campaign_brief, topic=sample_topic, candidate_assets=sample_assets)

    revised_response = dict(_HERO_RESPONSE, hero_title="Communicate with Impact (Updated)")
    fake_llm._response = revised_response

    revised = agent.revise(
        campaign_brief=sample_campaign_brief,
        topic=sample_topic,
        current_draft=current,
        instruction="punch up the hero title",
        candidate_assets=sample_assets,
    )

    assert revised.content.hero_title == "Communicate with Impact (Updated)"
    assert revised.content.modules == sample_topic.modules
    assert "CURRENT DRAFT" in fake_llm.last_prompt
    assert "punch up the hero title" in fake_llm.last_prompt
    # modules/methodology/outcomes must never be shown as part of the
    # editable current draft -- only hero/hook/closing are revisable
    current_hero_dump = current.content.model_dump_json(
        include={"hero_title", "hero_tagline", "hero_description", "hook_lines", "closing_line"}
    )
    assert "module_number" not in current_hero_dump
    assert current_hero_dump in fake_llm.last_prompt
