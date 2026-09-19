from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.core.auth import get_current_user
from app.core.vector_store import vector_store
from app.core.bm25_store import bm25_store
from app.core.llm import llm_service
from app.core.embeddings import embedding_service
from app.models.document import Document

router = APIRouter()


@router.get("/index/health")
def index_health(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    docs = db.query(Document).filter(Document.owner_id == current_user["user_id"]).all()

    current_count = sum(1 for d in docs if d.processing_status == "ready")
    failed_count = sum(1 for d in docs if d.processing_status == "failed")

    embedding_models_in_use = sorted({d.embedding_model for d in docs if d.embedding_model})
    parser_versions_in_use = sorted({d.parser_version for d in docs if d.parser_version})

    known_document_ids = {d.document_id for d in docs}
    all_chunks = vector_store.get_all_chunks()
    all_metadatas = all_chunks.get("metadatas", []) or []

    chunk_document_ids = {m.get("document_id") for m in all_metadatas if m and m.get("document_id")}
    orphaned_document_ids = [doc_id for doc_id in chunk_document_ids if doc_id not in known_document_ids]

    collections = sorted({d.collection_id for d in docs if d.collection_id})

    return {
        "documents": {"current": current_count, "failed": failed_count, "total": len(docs)},
        "orphaned_documents": {"count": len(orphaned_document_ids), "document_ids": orphaned_document_ids[:20]},
        "embedding_models_in_use": embedding_models_in_use,
        "embedding_model_mixed_warning": len(embedding_models_in_use) > 1,
        "parser_versions_in_use": parser_versions_in_use,
        "collections": collections,
        "vector_store": {"backend": vector_store.name, "total_chunks": vector_store.count()},
        "bm25_index": {"total_chunks": len(bm25_store.corpus_ids)},
    }


@router.get("/system/status")
def system_status(current_user: dict = Depends(get_current_user)):
    return {
        "llm_provider": llm_service.provider_name,
        "embedding_provider": embedding_service.provider_name,
        "vector_store_backend": vector_store.name,
    }
