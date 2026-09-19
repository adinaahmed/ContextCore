import chromadb
from app.core.vector_stores.base import VectorStore
from app.core.bm25_store import bm25_store


class ChromaVectorStore(VectorStore):
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, ids: list[str], texts: list[str], embeddings: list[list[float]], metadatas: list[dict]):
        if not ids:
            return
        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        bm25_store.add_chunks(ids=ids, texts=texts)

    def query(self, query_embedding: list[float], top_k: int = 5, where: dict | None = None):
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

    def get_all_chunks(self) -> dict:
        return self.collection.get(include=["documents"])

    def get_chunks_by_document_id(self, document_id: str) -> dict:
        return self.collection.get(where={"document_id": document_id}, include=["metadatas"])

    def get_metadata_by_ids(self, ids: list[str]) -> dict:
        if not ids:
            return {}
        result = self.collection.get(ids=ids, include=["metadatas"])
        result_ids = result.get("ids", [])
        result_metadatas = result.get("metadatas", [])
        return dict(zip(result_ids, result_metadatas))

    def delete_by_document_id(self, document_id: str):
        self.collection.delete(where={"document_id": document_id})

    def delete_by_chunk_ids(self, ids: list[str]):
        if ids:
            self.collection.delete(ids=ids)

    def count(self) -> int:
        return self.collection.count()

    @property
    def name(self) -> str:
        return "chroma"
