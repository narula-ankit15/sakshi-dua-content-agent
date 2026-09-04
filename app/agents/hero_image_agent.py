from app.agents.llm_client import ImageGenClient
from app.models import CampaignBrief, Topic

_STYLE = (
    "minimalist modern flat-vector illustration style, clean simple shapes, generous white negative space, "
    "warm professional color palette of indigo blue and amber orange, the scene filling most of the frame in a "
    "balanced centered composition (not tiny and lost in empty space), small tasteful abstract circle accents "
    "tucked in a corner or two, wide banner composition, absolutely no text, no words, no letters, no numbers, "
    "no logos, no watermarks"
)


class HeroImageAgent:
    """Generates a polished, on-brand hero banner illustration for an email
    via Gemini's image model. Real workshop photos are candid phone shots --
    fine as small supporting proof-of-work thumbnails, but not polished
    enough to be the email's large lead visual -- so this produces a
    professional illustrative hero instead, freeing the actual photos for a
    small gallery further down the email.
    """

    def __init__(self, image_client: ImageGenClient):
        self._image_client = image_client

    def generate(self, *, topic: Topic, campaign_brief: CampaignBrief) -> bytes:
        prompt = self._build_prompt(topic, campaign_brief)
        return self._image_client.generate_image(prompt)

    @staticmethod
    def _build_prompt(topic: Topic, campaign_brief: CampaignBrief) -> str:
        theme = topic.tagline or topic.topic_name
        return (
            f"An email hero banner illustration for a corporate training workshop called "
            f"'{topic.topic_name}'. Depict a small, diverse group of professionals in an active workshop "
            f"moment together -- discussing, gesturing, engaged with each other -- conveying the theme of "
            f"{theme.lower()}. Style: {_STYLE}."
        )
