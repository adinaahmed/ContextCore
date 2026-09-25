from pydantic import BaseModel, Field
from typing import Literal


class IngestRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw document text to ingest")
    document_id: str = Field(..., description="Unique identifier for this document")
    source: str = Field(default="unknown", description="Where this document came from")
    strategy: Literal["recursive", "semantic", "contextual"] = Field(
        default="recursive", description="Chunking strategy to use"
    )
    collection_id: str | None = Field(default=None, description="Optional subject/collection grouping")


class IngestResponse(BaseModel):
    document_id: str
    chunks_created: int
    strategy_used: str
    status: str
    action: str
    version: int
    collection_id: str | None = None
    chunks_reused: int = 0
    chunks_reprocessed: int = 0
