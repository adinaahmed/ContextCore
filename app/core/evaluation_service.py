import json
import time
from sqlalchemy.orm import Session
from app.core.hybrid_retrieval import hybrid_retriever
from app.core.embeddings import embedding_service
from app.models.evaluation import EvaluationRun

DATASET_PATH = "evaluation_dataset.json"


def load_dataset() -> list[dict]:
    try:
        with open(DATASET_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def run_evaluation(db: Session, k: int = 5) -> dict:
    dataset = load_dataset()

    if not dataset:
        return {
            "status": "not_evaluated",
            "message": "No evaluation dataset found. Add questions to evaluation_dataset.json.",
        }

    reciprocal_ranks = []
    hits = 0
    latencies = []

    for item in dataset:
        question = item["question"]
        expected_doc_id = item["expected_document_id"]

        start = time.perf_counter()
        results = hybrid_retriever.retrieve(question, top_k=k)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

        rank = None
        for i, r in enumerate(results, start=1):
            result_doc_id = (r.get("metadata") or {}).get("document_id")
            if result_doc_id == expected_doc_id:
                rank = i
                break

        if rank is not None:
            hits += 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)

    recall_at_k = hits / len(dataset)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
    avg_latency = sum(latencies) / len(latencies)

    run = EvaluationRun(
        embedding_model=embedding_service.provider_name,
        k_value=k,
        num_questions=len(dataset),
        recall_at_k=round(recall_at_k, 4),
        mrr=round(mrr, 4),
        avg_latency_ms=round(avg_latency, 2),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return {
        "status": "evaluated",
        "run_id": run.id,
        "run_at": run.run_at.isoformat(),
        "embedding_model": run.embedding_model,
        "k_value": run.k_value,
        "num_questions": run.num_questions,
        "recall_at_k": run.recall_at_k,
        "mrr": run.mrr,
        "avg_latency_ms": run.avg_latency_ms,
    }


def get_evaluation_history(db: Session) -> list[dict]:
    runs = db.query(EvaluationRun).order_by(EvaluationRun.run_at.desc()).all()
    if not runs:
        return []
    return [
        {
            "run_id": r.id,
            "run_at": r.run_at.isoformat(),
            "embedding_model": r.embedding_model,
            "k_value": r.k_value,
            "num_questions": r.num_questions,
            "recall_at_k": r.recall_at_k,
            "mrr": r.mrr,
            "avg_latency_ms": r.avg_latency_ms,
        }
        for r in runs
    ]
