from abc import ABC, abstractmethod


class VectorStore(ABC):
    @abstractmethod
    def add_chunks(self, ids: list[str], texts: list[str], embeddings: list[list[float]], metadatas: list[dict]):
        ...

    @abstractmethod
    def query(self, query_embedding: list[float], top_k: int = 5, where: dict | None = None):
        ...

    @abstractmethod
    def get_all_chunks(self) -> dict:
        ...

    @abstractmethod
    def get_chunks_by_document_id(self, document_id: str) -> dict:
        ...

    @abstractmethod
    def get_metadata_by_ids(self, ids: list[str]) -> dict:
        ...

    @abstractmethod
    def delete_by_document_id(self, document_id: str):
        ...

    @abstractmethod
    def delete_by_chunk_ids(self, ids: list[str]):
        ...

    @abstractmethod
    def count(self) -> int:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
