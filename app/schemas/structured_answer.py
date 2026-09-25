from pydantic import BaseModel, Field


class StructuredAnswer(BaseModel):
    answer: str = Field(..., description="The generated answer to the question")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model's confidence in the answer, 0 to 1")
    sources: list[str] = Field(default_factory=list, description="Source chunks used to generate the answer")
    used_retrieval: bool = Field(..., description="Whether retrieved context was used to answer")