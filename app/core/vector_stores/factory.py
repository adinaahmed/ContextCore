from app.config import settings
from app.core.vector_stores.base import VectorStore
from app.core.vector_stores.chroma_store import ChromaVectorStore


def get_vector_store(provider_name: str = None) -> VectorStore:
    provider_name = (provider_name or settings.vector_store_provider).lower()

    if provider_name == "chroma":
        return ChromaVectorStore(persist_directory=settings.chroma_persist_directory)
    else:
        raise ValueError(f"Unknown vector store provider: {provider_name}")
