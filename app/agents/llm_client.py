import json
from typing import Protocol


class LLMClient(Protocol):
    """Agents depend on this, not on google-genai directly — swapping the
    LLM provider later (per the doc's "swap the LLM provider" assumption)
    means writing one new class, not touching any agent's prompt logic.
    """

    def generate_json(self, *, system: str, prompt: str) -> dict:
        ...


class GeminiClient:
    def __init__(self, api_key: str, model: str):
        # imported lazily so unit tests that use a fake client don't need
        # the google-genai package installed at all
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate_json(self, *, system: str, prompt: str) -> dict:
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config={
                "system_instruction": system,
                "response_mime_type": "application/json",
            },
        )
        return json.loads(response.text)


class ImageGenClient(Protocol):
    """Separate from LLMClient (not just another method on it) so fakes/tests
    for the many text-generation agents never have to stub out image
    generation too -- only agents that actually need a hero image depend on
    this narrower protocol.
    """

    def generate_image(self, prompt: str) -> bytes:
        ...


class GeminiImageClient:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-image"):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate_image(self, prompt: str) -> bytes:
        from google.genai import types

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            # 16:9 so the result already fits an email's wide hero-banner
            # slot without needing to crop a square/portrait result.
            config=types.GenerateContentConfig(image_config=types.ImageConfig(aspect_ratio="16:9")),
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                return part.inline_data.data
        raise RuntimeError("Gemini did not return image data for the hero image prompt")
