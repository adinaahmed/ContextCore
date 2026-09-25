from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime, timezone
from app.db.database import Base


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    embedding_model = Column(String, nullable=True)
    k_value = Column(Integer, nullable=False)
    num_questions = Column(Integer, nullable=False)
    recall_at_k = Column(Float, nullable=False)
    mrr = Column(Float, nullable=False)
    avg_latency_ms = Column(Float, nullable=True)
