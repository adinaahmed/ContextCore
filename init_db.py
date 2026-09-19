from app.db.database import engine, Base
from app.models.user import User  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.conversation import ConversationSession, ConversationMessage  # noqa: F401
from app.models.evaluation import EvaluationRun  # noqa: F401

Base.metadata.create_all(bind=engine)
print("Tables created successfully.")
