from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.config import settings

router_llm = ChatGoogleGenerativeAI(
    model=settings.gemini_model,
    google_api_key=settings.google_api_key,
    temperature=0,
)

router_prompt = ChatPromptTemplate.from_template(
    """Classify the user's question into exactly one category: "direct" or "retrieval".

Default to "retrieval" unless the question is CLEARLY one of these:
- A greeting (e.g. "hello", "hi", "how are you")
- Small talk or pleasantries (e.g. "thank you", "goodbye", "nice to meet you")
- A question about the assistant itself (e.g. "what can you do", "who are you")

Use "retrieval" for ANYTHING else, including:
- Any factual question, definition, or "what is X" question
- Any question that could plausibly be answered by looking up documents
- Any technical, project-specific, or specific-detail question
- Any follow-up question in an ongoing conversation

When in doubt, choose "retrieval" — it is always safer to check documents than to skip them.

Respond with ONLY one word, either "direct" or "retrieval". No punctuation, no explanation.

Question: {question}
Classification:"""
)

router_chain = router_prompt | router_llm | StrOutputParser()


def classify_question(question: str) -> str:
    try:
        result = router_chain.invoke({"question": question}).strip().lower()
        return "direct" if "direct" in result else "retrieval"
    except Exception:
        return "retrieval"