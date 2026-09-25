from app.config import settings
from app.core.llm_providers.base import LLMProvider
from app.core.llm_providers.gemini_provider import GeminiProvider
from app.core.llm_providers.ollama_provider import OllamaProvider


def get_llm_provider(provider_name: str = None) -> LLMProvider:
    provider_name = (provider_name or settings.llm_provider).lower()

    if provider_name == "gemini":
        return GeminiProvider()
    elif provider_name == "ollama":
        return OllamaProvider()
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}")
