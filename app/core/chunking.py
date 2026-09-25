import re
import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config import settings
from app.core.embeddings import embedding_service
from app.core.llm import llm_service


class ChunkingService:
    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap

        self.recursive_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def chunk_text(self, text: str, strategy: str = None) -> list[str]:
        strategy = strategy or settings.default_chunk_strategy

        if strategy == "recursive":
            return self._chunk_recursive(text)
        elif strategy == "semantic":
            return self._chunk_semantic(text)
        elif strategy == "contextual":
            return self._chunk_contextual(text)
        else:
            raise ValueError(f"Unknown chunking strategy: {strategy}")

    def _chunk_recursive(self, text: str) -> list[str]:
        return self.recursive_splitter.split_text(text)

    def _chunk_semantic(self, text: str, similarity_threshold: float = 0.25) -> list[str]:
        sentences = self._split_sentences(text)
        if len(sentences) <= 1:
            return sentences

        embeddings = embedding_service.embed_batch(sentences)
        chunks = []
        current_chunk = [sentences[0]]

        for i in range(1, len(sentences)):
            similarity = self._cosine_similarity(embeddings[i - 1], embeddings[i])
            if similarity >= similarity_threshold:
                current_chunk.append(sentences[i])
            else:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sentences[i]]

        chunks.append(" ".join(current_chunk))
        return chunks

    def _chunk_contextual(self, text: str) -> list[str]:
        """
        Splits using the recursive strategy first (for consistent sizing),
        then asks the LLM to prepend a short contextual summary to each chunk.
        """
        base_chunks = self._chunk_recursive(text)
        enriched_chunks = []

        for chunk in base_chunks:
            try:
                context_note = self._generate_context_note(full_document=text, chunk=chunk)
                enriched_chunks.append(f"{context_note}\n\n{chunk}")
            except Exception:
                # If the LLM fails for one chunk, fall back to the raw chunk
                # rather than losing that piece of the document entirely
                enriched_chunks.append(chunk)

        return enriched_chunks

    def _generate_context_note(self, full_document: str, chunk: str) -> str:
        prompt = f"""You will be given a full document and one small excerpt (chunk) from it.
Write ONE short sentence (max 20 words) describing what this chunk is about and where it fits in the document.
Do not repeat the chunk's content verbatim. Be concise.

FULL DOCUMENT:
{full_document[:2000]}

CHUNK:
{chunk}

CONTEXT SENTENCE:"""

        # raw_generate uses the shared LLM service: Gemini, with automatic
        # fallback to Ollama if Gemini is unavailable
        note = (llm_service.raw_generate(prompt) or "").strip()
        if not note:
            # Raising lets _chunk_contextual fall back to storing the plain chunk
            raise ValueError("Empty context note")
        return note

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s.strip() for s in sentences if s.strip()]

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        a, b = np.array(vec_a), np.array(vec_b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


chunking_service = ChunkingService()