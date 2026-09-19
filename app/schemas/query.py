from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    session_id: str | None = Field(default=None)
    use_multi_query: bool = Field(default=False)
    use_context_compression: bool = Field(default=False)
    document_ids: list[str] | None = Field(default=None, description="Optional: scope search to one or more documents")


class Citation(BaseModel):
    document_id: str | None = None
    source: str | None = None
    page_number: int | None = None
    chunk_index: int | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    citations: list[Citation] = []
    session_id: str | None = None
    classification: str | None = None
