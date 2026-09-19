import hashlib
import re
from sqlalchemy.orm import Session
from app.models.document import Document
from app.core.vector_store import vector_store
from app.core.bm25_store import bm25_store
from app.core.embeddings import embedding_service
from app.core.chunking import chunking_service

PAGE_MARKER_PATTERN = re.compile(r"\[PAGE (\d+)\]")


def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_page_and_clean(full_text: str, chunk_text: str, search_from: int) -> tuple[int | None, str, int]:
    idx = full_text.find(chunk_text, search_from)
    if idx == -1:
        idx = full_text.find(chunk_text)
    page_number = None
    new_search_from = search_from
    if idx != -1:
        region_end = idx + len(chunk_text)
        region = full_text[:region_end]
        matches = PAGE_MARKER_PATTERN.findall(region)
        if matches:
            page_number = int(matches[-1])
        new_search_from = region_end
    cleaned = PAGE_MARKER_PATTERN.sub("", chunk_text).strip()
    return page_number, cleaned, new_search_from


class IngestionResult:
    def __init__(self, action, version, chunks_total, chunks_reused, chunks_reprocessed):
        self.action = action
        self.version = version
        self.chunks_total = chunks_total
        self.chunks_reused = chunks_reused
        self.chunks_reprocessed = chunks_reprocessed


def ingest_or_update_document(
    db: Session, document_id: str, owner_id: str, source: str, text: str,
    strategy: str, collection_id: str | None = None,
) -> IngestionResult:
    doc_hash = compute_hash(text)
    existing = db.query(Document).filter(Document.document_id == document_id).first()

    if existing is not None and existing.file_hash == doc_hash:
        return IngestionResult(action="unchanged", version=existing.version, chunks_total=0, chunks_reused=0, chunks_reprocessed=0)

    raw_chunks = chunking_service.chunk_text(text, strategy=strategy)
    if not raw_chunks:
        raise ValueError("No chunks produced from input text")

    search_cursor = 0
    new_chunks, page_numbers = [], []
    for raw_chunk in raw_chunks:
        page_number, cleaned_text, search_cursor = _extract_page_and_clean(text, raw_chunk, search_cursor)
        new_chunks.append(cleaned_text)
        page_numbers.append(page_number)

    new_hashes = [compute_hash(c) for c in new_chunks]

    existing_chunks_data = vector_store.get_chunks_by_document_id(document_id)
    existing_ids = existing_chunks_data.get("ids", [])
    existing_metadatas = existing_chunks_data.get("metadatas", []) or []

    existing_by_index = {}
    for cid, meta in zip(existing_ids, existing_metadatas):
        idx = meta.get("chunk_index")
        if idx is not None:
            existing_by_index[idx] = (cid, meta.get("content_hash"))

    chunks_reused = chunks_reprocessed = 0
    ids_to_delete, ids_to_add, texts_to_add, metadatas_to_add = [], [], [], []

    for i, (chunk_text, chunk_hash, page_number) in enumerate(zip(new_chunks, new_hashes, page_numbers)):
        old_entry = existing_by_index.get(i)
        if old_entry is not None and old_entry[1] == chunk_hash:
            chunks_reused += 1
            continue
        chunks_reprocessed += 1
        if old_entry is not None:
            ids_to_delete.append(old_entry[0])
        new_chunk_id = f"{document_id}_chunk_{i}"
        ids_to_add.append(new_chunk_id)
        texts_to_add.append(chunk_text)
        metadatas_to_add.append({
            "document_id": document_id, "source": source, "chunk_index": i,
            "owner_id": owner_id, "content_hash": chunk_hash,
            "page_number": page_number if page_number is not None else -1,
        })

    for idx, (cid, _) in existing_by_index.items():
        if idx >= len(new_chunks):
            ids_to_delete.append(cid)

    if ids_to_delete:
        vector_store.delete_by_chunk_ids(ids_to_delete)
        bm25_store.remove_by_ids(ids_to_delete)

    if ids_to_add:
        embeddings_to_add = embedding_service.embed_batch(texts_to_add)
        vector_store.add_chunks(ids=ids_to_add, texts=texts_to_add, embeddings=embeddings_to_add, metadatas=metadatas_to_add)

    if existing is None:
        new_doc = Document(
            document_id=document_id, owner_id=owner_id, source=source, file_hash=doc_hash,
            version=1, collection_id=collection_id, embedding_model=embedding_service.provider_name,
            chunking_strategy=strategy, processing_status="ready",
        )
        db.add(new_doc)
        version, action = 1, "new"
    else:
        existing.file_hash = doc_hash
        existing.version += 1
        existing.collection_id = collection_id or existing.collection_id
        existing.embedding_model = embedding_service.provider_name
        existing.chunking_strategy = strategy
        existing.processing_status = "ready"
        version, action = existing.version, "updated"

    db.flush()
    return IngestionResult(action=action, version=version, chunks_total=len(new_chunks), chunks_reused=chunks_reused, chunks_reprocessed=chunks_reprocessed)


def mark_document_failed(db: Session, document_id: str, owner_id: str):
    existing = db.query(Document).filter(Document.document_id == document_id).first()
    if existing:
        existing.processing_status = "failed"
        db.flush()
