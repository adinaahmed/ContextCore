from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from app.config import settings


class GeneratedAnswer(BaseModel):
    answer: str = Field(description="The generated answer to the question")
    confidence: float = Field(description="Confidence in the answer, from 0.0 to 1.0")
    used_retrieval: bool = Field(description="Whether the answer used retrieved document context")


llm = ChatGoogleGenerativeAI(
    model=settings.gemini_model,
    google_api_key=settings.google_api_key,
    timeout=15,
)

parser = JsonOutputParser(pydantic_object=GeneratedAnswer)

FEW_SHOT_EXAMPLES = """Example 1:
Context: "Paris is the capital of France."
Question: "What is the capital of France?"
Output: {{"answer": "Paris is the capital of France.", "confidence": 1.0, "used_retrieval": true}}

Example 2:
Context: "The sky is blue on a clear day."
Question: "What is the population of Tokyo?"
Output: {{"answer": "I don't have enough information to answer that.", "confidence": 0.1, "used_retrieval": true}}

Example 3:
Context: "(No context retrieved — answer using general knowledge if possible.)"
Question: "Hello, how are you?"
Output: {{"answer": "I'm doing well, thank you! How can I help you today?", "confidence": 0.9, "used_retrieval": false}}
"""

structured_prompt = ChatPromptTemplate.from_template(
    """You are a grounded RAG assistant. Use the CONTEXT to answer the QUESTION.
If the context says no context was retrieved, answer using your own general knowledge
if it's a simple/general question, and set used_retrieval to false.
If context is provided but doesn't answer the question, say you don't have enough
information and set confidence low.
Do not invent facts.

{format_instructions}

Examples of correct behavior:
{examples}

CONTEXT:
{context}

QUESTION:
{question}
"""
)

# This is the actual LCEL chain: prompt -> llm -> parser, composed declaratively
structured_chain = structured_prompt | llm | parser


def run_structured_chain(question: str, context: str) -> dict:
    return structured_chain.invoke({
        "question": question,
        "context": context,
        "examples": FEW_SHOT_EXAMPLES,
        "format_instructions": parser.get_format_instructions(),
    })