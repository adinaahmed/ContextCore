import time
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.routers import ingest, query, auth, evaluation, index_health
from app.core.vector_store import vector_store
from app.core.bm25_store import bm25_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag_backend")

app = FastAPI(title="RAG Backend")

app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")


@app.on_event("startup")
def rebuild_bm25_on_startup():
    all_chunks = vector_store.get_all_chunks()
    ids = all_chunks.get("ids", [])
    texts = all_chunks.get("documents", [])

    if ids:
        bm25_store.rebuild_from_source(ids=ids, texts=texts)
        print(f"[startup] BM25 index rebuilt from {len(ids)} persisted chunks.")
    else:
        print("[startup] No existing chunks found — BM25 index starts empty.")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {duration:.3f}s")
    return response


app.include_router(ingest.router)
app.include_router(query.router)
app.include_router(auth.router)
app.include_router(evaluation.router)
app.include_router(index_health.router)


@app.get("/health")
def health():
    return {"status": "ok", "chunk_strategy": settings.default_chunk_strategy}
