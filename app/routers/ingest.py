import mimetypes
import csv
import io
import openpyxl
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from jose import jwt, JWTError
from app.core.auth import get_current_user
from app.db.database import get_db
from app.schemas.ingest import IngestRequest, IngestResponse
from app.core.document_parser import document_parser
from app.core.document_lifecycle import ingest_or_update_document, mark_document_failed
from app.core.vector_store import vector_store
from app.core.bm25_store import bm25_store
from app.models.document import Document
from app.config import settings

router = APIRouter()

STRATEGY_DESCRIPTIONS = {
    "recursive": "Recursive — fixed-size pieces, split cleanly at paragraph/sentence boundaries.",
    "semantic": "Semantic — grouped by meaning so each piece stays on one topic.",
    "contextual": "Contextual — each piece carries a little surrounding context for the AI.",
}
MAX_STORED_FILE_SIZE = 15 * 1024 * 1024
INLINE_RENDERABLE_EXT = (".pdf", ".txt", ".md", ".json", ".html", ".htm")
TABLE_RENDERABLE_EXT = (".csv", ".xlsx")
NO_BROWSER_RENDERER_EXT = (".docx", ".pptx")

PAGE_STYLE = """
<style>
  :root { --cream:#FFF8CA; --white:#fff; --rosewood:#7A0D0E; --coffee:#2D120D; --ink-soft:#7a5f57; --border:#e6dca3; --sky:#CDE3E8; --radius:10px; }
  * { box-sizing: border-box; }
  body { font-family: 'Inter', -apple-system, sans-serif; background:var(--cream); margin:0; color:var(--coffee); }
  .topbar { background:var(--coffee); color:var(--cream); padding:20px 36px; }
  .topbar-title { font-size:20px; font-weight:700; margin-bottom:4px; }
  .topbar-meta { font-size:12.5px; color:#cbb5ac; }
  .container { max-width: 900px; margin: 0 auto; padding: 28px 36px 60px; }
  .tabs-row { display:flex; gap:8px; margin-bottom:20px; flex-wrap:wrap; }
  .tab-link { text-decoration:none; padding:9px 18px; border-radius:8px; font-size:13px; font-weight:600; border:1.5px solid var(--border); }
  .tab-link.active { background:var(--rosewood); color:var(--cream); border-color:var(--rosewood); }
  .tab-link:not(.active) { background:var(--white); color:var(--coffee); }
  .info-banner { background:var(--sky); border-radius:var(--radius); padding:14px 18px; margin-bottom:20px; font-size:13px; line-height:1.6; }
  .chunk-card { background:var(--white); border:1px solid var(--border); border-radius:var(--radius); padding:18px 22px; margin-bottom:14px; }
  .chunk-label { font-size:11px; color:var(--ink-soft); margin-bottom:8px; text-transform:uppercase; letter-spacing:0.4px; font-weight:600; }
  .chunk-text { font-size:14px; line-height:1.7; white-space:pre-wrap; }
  .full-text-box { background:var(--white); border:1px solid var(--border); border-radius:var(--radius); padding:28px 32px; font-size:14.5px; line-height:1.85; white-space:pre-wrap; }
  table.data-table { width:100%; border-collapse: collapse; background:var(--white); border-radius:var(--radius); overflow:hidden; border:1px solid var(--border); }
  table.data-table th { background: var(--coffee); color: var(--cream); text-align:left; padding:10px 14px; font-size:12.5px; }
  table.data-table td { padding:9px 14px; font-size:13px; border-bottom:1px solid var(--border); }
  table.data-table tr:last-child td { border-bottom:none; }
  table.data-table tr:nth-child(even) td { background: #fffdf0; }
</style>
"""


def _resolve_user_id_from_query_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/ingest", response_model=IngestResponse)
def ingest_document(request: IngestRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        try:
            result = ingest_or_update_document(
                db=db, document_id=request.document_id, owner_id=current_user["user_id"],
                source=request.source, text=request.text, strategy=request.strategy, collection_id=request.collection_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception:
            mark_document_failed(db, request.document_id, current_user["user_id"])
            db.commit()
            raise
        db.commit()
        return IngestResponse(
            document_id=request.document_id, chunks_created=result.chunks_total, strategy_used=request.strategy,
            status="success" if result.action != "unchanged" else "skipped_unchanged", action=result.action,
            version=result.version, collection_id=request.collection_id,
            chunks_reused=result.chunks_reused, chunks_reprocessed=result.chunks_reprocessed,
        )
    except HTTPException:
        db.rollback(); raise
    except Exception as e:
        db.rollback(); raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


def _store_original_file(document_id: str, filename: str, file_bytes: bytes, owner_id: str, db: Session):
    try:
        if len(file_bytes) > MAX_STORED_FILE_SIZE:
            return
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        doc = db.query(Document).filter(Document.document_id == document_id, Document.owner_id == owner_id).first()
        if doc:
            doc.original_filename = filename
            doc.original_content_type = content_type
            doc.original_file_data = file_bytes
    except Exception:
        pass


async def _ingest_one_file(file: UploadFile, document_id: str, source: str, strategy: str, collection_id: str | None, owner_id: str, db: Session) -> dict:
    try:
        file_bytes = await file.read()
    except Exception as e:
        return {"document_id": document_id, "status": "error", "detail": f"Could not read file: {e}"}

    try:
        extracted_text = document_parser.parse(file.filename, file_bytes)
    except ValueError as e:
        return {"document_id": document_id, "status": "error", "detail": str(e)}
    except Exception as e:
        return {"document_id": document_id, "status": "error", "detail": f"Parsing failed: {e}"}

    try:
        result = ingest_or_update_document(db=db, document_id=document_id, owner_id=owner_id, source=source, text=extracted_text, strategy=strategy, collection_id=collection_id)
        db.commit()
    except ValueError as e:
        db.rollback()
        return {"document_id": document_id, "status": "error", "detail": str(e)}
    except Exception as e:
        db.rollback()
        try:
            mark_document_failed(db, document_id, owner_id)
            db.commit()
        except Exception:
            db.rollback()
        return {"document_id": document_id, "status": "error", "detail": f"{type(e).__name__}: {e}"}

    _store_original_file(document_id, file.filename, file_bytes, owner_id, db)
    try:
        db.commit()
    except Exception:
        db.rollback()

    return {"document_id": document_id, "status": "success" if result.action != "unchanged" else "skipped_unchanged", "action": result.action, "chunks_created": result.chunks_total}


@router.post("/ingest/file", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile = File(...), document_id: str = Form(...), source: str = Form(default="file_upload"),
    strategy: str = Form(default="recursive"), collection_id: str = Form(default=None),
    current_user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    result = await _ingest_one_file(file, document_id, source, strategy, collection_id, current_user["user_id"], db)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["detail"])
    doc = db.query(Document).filter(Document.document_id == document_id).first()
    return IngestResponse(
        document_id=document_id, chunks_created=result.get("chunks_created", 0), strategy_used=strategy,
        status=result["status"], action=result["action"], version=doc.version if doc else 1,
        collection_id=collection_id, chunks_reused=0, chunks_reprocessed=0,
    )


@router.post("/ingest/bulk")
async def ingest_bulk(
    files: list[UploadFile] = File(...), strategy: str = Form(default="recursive"),
    collection_id: str = Form(default=None), current_user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    results = []
    used_ids = set()
    for f in files:
        try:
            base_id = f.filename.rsplit(".", 1)[0].replace(" ", "_").lower() if f.filename else "untitled"
            doc_id = base_id
            suffix = 1
            while doc_id in used_ids:
                suffix += 1
                doc_id = f"{base_id}_{suffix}"
            used_ids.add(doc_id)
            outcome = await _ingest_one_file(f, doc_id, "bulk_upload", strategy, collection_id, current_user["user_id"], db)
        except Exception as e:
            outcome = {"document_id": f.filename or "unknown", "status": "error", "detail": f"Unexpected error: {e}"}
        results.append(outcome)
    return {"results": results}


@router.get("/documents")
def list_documents(collection_id: str = None, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Document).filter(Document.owner_id == current_user["user_id"])
    if collection_id:
        query = query.filter(Document.collection_id == collection_id)
    docs = query.all()
    return [
        {"document_id": d.document_id, "source": d.source, "version": d.version, "collection_id": d.collection_id,
         "processing_status": d.processing_status, "embedding_model": d.embedding_model, "chunking_strategy": d.chunking_strategy,
         "has_original": d.original_file_data is not None}
        for d in docs
    ]


@router.get("/collections")
def list_collections(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    results = (
        db.query(Document.collection_id, func.count(Document.id).label("doc_count"))
        .filter(Document.owner_id == current_user["user_id"], Document.collection_id.isnot(None))
        .group_by(Document.collection_id).all()
    )
    return [{"collection_id": r[0], "document_count": r[1]} for r in results]


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.document_id == document_id, Document.owner_id == current_user["user_id"]).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    vector_store.delete_by_document_id(document_id)
    bm25_store.remove_by_document_id(document_id)
    db.delete(doc)
    db.commit()
    return {"status": "deleted", "document_id": document_id}


def _get_ext(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""


@router.get("/documents/{document_id}/download")
def download_document(document_id: str, token: str = Query(...), db: Session = Depends(get_db)):
    user_id = _resolve_user_id_from_query_token(token)
    doc = db.query(Document).filter(Document.document_id == document_id, Document.owner_id == user_id).first()
    if not doc or not doc.original_file_data:
        raise HTTPException(status_code=404, detail="Original file not available for this document")

    filename = doc.original_filename or document_id
    ext = _get_ext(filename)

    # CSV and XLSX get rendered as clean HTML tables — a genuinely better
    # viewing experience than a raw download or a spreadsheet app popup.
    if ext == ".csv":
        try:
            decoded = doc.original_file_data.decode("utf-8")
        except UnicodeDecodeError:
            decoded = doc.original_file_data.decode("latin-1")
        rows = list(csv.reader(io.StringIO(decoded)))
        return HTMLResponse(_render_table_page(filename, rows))

    if ext == ".xlsx":
        wb = openpyxl.load_workbook(io.BytesIO(doc.original_file_data), data_only=True)
        sheet = wb.worksheets[0]
        rows = [[str(c) if c is not None else "" for c in row] for row in sheet.iter_rows(values_only=True)]
        return HTMLResponse(_render_table_page(filename, rows, sheet_name=sheet.title))

    # Python's mimetypes module doesn't reliably register .md, .json, .html
    # on every system — these explicit overrides guarantee correct inline
    # rendering regardless of the host OS's mime database.
    EXTENSION_OVERRIDES = {
        ".md": "text/plain", ".txt": "text/plain",
        ".json": "application/json", ".html": "text/html", ".htm": "text/html",
    }
    content_type = EXTENSION_OVERRIDES.get(ext)
    if not content_type:
        guessed_type, _ = mimetypes.guess_type(filename)
        content_type = guessed_type or doc.original_content_type or "application/octet-stream"

    disposition = "inline" if ext in INLINE_RENDERABLE_EXT or content_type == "application/pdf" else "attachment"

    return Response(
        content=doc.original_file_data, media_type=content_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


def _render_table_page(filename: str, rows: list, sheet_name: str = None) -> str:
    if not rows:
        body = '<p>No data found.</p>'
    else:
        header, data_rows = rows[0], rows[1:]
        thead = "".join(f"<th>{h}</th>" for h in header)
        tbody = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in data_rows[:2000])
        body = f'<table class="data-table"><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>'
        if len(data_rows) > 2000:
            body += f'<p style="margin-top:12px;font-size:12px;color:var(--ink-soft);">Showing first 2000 of {len(data_rows)} rows.</p>'

    return f"""<html><head><title>{filename} — ContextCore</title>{PAGE_STYLE}</head><body>
      <div class="topbar">
        <div class="topbar-title">{filename}</div>
        <div class="topbar-meta">{sheet_name + ' &middot; ' if sheet_name else ''}{len(rows)} row(s)</div>
      </div>
      <div class="container">{body}</div>
    </body></html>"""


@router.get("/documents/{document_id}/view", response_class=HTMLResponse)
def view_document(document_id: str, token: str = Query(...), mode: str = Query(default="full"), db: Session = Depends(get_db)):
    user_id = _resolve_user_id_from_query_token(token)
    doc = db.query(Document).filter(Document.document_id == document_id, Document.owner_id == user_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks_data = vector_store.get_chunks_by_document_id(document_id)
    ids = chunks_data.get("ids", [])
    metadatas = chunks_data.get("metadatas", []) or []
    full_chunks = vector_store.get_all_chunks()
    id_to_text = dict(zip(full_chunks.get("ids", []), full_chunks.get("documents", [])))
    ordered = sorted(zip(ids, metadatas), key=lambda pair: pair[1].get("chunk_index", 0))
    strategy_label = STRATEGY_DESCRIPTIONS.get(doc.chunking_strategy, doc.chunking_strategy or "Unknown")

    ext = _get_ext(doc.original_filename or "")
    has_original = doc.original_file_data is not None
    can_open_natively = has_original and (ext in INLINE_RENDERABLE_EXT or ext in TABLE_RENDERABLE_EXT)

    info_banner = ""
    if has_original and ext in NO_BROWSER_RENDERER_EXT:
        info_banner = f'<div class="info-banner">This is a {ext.strip(".").upper()} file. Browsers have no built-in viewer for this format, so it downloads instead of opening inline — this applies to every website, not just this one. Once this app is deployed publicly, files like this can be rendered inline using Microsoft/Google\'s document viewer services.</div>'

    original_action = ""
    if has_original:
        label = "Open Original File" if can_open_natively else "Download Original File"
        original_action = f'<a href="/documents/{document_id}/download?token={token}" target="_blank" class="tab-link">{label}</a>'
    else:
        original_action = '<span style="font-size:12px;color:#7a5f57;align-self:center;">Original file not stored (older upload or too large)</span>'

    if mode == "chunks":
        chunk_html = f'<div class="info-banner">Chunking technique used: <strong>{strategy_label}</strong></div>'
        for cid, meta in ordered:
            text = id_to_text.get(cid, "")
            page = meta.get("page_number")
            page_label = f" &middot; page {page}" if isinstance(page, int) and page >= 0 else ""
            chunk_html += f'<div class="chunk-card"><div class="chunk-label">Chunk {meta.get("chunk_index", "?")}{page_label}</div><div class="chunk-text">{text}</div></div>'
        body = chunk_html
    else:
        full_text = "\n\n".join(id_to_text.get(cid, "") for cid, _ in ordered)
        body = f'<div class="full-text-box">{full_text}</div>'

    nav = f'''<div class="tabs-row">
      <a href="?token={token}&mode=full" class="tab-link {"active" if mode == "full" else ""}">Extracted Text</a>
      <a href="?token={token}&mode=chunks" class="tab-link {"active" if mode == "chunks" else ""}">View Chunks (Technique)</a>
      {original_action}
    </div>'''

    return f"""<html><head><title>{document_id} — ContextCore</title>{PAGE_STYLE}</head><body>
      <div class="topbar">
        <div class="topbar-title">{document_id}</div>
        <div class="topbar-meta">Version {doc.version} &middot; {doc.source} &middot; {doc.collection_id or 'no collection'} &middot; {len(ordered)} chunk(s)</div>
      </div>
      <div class="container">
        {nav}
        {info_banner}
        {body}
      </div>
    </body></html>"""
