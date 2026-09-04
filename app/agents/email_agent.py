import json
from typing import Optional

from app.agents.llm_client import LLMClient
from app.agents.prompt_helpers import campaign_context_block, topic_content_dict
from app.models import (
    Asset,
    CampaignBrief,
    EmailBrief,
    EmailContent,
    EmailContentItem,
    EmailDraft,
    EmailLayout,
    EmailLength,
    Topic,
)
from app.rendering.email_renderer import EmailRenderer

SYSTEM_PROMPT = """You are a workshop-trainer marketing copywriter writing ONLY the copy for a promotional email --
the email's visual structure is a fixed, pre-built template (chosen by LAYOUT below), so you never write HTML,
image references, or the footer, only the text that drops into it.
Rules:
- Use ONLY the facts given in TOPIC CONTENT. Never invent module titles, outcomes, or methodology that aren't
  listed there, and never invent dates, seat counts, or prices that aren't in KEY MESSAGE/CTA TEXT.
- Match the requested audience/tone.
- Follow LAYOUT below exactly -- which fields to write, exactly how many entries `items` must have, and which
  fields to leave null/empty because that layout doesn't use them.
- Every field fills a fixed-width slot in a pre-built template with no room to grow -- keep things tight (see
  LENGTH for how much detail to give). Shorter is always safe; longer risks getting visually cut off.
- No emoji anywhere in eyebrow/headline/intro_text/bullet_line/items/closing_text (subject_lines are the one
  exception -- see below).
- Use a tasteful emoji in most subject_lines where it fits the tone naturally (e.g. training-relevant: 🎯 🧠 📈 🗣️ ✨) -- skip emojis entirely for a b2b_professional or internal_team audience. This is the only place emoji belong.
- Return strictly the JSON schema described in the prompt, nothing else.
"""

RESPONSE_SCHEMA_HINT = """Respond with JSON matching exactly:
{
  "subject_lines": ["...", "...", "..."],
  "eyebrow": "..." or null,
  "headline": "...",
  "intro_text": "...",
  "bullet_line": "..." or null,
  "items": [{"title": "...", "text": "...", "cta_text": "..." or null}],
  "closing_text": "..."
}
subject_lines must have 2-3 variants for A/B testing, each meaningfully different (not minor rewording), most
using a tasteful emoji per the system rules. Follow LAYOUT exactly for which fields to fill, how many entries
`items` must have, and which fields to leave null/empty -- do not add extra items or fields beyond what LAYOUT
specifies.
"""

MORE_SUBJECT_LINES_SYSTEM_PROMPT = """You generate additional email subject line options for a corporate workshop
marketing campaign.
Rules:
- Use ONLY the facts given in TOPIC CONTENT. Never invent module titles, outcomes, or methodology not listed there.
- Match the requested audience/tone.
- Generate subject lines that take a meaningfully different angle from both each other and from EXISTING SUBJECT
  LINES -- new hooks/emphasis, not minor rewording of what's already there.
- Use a tasteful emoji in most subject lines where it fits the tone naturally (e.g. training-relevant: 🎯 🧠 📈 🗣️ ✨) -- skip emojis entirely for a b2b_professional or internal_team audience.
- Return strictly the JSON schema described in the prompt, nothing else.
"""

MORE_SUBJECT_LINES_RESPONSE_SCHEMA_HINT = """Respond with JSON matching exactly:
{
  "subject_lines": ["...", "...", "..."]
}
Generate exactly 3 new subject lines. Do not repeat or lightly reword any line from EXISTING SUBJECT LINES.
"""

REVISE_SYSTEM_PROMPT = """You are revising the copy of a previously generated marketing email based on the user's
feedback. The email's visual structure is a fixed template -- you're only ever editing the copy fields, never HTML.
Rules:
- Use ONLY the facts given in TOPIC CONTENT. Never invent module titles, outcomes, or methodology not listed there.
- Apply the user's requested change described in USER'S REQUESTED CHANGE to CURRENT DRAFT. Keep everything else
  about the draft as close to the original as makes sense, unless the instruction implies a broader rewrite.
- Still follow the original LENGTH and LAYOUT guidance below unless the instruction explicitly asks to change one
  of those -- in particular, `items` must still have exactly the count LAYOUT requires.
- Still use a tasteful emoji in most subject_lines (skip for b2b_professional/internal_team) unless the
  instruction explicitly asks to change that. No emoji anywhere else, same as the original rules.
- Return strictly the JSON schema described in the prompt, nothing else.
"""

_LENGTH_GUIDANCE = {
    EmailLength.SHORT: "Keep every field tight and punchy -- short headline, one crisp intro sentence, brief item text.",
    EmailLength.MEDIUM: "Give each field a normal amount of copy -- a clear headline, a full intro sentence, and a proper phrase for each item.",
    EmailLength.LONG: (
        "Go slightly fuller in intro_text and closing_text. Item text stays short regardless of LENGTH -- those "
        "sit in fixed-width cells with no room to grow."
    ),
}

_LAYOUT_GUIDANCE = {
    EmailLayout.HERO_THREE_COLUMN: (
        "LAYOUT: Hero + 3-Column. Write eyebrow (optional short label, or null), headline (punchy, topic-"
        "grounded), intro_text (ONE supporting sentence under the headline). items must have EXACTLY 3 entries, "
        "each a short column highlight: title (2-5 words), text (one short phrase), and cta_text (optional 2-3 "
        "word button label of your own -- distinct from the main CTA -- only for a column that genuinely deserves "
        "its own action, otherwise null). closing_text: one short closing line. bullet_line is unused by this "
        "layout -- leave it null."
    ),
    EmailLayout.EVENT: (
        "LAYOUT: Event. Write eyebrow (optional, e.g. a save-the-date style label, or null), headline, intro_text "
        "(one supporting sentence), and bullet_line (ONE short logistics/detail line, e.g. timing or format). "
        "items must have EXACTLY 3 entries (title: 2-4 words, text: one short phrase each, cta_text always null -- "
        "this layout's columns don't have their own buttons). closing_text: one short closing line."
    ),
    EmailLayout.MINIMAL_ANNOUNCEMENT: (
        "LAYOUT: Minimal Announcement. This is text-light and image-led -- write headline (punchy, topic-"
        "grounded) and intro_text (1-2 sentences -- this is the main copy of the whole email). items must have "
        "EXACTLY 2 entries; their title/text are not shown in this layout, so keep them brief placeholders. "
        "closing_text: one short closing line shown under the second image. eyebrow and bullet_line are unused -- "
        "leave them null."
    ),
    EmailLayout.WELCOME_GRID: (
        "LAYOUT: Welcome Grid. Write eyebrow (optional, or null), headline, intro_text (one supporting sentence "
        "under the hero image). items must have EXACTLY 4 entries for a 2x2 grid (title: 2-4 words, text: one "
        "short phrase each, cta_text always null). closing_text: one short closing line. bullet_line is unused -- "
        "leave it null."
    ),
    EmailLayout.WORKSHOP_HIGHLIGHTS: (
        "LAYOUT: Workshop Highlights. Write ONLY eyebrow (optional, or null), headline, intro_text (one "
        "supporting sentence), and closing_text (one short line). items MUST be an empty list -- this layout's "
        "module highlights, methodology chips, and outcome/module counts are pulled directly from TOPIC CONTENT "
        "by the platform, never written by you. bullet_line is unused -- leave it null."
    ),
}


class EmailContentAgent:
    """Mirrors BrochureContentAgent's division of labor: the LLM writes only
    the copy (EmailContent), and a deterministic EmailRenderer assembles it
    into one of five fixed HTML templates (EmailLayout) -- never full HTML
    from the model itself. That's what makes "the right number of images at
    the right size" an actual guarantee instead of a prompt hint, and it
    means trainer identity/footer/CTA button are 100% code-controlled, the
    same fabrication-proofing principle Brochure already uses.
    """

    def __init__(self, llm: LLMClient, renderer: EmailRenderer):
        self._llm = llm
        self._renderer = renderer

    def generate(
        self,
        *,
        campaign_brief: CampaignBrief,
        email_brief: EmailBrief,
        topic: Topic,
        hero_asset: Optional[Asset] = None,
        item_assets: Optional[list[Asset]] = None,
    ) -> EmailDraft:
        prompt = self._build_prompt(campaign_brief, email_brief, topic)
        raw = self._llm.generate_json(system=SYSTEM_PROMPT, prompt=prompt)
        content = self._assemble_content(raw, email_brief.layout, topic)
        return self._render(
            raw.get("subject_lines") or [],
            content,
            email_brief.layout,
            campaign_brief.cta_text,
            topic.positioning_tags,
            hero_asset,
            item_assets or [],
        )

    def revise(
        self,
        *,
        campaign_brief: CampaignBrief,
        email_brief: EmailBrief,
        topic: Topic,
        current_draft: EmailDraft,
        instruction: str,
        hero_asset: Optional[Asset] = None,
        item_assets: Optional[list[Asset]] = None,
    ) -> EmailDraft:
        base_prompt = self._build_prompt(campaign_brief, email_brief, topic)
        current_content_json = current_draft.content.model_dump_json() if current_draft.content else "{}"
        prompt = (
            f"CURRENT DRAFT (copy fields only -- apply the requested change to these): {current_content_json}\n\n"
            f"USER'S REQUESTED CHANGE: {instruction}\n\n"
            f"{base_prompt}"
        )
        raw = self._llm.generate_json(system=REVISE_SYSTEM_PROMPT, prompt=prompt)
        content = self._assemble_content(raw, email_brief.layout, topic)
        return self._render(
            raw.get("subject_lines") or [],
            content,
            email_brief.layout,
            campaign_brief.cta_text,
            topic.positioning_tags,
            hero_asset,
            item_assets or [],
        )

    @staticmethod
    def _assemble_content(raw: dict, layout: EmailLayout, topic: Topic) -> EmailContent:
        items = [EmailContentItem.model_validate(item) for item in (raw.get("items") or [])]
        content = EmailContent(
            eyebrow=raw.get("eyebrow"),
            headline=raw["headline"],
            intro_text=raw["intro_text"],
            bullet_line=raw.get("bullet_line"),
            items=items,
            closing_text=raw["closing_text"],
        )
        if layout == EmailLayout.WORKSHOP_HIGHLIGHTS:
            # Structured facts reproduced exactly, never rephrased by the
            # LLM -- same principle BrochureContentAgent applies to modules/
            # methodology/outcomes.
            content = content.model_copy(
                update={"modules": topic.modules, "methodology": topic.methodology, "outcomes": topic.outcomes}
            )
        return content

    def _render(
        self,
        subject_lines: list[str],
        content: EmailContent,
        layout: EmailLayout,
        cta_text: str,
        positioning_tags: list[str],
        hero_asset: Optional[Asset],
        item_assets: list[Asset],
    ) -> EmailDraft:
        html = self._renderer.render(
            content,
            layout,
            cta_text=cta_text,
            positioning_tags=positioning_tags,
            hero_photo_url=hero_asset.url if hero_asset else None,
            item_photo_urls=[a.url for a in item_assets],
        )
        used_assets = ([hero_asset] if hero_asset else []) + item_assets
        return EmailDraft(
            subject_lines=subject_lines,
            html_body=html,
            referenced_asset_ids=[a.asset_id for a in used_assets],
            content=content,
        )

    def generate_more_subject_lines(
        self,
        *,
        campaign_brief: CampaignBrief,
        topic: Topic,
        existing_subject_lines: list[str],
    ) -> list[str]:
        """Generates additional subject line options without touching the
        rest of the draft -- backs the "generate more options" action in the
        subject line picker, which shouldn't have to regenerate the whole
        email just to get a couple more headlines to choose from.
        """
        prompt = (
            f"{campaign_context_block(campaign_brief)}"
            f"EXISTING SUBJECT LINES: {json.dumps(existing_subject_lines)}\n\n"
            f"TOPIC CONTENT: {json.dumps(topic_content_dict(topic))}\n\n"
            f"{MORE_SUBJECT_LINES_RESPONSE_SCHEMA_HINT}"
        )
        raw = self._llm.generate_json(system=MORE_SUBJECT_LINES_SYSTEM_PROMPT, prompt=prompt)
        return list(raw.get("subject_lines") or [])

    def _build_prompt(self, campaign_brief: CampaignBrief, email_brief: EmailBrief, topic: Topic) -> str:
        design_note = f"DESIGN SYSTEM: {email_brief.design_system_id}\n" if email_brief.design_system_id else ""
        return (
            f"{campaign_context_block(campaign_brief)}"
            f"CTA TEXT (the main button -- already set by the platform, you don't need to repeat it): "
            f"{campaign_brief.cta_text}\n"
            f"LENGTH: {_LENGTH_GUIDANCE[email_brief.length]}\n"
            f"{design_note}"
            f"{_LAYOUT_GUIDANCE[email_brief.layout]}\n\n"
            f"TOPIC CONTENT: {json.dumps(topic_content_dict(topic))}\n\n"
            f"{RESPONSE_SCHEMA_HINT}"
        )
