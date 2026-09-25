from app.config import settings
from app.core.embedding_providers.base import EmbeddingProvider
from app.core.embedding_providers.local_provider import LocalEmbeddingProvider


def get_embedding_provider(provider_name: str = None) -> EmbeddingProvider:
    provider_name = (provider_name or settings.embedding_provider).lower()

    if provider_name == "local":
        return LocalEmbeddingProvider()
    else:
        raise ValueError(f"Unknown embedding provider: {provider_name}")
