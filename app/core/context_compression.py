import re
import numpy as np
from app.core.embeddings import embedding_service


class ContextCompressor:
    def __init__(self, similarity_threshold: float = 0.3, min_sentences_kept: int = 1):
        self.similarity_threshold = similarity_threshold
        self.min_sentences_kept = min_sentences_kept

    def compress(self, question: str, chunks: list[str]) -> list[str]:
        """
        For each chunk, keeps only the sentences relevant to the question.
        Falls back to keeping the whole chunk if compression would remove everything.
        """
        if not chunks:
            return []

        question_embedding = embedding_service.embed_text(question)
        compressed_chunks = []

        for chunk in chunks:
            sentences = self._split_sentences(chunk)

            if len(sentences) <= 1:
                # Nothing meaningful to compress — keep as-is
                compressed_chunks.append(chunk)
                continue

            sentence_embeddings = embedding_service.embed_batch(sentences)

            scored_sentences = []
            for sentence, embedding in zip(sentences, sentence_embeddings):
                similarity = self._cosine_similarity(question_embedding, embedding)
                scored_sentences.append((sentence, similarity))

            # Keep sentences above threshold
            relevant = [s for s, score in scored_sentences if score >= self.similarity_threshold]

            # Safety net: never fully empty a chunk — keep at least the top N sentences
            if len(relevant) < self.min_sentences_kept:
                scored_sentences.sort(key=lambda x: x[1], reverse=True)
                relevant = [s for s, _ in scored_sentences[:self.min_sentences_kept]]

            compressed_chunks.append(" ".join(relevant))

        return compressed_chunks

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s.strip() for s in sentences if s.strip()]

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        a, b = np.array(vec_a), np.array(vec_b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


context_compressor = ContextCompressor()