from sqlalchemy import Column, String, Integer, DateTime, LargeBinary, text
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
from app.db.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    document_id = Column(String, unique=True, nullable=False, index=True)
    owner_id = Column(String, nullable=False, index=True)
    source = Column(String, nullable=True)
    file_hash = Column(String, nullable=True)
    version = Column(Integer, default=1)
    collection_id = Column(String, nullable=True, index=True)
    parser_version = Column(String, default="v1")
    embedding_model = Column(String, nullable=True)
    chunking_strategy = Column(String, nullable=True)
    processing_status = Column(String, default="ready")
    original_filename = Column(String, nullable=True)
    original_content_type = Column(String, nullable=True)
    original_file_data = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
