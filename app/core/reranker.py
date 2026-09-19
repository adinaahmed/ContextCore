from sentence_transformers import CrossEncoder


class RerankerService:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """
        candidates: list of dicts, each must have a 'text' key (from hybrid_retriever output)
        Returns the same dicts, re-sorted by cross-encoder relevance, trimmed to top_k.
        """
        if not candidates:
            return []

        # Build (query, chunk_text) pairs — this is the "joint" input the cross-encoder needs
        pairs = [(query, c["text"]) for c in candidates]

        # Get one relevance score per pair
        scores = self.model.predict(pairs)

        # Attach the new score to each candidate, then sort
        for candidate, score in zip(candidates, scores):
            candidate["rerank_score"] = float(score)

        reranked = sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)
        return reranked[:top_k]


reranker_service = RerankerService()