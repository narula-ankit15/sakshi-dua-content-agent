from app.agents.llm_client import LLMClient
from app.models import CampaignBrief

_SYSTEM = (
    "You write short overlay text for promotional workshop/training images (the kind of 2-6 word "
    "line stamped across a banner creative, not body copy). Punchy, concrete, no fluff."
)


class ImageOverlayTextAgent:
    """Text-only suggestion agent for the image editor's "Suggest text with
    AI" action. Deliberately separate from EmailContentAgent/WhatsAppContentAgent
    -- it doesn't touch imagery, compliance, or the content library, just
    proposes short strings for a human to place (or not) on a canvas.
    """

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def suggest(self, campaign_brief: CampaignBrief) -> list[str]:
        prompt = (
            f"Campaign purpose: {campaign_brief.purpose.value}\n"
            f"Key message: {campaign_brief.key_message}\n"
            f"Audience tone: {campaign_brief.audience_tone.value}\n\n"
            "Suggest 4 short overlay text options (max 6 words each) that could be stamped "
            "across a promotional image for this campaign. Return JSON: "
            '{"suggestions": ["...", "...", "...", "..."]}'
        )
        result = self._llm.generate_json(system=_SYSTEM, prompt=prompt)
        return result["suggestions"]
