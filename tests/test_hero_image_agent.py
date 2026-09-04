from app.agents.hero_image_agent import HeroImageAgent
from app.models import AudienceTone, CampaignBrief, Purpose


class FakeImageGenClient:
    def __init__(self, response: bytes = b"fake-png-bytes"):
        self._response = response
        self.last_prompt = None

    def generate_image(self, prompt: str) -> bytes:
        self.last_prompt = prompt
        return self._response


def _campaign_brief() -> CampaignBrief:
    return CampaignBrief(
        purpose=Purpose.PROMO_SALE,
        key_message="drive signups",
        cta_text="Reserve a seat",
        audience_tone=AudienceTone.CONSUMERS_PREMIUM,
    )


def test_generate_returns_image_bytes_from_client(sample_topic):
    fake_client = FakeImageGenClient(b"some-png-bytes")
    agent = HeroImageAgent(fake_client)

    result = agent.generate(topic=sample_topic, campaign_brief=_campaign_brief())

    assert result == b"some-png-bytes"


def test_generate_grounds_prompt_in_topic_name_and_tagline(sample_topic):
    fake_client = FakeImageGenClient()
    agent = HeroImageAgent(fake_client)

    agent.generate(topic=sample_topic, campaign_brief=_campaign_brief())

    assert sample_topic.topic_name in fake_client.last_prompt
    assert sample_topic.tagline.lower() in fake_client.last_prompt.lower()


def test_generate_prompt_explicitly_forbids_text_in_the_image(sample_topic):
    fake_client = FakeImageGenClient()
    agent = HeroImageAgent(fake_client)

    agent.generate(topic=sample_topic, campaign_brief=_campaign_brief())

    assert "no text" in fake_client.last_prompt.lower()
