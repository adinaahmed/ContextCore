from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.config import settings

router_llm = ChatGoogleGenerativeAI(
    model=settings.gemini_model,
    google_api_key=settings.google_api_key,
    temperature=0,
    timeout=15,
)

router_prompt = ChatPromptTemplate.from_template(
    """Classify the user's question into EXACTLY ONE of these categories:

"direct" — a greeting, small talk, or a question about the assistant itself
  (e.g. "hello", "thank you", "what can you do")

"calculation" — the question requires arithmetic/math computation
  (e.g. "what is 45 times 12", "calculate the average of...")

"complex" — the question has MULTIPLE parts, asks for a COMPARISON, or is
  vague/broad enough that it likely needs several search attempts to answer well
  (e.g. "compare X and Y", "explain both A and B", "what are the differences between...")

"simple" — a single, clear factual question that doesn't fit any category above
  (e.g. "what is RAG", "what score did Bob get")

When uncertain between "simple" and "complex", choose "simple" — it is cheaper
and usually sufficient.

Respond with ONLY one word: direct, calculation, complex, or simple. No punctuation, no explanation.

Question: {question}
Classification:"""
)

router_chain = router_prompt | router_llm | StrOutputParser()

VALID_CATEGORIES = {"direct", "calculation", "complex", "simple"}


def classify_question(question: str) -> str:
    try:
        result = router_chain.invoke({"question": question}).strip().lower()
        for category in VALID_CATEGORIES:
            if category in result:
                return category
        return "simple"
    except Exception:
        return "simple"
