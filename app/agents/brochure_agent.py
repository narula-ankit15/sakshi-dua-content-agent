import base64
import json
from typing import Optional

from app.agents.llm_client import LLMClient
from app.agents.prompt_helpers import campaign_context_block, topic_content_dict
from app.models import Asset, BrochureContent, BrochureDraft, BrochureLayout, CampaignBrief, Topic
from app.rendering.brochure_renderer import BrochureRenderer

SYSTEM_PROMPT = """You are a corporate-trainer marketing copywriter writing the Hero, Hook, and Closing copy for a
one-page workshop brochure. The brochure's Modules, Methodology, Outcomes, and Positioning Tags sections are fixed
and come directly from TOPIC CONTENT -- you do NOT write those, only the three prose spots below.
Rules:
- Use ONLY the facts given in TOPIC CONTENT and the campaign brief. Never invent modules, outcomes, or methodology.
- The page is a FIXED one-page layout -- every field below has a hard length cap because there is no room to
  grow. Treat these as maximums, not targets: shorter is always safe, longer will get cut off.
- hero_title: max 6 words (the topic name or a close, punchier variant).
- hero_tagline: max 8 words, one line.
- hero_description: ONE sentence, max 18 words.
- hook_lines: exactly 2 lines (not 3), each max 12 words, explaining why this workshop matters, grounded in
  TOPIC CONTENT's hook_description and outcomes -- expand/rephrase, don't just copy hook_description verbatim.
- closing_line: ONE sentence, max 16 words -- can draw from TOPIC CONTENT's closing_line but should reflect
  this campaign's key message and CTA.
- Match the requested audience/tone.
- Return strictly the JSON schema described in the prompt, nothing else.
"""

RESPONSE_SCHEMA_HINT = """Respond with JSON matching exactly:
{
  "hero_title": "...",
  "hero_tagline": "...",
  "hero_description": "...",
  "hook_lines": ["...", "..."],
  "closing_line": "..."
}
hook_lines must have exactly 2 entries. Respect the word-count maximums given above for every field -- this is a
fixed one-page layout with no room to grow.
"""

REVISE_SYSTEM_PROMPT = """You are revising the Hero, Hook, and Closing copy of a one-page workshop brochure based on
the user's feedback. Modules, Methodology, Outcomes, and Positioning Tags are fixed and not part of what you write.
Rules:
- Use ONLY the facts given in TOPIC CONTENT and the campaign brief. Never invent modules, outcomes, or methodology.
- Apply the user's requested change described in USER'S REQUESTED CHANGE to CURRENT DRAFT's hero/hook/closing copy.
  Keep everything else as close to the original as makes sense unless the instruction implies a broader rewrite.
- The page is a FIXED one-page layout with hard length caps (these are maximums, not targets -- shorter is always
  safe): hero_title max 6 words, hero_tagline max 8 words, hero_description one sentence max 18 words, hook_lines
  exactly 2 lines of max 12 words each, closing_line one sentence max 16 words. Stay within these even if the
  instruction doesn't mention length.
- Return strictly the JSON schema described in the prompt, nothing else.
"""

_HERO_FIELDS = {"hero_title", "hero_tagline", "hero_description", "hook_lines", "closing_line"}


class BrochureContentAgent:
    """Unlike Email/WhatsApp, most of a brochure's content (Modules,
    Methodology, Outcomes, Positioning Tags) is never LLM-generated -- it's
    copied verbatim from the Topic record, the same "structured facts are
    reproduced exactly" principle the real-estate version applied to RERA
    numbers and prices. The LLM only writes Hero/Hook/Closing copy. This
    agent then renders the assembled content into the full BrochureDraft
    (HTML + PDF + PNG) via BrochureRenderer, so callers get one draft object
    back, the same shape as EmailContentAgent/WhatsAppContentAgent.
    """

    def __init__(self, llm: LLMClient, renderer: BrochureRenderer):
        self._llm = llm
        self._renderer = renderer

    def generate(
        self,
        *,
        campaign_brief: CampaignBrief,
        topic: Topic,
        layout: BrochureLayout = BrochureLayout.MODERN_GRADIENT,
        candidate_assets: Optional[list[Asset]] = None,
    ) -> BrochureDraft:
        prompt = self._build_prompt(campaign_brief, topic)
        raw = self._llm.generate_json(system=SYSTEM_PROMPT, prompt=prompt)
        content = self._assemble_content(raw, topic)
        return self._render(content, layout, candidate_assets or [])

    def revise(
        self,
        *,
        campaign_brief: CampaignBrief,
        topic: Topic,
        current_draft: BrochureDraft,
        instruction: str,
        layout: BrochureLayout = BrochureLayout.MODERN_GRADIENT,
        candidate_assets: Optional[list[Asset]] = None,
    ) -> BrochureDraft:
        base_prompt = self._build_prompt(campaign_brief, topic)
        current_hero = current_draft.content.model_dump_json(include=_HERO_FIELDS)
        prompt = (
            f"CURRENT DRAFT (hero/hook/closing only -- modules/methodology/outcomes/positioning_tags are fixed "
            f"and not shown here): {current_hero}\n\n"
            f"USER'S REQUESTED CHANGE: {instruction}\n\n"
            f"{base_prompt}"
        )
        raw = self._llm.generate_json(system=REVISE_SYSTEM_PROMPT, prompt=prompt)
        content = self._assemble_content(raw, topic)
        return self._render(content, layout, candidate_assets or [])

    @staticmethod
    def _assemble_content(raw: dict, topic: Topic) -> BrochureContent:
        return BrochureContent(
            hero_title=raw["hero_title"],
            hero_tagline=raw["hero_tagline"],
            hero_description=raw["hero_description"],
            hook_lines=raw["hook_lines"],
            modules=topic.modules,
            methodology=topic.methodology,
            outcomes=topic.outcomes,
            closing_line=raw["closing_line"],
            positioning_tags=topic.positioning_tags,
        )

    def _render(self, content: BrochureContent, layout: BrochureLayout, candidate_assets: list[Asset]) -> BrochureDraft:
        # First candidate is the hero; the next few back a small "from past
        # cohorts" photo strip -- real workshop photos, not stock imagery,
        # since that's what the asset bank actually holds.
        hero_asset = candidate_assets[0] if candidate_assets else None
        gallery_assets = candidate_assets[1:4]
        result = self._renderer.render(
            content,
            layout=layout,
            hero_photo_url=hero_asset.url if hero_asset else None,
            gallery_photo_urls=[a.url for a in gallery_assets],
        )
        used_assets = ([hero_asset] if hero_asset else []) + gallery_assets
        return BrochureDraft(
            content=content,
            html=result["html"],
            pdf_base64=base64.b64encode(result["pdf_bytes"]).decode("ascii"),
            png_base64=base64.b64encode(result["png_bytes"]).decode("ascii"),
            overflowed=result["overflowed"],
            referenced_asset_ids=[a.asset_id for a in used_assets],
        )

    @staticmethod
    def _build_prompt(campaign_brief: CampaignBrief, topic: Topic) -> str:
        return (
            f"{campaign_context_block(campaign_brief)}"
            f"CTA TEXT: {campaign_brief.cta_text}\n\n"
            f"TOPIC CONTENT: {json.dumps(topic_content_dict(topic))}\n\n"
            f"{RESPONSE_SCHEMA_HINT}"
        )
