import json
from typing import Optional

from app.agents.llm_client import LLMClient
from app.agents.prompt_helpers import campaign_context_block, topic_content_dict
from app.models import Asset, CampaignBrief, Topic, WhatsAppBrief, WhatsAppDraft, WhatsAppLength

SYSTEM_PROMPT = """You are a corporate-trainer marketing copywriter generating a WhatsApp/SMS message for a
workshop promotion campaign.
Rules:
- Use ONLY the facts given in TOPIC CONTENT. Never invent module titles, outcomes, methodology, dates, or seat
  counts that aren't given.
- Match the requested audience/tone.
- Generate at least 2 distinct message_variants (different opening lines / phrasing / emphasis), not just minor rewording -- like A/B test candidates. image_asset_id is shared across all variants, only the message copy and CTA vary.
- Use emojis where they fit the tone naturally (e.g. training-relevant: 🎯 🧠 📈 🗣️ ✨) -- tasteful and not excessive, skip them entirely for a b2b_professional or internal_team audience.
- Follow the CTA instruction exactly -- only include a call to action if told to.
- Follow the IMAGE instruction exactly -- only select an image_asset_id if told to, and never invent one.
- Follow the FORMATTING rules below -- a real WhatsApp business message, not a text-message paragraph.
- Return strictly the JSON schema described in the prompt, nothing else.
"""

FORMATTING_GUIDANCE = """FORMATTING: Write each message_variant as a short, line-broken WhatsApp message, like a bank
or insurer's automated alert -- never one run-on paragraph. Use literal \\n characters (blank line = \\n\\n) to
separate:
  1. A one-line opening hook/headline.
  2. If there are 2+ discrete facts to state (workshop date, seats left, a specific module highlight, price, etc.),
     a short lead-in line ("Here are the details:" or similar) followed by each fact on its own line as
     "Label: value" -- do not weave them into a sentence.
  3. A short closing line (the CTA lead-in, or a one-line takeaway) -- WITHOUT restating the cta button text.
Skip the details-list structure only for very short/simple messages with a single fact; even then, keep the
opening line and closing line on separate lines rather than one paragraph.
Wrap 2-4 of the most important words/phrases per variant (a date, a module name, a key outcome) in single asterisks
for WhatsApp bold, e.g. "seats open for *Communicate with Impact*" or "*early-bird pricing* ends Friday" -- never
wrap a whole sentence, and never use double asterisks or markdown headers (WhatsApp doesn't render those)."""

RESPONSE_SCHEMA_HINT = """Respond with JSON matching exactly:
{
  "message_variants": ["...", "..."],
  "cta_variants": ["...", "..."] or null,
  "image_asset_id": "..." or null
}
message_variants must have at least 2 distinct variants, each formatted per the FORMATTING rules (line breaks as
literal \\n characters within the JSON string, key facts wrapped in single asterisks for bold). If a CTA is
required, cta_variants must be the exact same length as message_variants (one CTA per variant, cycling through
the CTA OPTIONS given below in order); otherwise cta_variants must be null.
"""

_LENGTH_GUIDANCE = {
    WhatsAppLength.SHORT: "Keep each message variant under 150 characters.",
    WhatsAppLength.STANDARD: "Keep each message variant under 300 characters.",
}

REVISE_SYSTEM_PROMPT = """You are revising a previously generated WhatsApp/SMS message based on the user's feedback.
Rules:
- Use ONLY the facts given in TOPIC CONTENT. Never invent module titles, outcomes, methodology, dates, or seat
  counts that aren't given.
- Apply the user's requested change described in USER'S REQUESTED CHANGE to every variant in CURRENT DRAFT's
  message_variants. Keep everything else about the draft as close to the original as makes sense, unless the
  instruction implies a broader rewrite. Still return at least 2 distinct variants.
- Still follow the original CTA and IMAGE instructions below unless the instruction explicitly asks to change them.
  If CURRENT DRAFT had cta_variants, keep the same CTA text(s) assigned to the same variants unless the
  instruction is specifically about the CTA.
- Still follow the FORMATTING rules below -- keep the line-broken, partly-bolded structure unless the instruction
  explicitly asks to change that (e.g. "make it one line").
- Return strictly the JSON schema described in the prompt, nothing else.
"""


class WhatsAppContentAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def generate(
        self,
        *,
        campaign_brief: CampaignBrief,
        whatsapp_brief: WhatsAppBrief,
        topic: Topic,
        candidate_assets: Optional[list[Asset]] = None,
    ) -> WhatsAppDraft:
        # If the brief says no image, don't even show the model candidates --
        # it can't pick what it never sees.
        assets = (candidate_assets or []) if whatsapp_brief.image_required else []
        prompt = self._build_prompt(campaign_brief, whatsapp_brief, topic, assets)
        raw = self._llm.generate_json(system=SYSTEM_PROMPT, prompt=prompt)
        draft = WhatsAppDraft.model_validate(raw)

        # Belt-and-suspenders: an LLM can still ignore the prompt, so enforce
        # both flags in code too. A single image_asset_id field makes a
        # user's explicit pick trivial to force outright, unlike email's
        # multi-asset hero+gallery layout which can't collapse to one field.
        if not whatsapp_brief.image_required:
            draft.image_asset_id = None
        elif whatsapp_brief.selected_asset_id:
            draft.image_asset_id = whatsapp_brief.selected_asset_id
        self._normalize_cta_variants(draft, campaign_brief, whatsapp_brief)
        return draft

    def revise(
        self,
        *,
        campaign_brief: CampaignBrief,
        whatsapp_brief: WhatsAppBrief,
        topic: Topic,
        current_draft: WhatsAppDraft,
        instruction: str,
        candidate_assets: Optional[list[Asset]] = None,
    ) -> WhatsAppDraft:
        assets = (candidate_assets or []) if whatsapp_brief.image_required else []
        base_prompt = self._build_prompt(campaign_brief, whatsapp_brief, topic, assets)
        prompt = (
            f"CURRENT DRAFT: {current_draft.model_dump_json()}\n\n"
            f"USER'S REQUESTED CHANGE: {instruction}\n\n"
            f"{base_prompt}"
        )
        raw = self._llm.generate_json(system=REVISE_SYSTEM_PROMPT, prompt=prompt)
        draft = WhatsAppDraft.model_validate(raw)

        if not whatsapp_brief.image_required:
            draft.image_asset_id = None
        elif whatsapp_brief.selected_asset_id:
            draft.image_asset_id = whatsapp_brief.selected_asset_id
        self._normalize_cta_variants(draft, campaign_brief, whatsapp_brief)
        return draft

    @staticmethod
    def _normalize_cta_variants(
        draft: WhatsAppDraft, campaign_brief: CampaignBrief, whatsapp_brief: WhatsAppBrief
    ) -> None:
        if not whatsapp_brief.cta_required:
            draft.cta_variants = None
            return
        options = [campaign_brief.cta_text] + (
            [whatsapp_brief.secondary_cta_text] if whatsapp_brief.secondary_cta_text else []
        )
        count = len(draft.message_variants)
        # An LLM can still return the wrong length (or skip cta_variants
        # entirely) despite the prompt, so rebuild it deterministically by
        # cycling through the CTA option(s) rather than trusting the model's
        # count to match message_variants.
        if not draft.cta_variants or len(draft.cta_variants) != count:
            draft.cta_variants = [options[i % len(options)] for i in range(count)]

    def _build_prompt(
        self,
        campaign_brief: CampaignBrief,
        whatsapp_brief: WhatsAppBrief,
        topic: Topic,
        candidate_assets: list[Asset],
    ) -> str:
        assets = [{"asset_id": a.asset_id, "tags": a.tags} for a in candidate_assets]
        if whatsapp_brief.cta_required:
            cta_options = [campaign_brief.cta_text] + (
                [whatsapp_brief.secondary_cta_text] if whatsapp_brief.secondary_cta_text else []
            )
            cta_line = (
                f"CTA OPTIONS (use verbatim, one per variant, cycling through these in order if there are more "
                f"variants than options -- never invent your own): {json.dumps(cta_options)}"
            )
        else:
            cta_line = "Do not include an explicit call to action; set cta_variants to null."
        if not whatsapp_brief.image_required:
            image_line = "Do not select an image; set image_asset_id to null."
        elif whatsapp_brief.selected_asset_id:
            image_line = (
                f"The user explicitly picked asset_id '{whatsapp_brief.selected_asset_id}' as the image for this "
                "message -- CANDIDATE ASSETS lists exactly this one asset. Set image_asset_id to exactly that "
                "value. Do not select or invent any other asset_id."
            )
        else:
            image_line = (
                "You MUST select exactly one image_asset_id from CANDIDATE ASSETS that best fits the message -- do not leave it null."
            )
        return (
            f"{campaign_context_block(campaign_brief)}"
            f"{cta_line}\n"
            f"{image_line}\n"
            f"LENGTH: {_LENGTH_GUIDANCE[whatsapp_brief.length]}\n\n"
            f"{FORMATTING_GUIDANCE}\n\n"
            f"TOPIC CONTENT: {json.dumps(topic_content_dict(topic))}\n\n"
            f"CANDIDATE ASSETS: {json.dumps(assets)}\n\n"
            f"{RESPONSE_SCHEMA_HINT}"
        )
