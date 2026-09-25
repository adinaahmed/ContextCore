from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.config import settings
from app.core.hybrid_retrieval import hybrid_retriever

variant_llm = ChatGoogleGenerativeAI(
    model=settings.gemini_model,
    google_api_key=settings.google_api_key,
    temperature=0.7,  # some creativity helps generate genuinely different phrasings
    timeout=15,
)

variant_prompt = ChatPromptTemplate.from_template(
    """Generate 2 alternative phrasings of the following question.
Each variant should ask the same thing in different words, to help a search
system find relevant documents that might use different terminology.

Respond with ONLY the 2 variants, one per line, no numbering, no explanation.

Original question: {question}"""
)

variant_chain = variant_prompt | variant_llm | StrOutputParser()


def generate_query_variants(question: str) -> list[str]:
    """Returns [original_question, variant_1, variant_2]. Falls back to just the original on failure."""
    try:
        result = variant_chain.invoke({"question": question})
        variants = [line.strip() for line in result.strip().split("\n") if line.strip()]
        return [question] + variants[:2]  # cap at 2 variants, plus the original = max 3 queries
    except Exception:
        return [question]


def multi_query_retrieve(question: str, top_k: int = 5) -> list[dict]:
    """
    Runs hybrid retrieval across the original question and its variants,
    merges results, and deduplicates by chunk_id, keeping the best score per chunk.
    """
    queries = generate_query_variants(question)

    merged: dict[str, dict] = {}

    for q in queries:
        results = hybrid_retriever.retrieve(q, top_k=top_k)
        for r in results:
            chunk_id = r["chunk_id"]
            if chunk_id not in merged or r["score"] > merged[chunk_id]["score"]:
                merged[chunk_id] = r

    ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:top_k * 2]  # overfetch slightly for the reranker to work with, same pattern as before