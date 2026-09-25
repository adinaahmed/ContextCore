from rank_bm25 import BM25Okapi


class BM25Store:
    def __init__(self):
        self.corpus_texts: list[str] = []
        self.corpus_ids: list[str] = []
        self.bm25_index: BM25Okapi | None = None

    def add_chunks(self, ids: list[str], texts: list[str]):
        self.corpus_ids.extend(ids)
        self.corpus_texts.extend(texts)
        self._rebuild_index()

    def remove_by_document_id(self, document_id: str):
        prefix = f"{document_id}_chunk_"
        keep = [
            (cid, text) for cid, text in zip(self.corpus_ids, self.corpus_texts)
            if not cid.startswith(prefix)
        ]
        self.corpus_ids = [cid for cid, _ in keep]
        self.corpus_texts = [text for _, text in keep]
        self._rebuild_index()

    def remove_by_ids(self, ids: list[str]):
        id_set = set(ids)
        keep = [
            (cid, text) for cid, text in zip(self.corpus_ids, self.corpus_texts)
            if cid not in id_set
        ]
        self.corpus_ids = [cid for cid, _ in keep]
        self.corpus_texts = [text for _, text in keep]
        self._rebuild_index()

    def rebuild_from_source(self, ids: list[str], texts: list[str]):
        self.corpus_ids = list(ids)
        self.corpus_texts = list(texts)
        self._rebuild_index()

    def _rebuild_index(self):
        if not self.corpus_texts:
            self.bm25_index = None
            return
        tokenized_corpus = [self._tokenize(text) for text in self.corpus_texts]
        self.bm25_index = BM25Okapi(tokenized_corpus)

    def query(self, query_text: str, top_k: int = 5) -> list[tuple[str, str, float]]:
        if self.bm25_index is None or not self.corpus_texts:
            return []
        tokenized_query = self._tokenize(query_text)
        scores = self.bm25_index.get_scores(tokenized_query)
        scored = list(zip(self.corpus_ids, self.corpus_texts, scores))
        scored.sort(key=lambda x: x[2], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return text.lower().split()


bm25_store = BM25Store()
