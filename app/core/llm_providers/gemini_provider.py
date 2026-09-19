from google import genai
from app.core.llm_providers.base import LLMProvider
from app.config import settings


class GeminiProvider(LLMProvider):
    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.gemini_model
        self.client = genai.Client(
            api_key=settings.google_api_key,
            http_options={"timeout": 15000},
        )

    def generate(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
        )
        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")
        return response.text.strip()

    def is_available(self) -> bool:
        # Config presence only — avoids burning real API quota on a health check
        return bool(settings.google_api_key)

    @property
    def name(self) -> str:
        return f"gemini:{self.model_name}"
