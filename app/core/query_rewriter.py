from app.core.llm import llm_service
from app.config import settings


class QueryRewriter:
    def rewrite(self, question: str, history: list[dict]) -> str:
        """
        Rewrites the user's question before retrieval in a single LLM call:
        - resolves references to earlier turns ("it", "that", "the second one")
        - fixes spelling mistakes and unclear wording
        - expands abbreviations and adds key terms that improve search
        Falls back to the original question if rewriting is disabled or fails.
        """
        expand = getattr(settings, "query_rewrite_expand", True)
        if not history and not expand:
            return question

        recent_history = (history or [])[-3:]
        if recent_history:
            history_text = "\n".join(
                f"User: {turn['question']}\nAssistant: {turn['answer']}"
                for turn in recent_history
            )
        else:
            history_text = "(no previous conversation)"

        prompt = f"""You improve search queries for a document question-answering system.

Rewrite the user's latest question so it works well for searching documents:
1. If it refers to earlier conversation (e.g. "it", "that", "the second one"), make it standalone using the history.
2. Fix spelling mistakes and unclear wording.
3. Expand abbreviations and add closely related key terms if they would help find the right passage.
4. Keep the original meaning. Do not add facts, assumptions or answers.
5. Keep it to one or two sentences.

Only output the rewritten question, nothing else.

CONVERSATION HISTORY:
{history_text}

LATEST QUESTION:
{question}

REWRITTEN QUESTION:"""

        try:
            # raw_generate goes through the shared LLM service, so it uses
            # Gemini with automatic fallback to Ollama if Gemini is unavailable
            rewritten = (llm_service.raw_generate(prompt) or "").strip().strip('"').strip()
            # Guard against empty or runaway output
            if not rewritten or len(rewritten) > max(300, len(question) * 4):
                return question
            return rewritten
        except Exception:
            # If rewriting fails for any reason, fall back to the original question
            # rather than blocking the whole query pipeline
            return question


query_rewriter = QueryRewriter()