from app.core.llm import llm_service


class QueryRewriter:
    def rewrite(self, question: str, history: list[dict]) -> str:
        """
        Rewrites a potentially context-dependent question into a standalone one,
        using recent conversation history. Falls back to the original question
        if history is empty or rewriting fails.
        """
        if not history:
            return question

        # Use the last few turns for context — enough to resolve references,
        # without sending the entire conversation history on every call
        recent_history = history[-3:]
        history_text = "\n".join(
            f"User: {turn['question']}\nAssistant: {turn['answer']}"
            for turn in recent_history
        )

        prompt = f"""Given the conversation history below, rewrite the user's latest question
into a standalone question that makes sense without needing the prior conversation.
If the question is already standalone, return it unchanged.
Only output the rewritten question, nothing else.

CONVERSATION HISTORY:
{history_text}

LATEST QUESTION:
{question}

STANDALONE QUESTION:"""

        try:
            response = llm_service.client.models.generate_content(
                model=llm_service.model_name,
                contents=prompt,
            )
            rewritten = response.text.strip()
            return rewritten if rewritten else question
        except Exception:
            # If rewriting fails for any reason, fall back to the original question
            # rather than blocking the whole query pipeline
            return question


query_rewriter = QueryRewriter()