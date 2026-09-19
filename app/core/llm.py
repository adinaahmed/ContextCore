import json
import logging
from app.core.llm_providers.factory import get_llm_provider
from app.config import settings

logger = logging.getLogger("rag_backend")


class LLMService:
    def __init__(self, provider_name: str = None, fallback_provider_name: str = None):
        self.provider = get_llm_provider(provider_name)

        fallback_name = fallback_provider_name or settings.llm_fallback_provider
        self.fallback_provider = None
        if fallback_name and fallback_name.lower() != self.provider.name.split(":")[0]:
            try:
                self.fallback_provider = get_llm_provider(fallback_name)
            except Exception:
                self.fallback_provider = None

        self.last_provider_used = self.provider.name

    @property
    def provider_name(self) -> str:
        return self.provider.name

    def _generate_with_failover(self, prompt: str) -> str:
        try:
            result = self.provider.generate(prompt)
            self.last_provider_used = self.provider.name
            return result
        except Exception as primary_error:
            if self.fallback_provider is None:
                raise
            logger.warning(
                f"Primary provider '{self.provider.name}' failed ({primary_error}). "
                f"Falling back to '{self.fallback_provider.name}'."
            )
            try:
                result = self.fallback_provider.generate(prompt)
                self.last_provider_used = self.fallback_provider.name
                return result
            except Exception as fallback_error:
                self.last_provider_used = self.provider.name
                raise RuntimeError(
                    f"Both providers failed. Primary ({self.provider.name}): {primary_error}. "
                    f"Fallback ({self.fallback_provider.name}): {fallback_error}"
                ) from fallback_error

    def raw_generate(self, prompt: str) -> str:
        return self._generate_with_failover(prompt)

    def generate_answer(self, question: str, context_chunks: list[str]) -> str:
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")
        if not context_chunks:
            raise ValueError("Context chunks cannot be empty")

        numbered_context = "\n\n".join(
            f"Source {i+1}: {chunk}" for i, chunk in enumerate(context_chunks)
        )

        prompt = f"""You are a grounded RAG assistant.

Below are numbered sources. Internally identify which source(s) DIRECTLY and
SPECIFICALLY answer the question. Ignore sources that merely share a word
with the question but do not actually address it.

Base your answer ONLY on the source(s) that genuinely answer the question.
If none of the sources answer it, say there is not enough information.
Do not invent facts.

FORMATTING RULES (very important):
- Do NOT mention "Source 1", "Source 2", or any reference to source numbers.
- Do NOT use LaTeX syntax of any kind: no dollar signs, no backslash commands
  like \\sigma, \\bar{{X}}, \\pm, \\frac{{}}{{}}, \\cdot, \\sqrt{{}}. This text is
  displayed in a plain chat window with no math renderer, so LaTeX shows up
  as broken, unreadable code to the user.
- Instead, write all mathematical notation in plain, readable text using
  real Unicode symbols directly: σ (sigma), μ (mu), α (alpha), x̄ or "sample
  mean", ± (plus-minus), × (times), √ (square root), ≤ (less than or equal).
- Write formulas as plain arithmetic, e.g.: "362.3 ± 1.96 × (15 / √25)"
  instead of LaTeX fraction/sqrt commands.
- Write your final answer as clean, natural prose and worked steps that a
  student can read directly with no special rendering needed.

{numbered_context}

QUESTION:
{question}

ANSWER (plain text, no LaTeX, no source references):"""

        return self._generate_with_failover(prompt)

    def generate_direct_answer(self, question: str) -> str:
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")

        prompt = f"""Answer the following question directly and concisely, as a helpful assistant.
This question does not require looking up any documents. Do not use LaTeX
syntax; write any math in plain text with real Unicode symbols (σ, μ, α, ±, ×, √).

QUESTION:
{question}

ANSWER:"""
        return self._generate_with_failover(prompt)

    def generate_structured_answer(self, question: str, context_chunks: list[str]) -> dict:
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")

        context = "\n\n".join(context_chunks) if context_chunks else ""
        used_retrieval = bool(context_chunks)

        prompt = f"""You are a grounded RAG assistant. Answer the question using ONLY the provided context.

Respond with ONLY a valid JSON object in exactly this format, nothing else, no markdown fences:
{{
  "answer": "your answer here",
  "confidence": 0.0 to 1.0,
  "used_retrieval": {str(used_retrieval).lower()}
}}

Rules:
- If the context does not contain enough information, set answer to "I don't have enough information to answer that." and confidence to a low value like 0.1.
- confidence should reflect how directly the context supports your answer.
- Do NOT mention "Source 1" or source numbers inside the "answer" field.
- Do NOT use LaTeX syntax inside the "answer" field; use plain text with real Unicode symbols (σ, μ, α, ±, ×, √) instead.
- Output ONLY the JSON object, no other text.

CONTEXT:
{context}

QUESTION:
{question}

JSON RESPONSE:"""

        raw_text = self._generate_with_failover(prompt)
        try:
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`").replace("json", "", 1).strip()
            parsed = json.loads(raw_text)
            parsed["sources"] = context_chunks
            return parsed
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Returned invalid JSON: {e}") from e


llm_service = LLMService()
