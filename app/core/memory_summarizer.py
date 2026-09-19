from app.core.llm import llm_service


def summarize_turns(turns: list[dict]) -> str:
    """
    Condenses a list of conversation turns into a short summary paragraph.
    Falls back to a simple concatenated list if Gemini fails.
    """
    if not turns:
        return ""

    conversation_text = "\n".join(
        f"User: {t['question']}\nAssistant: {t['answer']}" for t in turns
    )

    prompt = f"""Summarize the following conversation history into 2-3 concise sentences,
capturing the key topics and facts discussed, so this summary can be used as
background context for continuing the conversation.

CONVERSATION:
{conversation_text}

SUMMARY:"""

    try:
        response = llm_service.client.models.generate_content(
            model=llm_service.model_name,
            contents=prompt,
        )
        return llm_service.raw_generate(prompt).strip() or _fallback_summary(turns)
    except Exception:
        return _fallback_summary(turns)


def _fallback_summary(turns: list[dict]) -> str:
    """Simple non-LLM fallback: just list the questions that were asked."""
    questions = [t["question"] for t in turns]
    return f"Earlier in this conversation, the user asked about: {'; '.join(questions)}."