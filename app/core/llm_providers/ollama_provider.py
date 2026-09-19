import requests
from app.core.llm_providers.base import LLMProvider
from app.config import settings


class OllamaProvider(LLMProvider):
    def __init__(self, model_name: str = None, base_url: str = None):
        self.model_name = model_name or settings.ollama_model
        self.base_url = base_url or settings.ollama_base_url

    def generate(self, prompt: str) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model_name, "prompt": prompt, "stream": False},
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            text = data.get("response", "").strip()
            if not text:
                raise RuntimeError("Ollama returned an empty response.")
            return text
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama request failed: {e}") from e

    def is_available(self) -> bool:
        # Cheap, local, no cost — safe to actually ping
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    @property
    def name(self) -> str:
        return f"ollama:{self.model_name}"
