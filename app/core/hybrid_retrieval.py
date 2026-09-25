from app.core.vector_store import vector_store
from app.core.bm25_store import bm25_store
from app.core.embeddings import embedding_service
from app.config import settings


class HybridRetriever:
    def __init__(self, dense_weight: float = 0.6, sparse_weight: float = 0.4):
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight

    def retrieve(self, query: str, top_k: int = 5, where: dict | None = None) -> list[dict]:
        query_embedding = embedding_service.embed_text(query)
        dense_results = vector_store.query(query_embedding, top_k=top_k * 2, where=where)

        dense_ids = dense_results["ids"][0] if dense_results["ids"] else []
        dense_texts = dense_results["documents"][0] if dense_results["documents"] else []
        dense_distances = dense_results["distances"][0] if dense_results["distances"] else []
        dense_scores = {cid: 1 / (1 + dist) for cid, dist in zip(dense_ids, dense_distances)}

        if where:
            # Scoped to specific document(s): BM25's in-memory index has no
            # per-chunk metadata filter, so scoped search relies on dense
            # (semantic) retrieval only. This is an honest simplification,
            # not a bug - full hybrid scoring only applies to unscoped search.
            ranked = sorted(dense_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
            id_to_text = dict(zip(dense_ids, dense_texts))
            final_ids = [cid for cid, _ in ranked]
            metadata_map = vector_store.get_metadata_by_ids(final_ids) if final_ids else {}
            return [
                {"chunk_id": cid, "text": id_to_text.get(cid, ""), "score": score, "metadata": metadata_map.get(cid, {}) or {}}
                for cid, score in ranked
            ]

        bm25_results = bm25_store.query(query, top_k=top_k * 2)
        bm25_scores_raw = {chunk_id: score for chunk_id, _, score in bm25_results}

        dense_scores_norm = self._normalize(dense_scores)
        bm25_scores_norm = self._normalize(bm25_scores_raw)

        all_ids = set(dense_scores_norm) | set(bm25_scores_norm)
        combined = {}
        id_to_text = dict(zip(dense_ids, dense_texts))
        for chunk_id, text, _ in bm25_results:
            id_to_text[chunk_id] = text

        for chunk_id in all_ids:
            d_score = dense_scores_norm.get(chunk_id, 0.0)
            s_score = bm25_scores_norm.get(chunk_id, 0.0)
            combined[chunk_id] = (self.dense_weight * d_score) + (self.sparse_weight * s_score)

        ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)[:top_k]
        final_ids = [cid for cid, _ in ranked]
        metadata_map = vector_store.get_metadata_by_ids(final_ids) if final_ids else {}

        return [
            {"chunk_id": cid, "text": id_to_text.get(cid, ""), "score": score, "metadata": metadata_map.get(cid, {}) or {}}
            for cid, score in ranked
        ]

    @staticmethod
    def _normalize(scores: dict) -> dict:
        if not scores:
            return {}
        values = list(scores.values())
        min_v, max_v = min(values), max(values)
        if max_v == min_v:
            return {k: 1.0 for k in scores}
        return {k: (v - min_v) / (max_v - min_v) for k, v in scores.items()}


# Weights come from config/.env (DENSE_WEIGHT, SPARSE_WEIGHT).
# getattr keeps the app starting with the defaults even if they aren't defined there.
hybrid_retriever = HybridRetriever(
    dense_weight=getattr(settings, "dense_weight", 0.6),
    sparse_weight=getattr(settings, "sparse_weight", 0.4),
)