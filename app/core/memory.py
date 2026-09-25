from sqlalchemy.orm import Session
from sqlalchemy import asc, desc
from app.models.conversation import ConversationSession, ConversationMessage
from app.core.memory_summarizer import summarize_turns

SUMMARIZE_AFTER = 10
KEEP_RAW = 5


class ConversationMemory:
    def add_turn(self, db: Session, session_id: str, question: str, answer: str, owner_id: str = None):
        session = db.query(ConversationSession).filter(ConversationSession.session_id == session_id).first()
        if session is None:
            session = ConversationSession(session_id=session_id, owner_id=owner_id)
            db.add(session)
            db.flush()

        message = ConversationMessage(session_id=session_id, question=question, answer=answer)
        db.add(message)
        db.flush()

        messages = (
            db.query(ConversationMessage)
            .filter(ConversationMessage.session_id == session_id)
            .order_by(asc(ConversationMessage.id))
            .all()
        )

        if len(messages) > SUMMARIZE_AFTER:
            to_summarize = messages[:-KEEP_RAW]
            if to_summarize:
                turns_for_summary = [{"question": m.question, "answer": m.answer} for m in to_summarize]
                new_piece = summarize_turns(turns_for_summary)
                session.summary = f"{session.summary} {new_piece}".strip() if session.summary else new_piece
                for m in to_summarize:
                    db.delete(m)

        db.commit()

    def get_history(self, db: Session, session_id: str) -> list[dict]:
        messages = (
            db.query(ConversationMessage)
            .filter(ConversationMessage.session_id == session_id)
            .order_by(asc(ConversationMessage.id))
            .all()
        )
        return [
            {"question": m.question, "answer": m.answer, "timestamp": m.created_at.isoformat() if m.created_at else None}
            for m in messages
        ]

    def get_summary(self, db: Session, session_id: str) -> str | None:
        session = db.query(ConversationSession).filter(ConversationSession.session_id == session_id).first()
        return session.summary if session else None

    def get_owner(self, db: Session, session_id: str) -> str | None:
        session = db.query(ConversationSession).filter(ConversationSession.session_id == session_id).first()
        return session.owner_id if session else None

    def list_sessions(self, db: Session, owner_id: str) -> list[dict]:
        sessions = (
            db.query(ConversationSession)
            .filter(ConversationSession.owner_id == owner_id)
            .order_by(desc(ConversationSession.created_at))
            .all()
        )
        result = []
        for s in sessions:
            last_msg = (
                db.query(ConversationMessage)
                .filter(ConversationMessage.session_id == s.session_id)
                .order_by(desc(ConversationMessage.id))
                .first()
            )
            msg_count = (
                db.query(ConversationMessage)
                .filter(ConversationMessage.session_id == s.session_id)
                .count()
            )
            result.append({
                "session_id": s.session_id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "message_count": msg_count,
                "last_question": last_msg.question if last_msg else None,
                "has_summary": bool(s.summary),
            })
        return result

    def clear_session(self, db: Session, session_id: str):
        session = db.query(ConversationSession).filter(ConversationSession.session_id == session_id).first()
        if session:
            db.delete(session)
            db.commit()


conversation_memory = ConversationMemory()
