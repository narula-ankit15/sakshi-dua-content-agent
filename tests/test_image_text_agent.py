from app.agents.image_text_agent import ImageOverlayTextAgent


class FakeLLMClient:
    def __init__(self, response: dict):
        self._response = response
        self.last_system = None
        self.last_prompt = None

    def generate_json(self, *, system: str, prompt: str) -> dict:
        self.last_system = system
        self.last_prompt = prompt
        return self._response


def test_suggest_returns_llm_suggestions(sample_campaign_brief):
    fake_llm = FakeLLMClient({"suggestions": ["Reserve Your Seat", "Limited Seats Left", "Join This Weekend", "Level Up Your Team"]})
    agent = ImageOverlayTextAgent(fake_llm)

    suggestions = agent.suggest(sample_campaign_brief)

    assert suggestions == ["Reserve Your Seat", "Limited Seats Left", "Join This Weekend", "Level Up Your Team"]
    assert "drive signups for the Communicate with Impact workshop" in fake_llm.last_prompt
    assert "overlay text" in fake_llm.last_prompt.lower()
