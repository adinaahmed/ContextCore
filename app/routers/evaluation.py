from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.core.auth import get_current_user
from app.core.evaluation_service import run_evaluation, get_evaluation_history

router = APIRouter()


@router.post("/evaluation/run")
def trigger_evaluation(
    k: int = 5,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return run_evaluation(db, k=k)


@router.get("/evaluation/history")
def evaluation_history(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    history = get_evaluation_history(db)
    if not history:
        return {"status": "not_evaluated", "runs": []}
    return {"status": "ok", "runs": history}
