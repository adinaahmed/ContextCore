from app.core.embedding_providers.factory import get_embedding_provider


class EmbeddingService:
    def __init__(self, provider_name: str = None):
        self.provider = get_embedding_provider(provider_name)

    @property
    def dimension(self) -> int:
        return self.provider.dimension

    @property
    def provider_name(self) -> str:
        return self.provider.name

    def embed_text(self, text: str) -> list[float]:
        return self.provider.embed_text(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self.provider.embed_batch(texts)


embedding_service = EmbeddingService()
