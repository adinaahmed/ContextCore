# RAG Backend

A production-style Retrieval-Augmented Generation backend built with FastAPI, ChromaDB, and Google Gemini.

## Architecture
User → FastAPI → JWT Auth → Router Chain (direct vs retrieval)
↓
Query Rewriting (using session memory)
↓
Hybrid Retrieval (BM25 + Dense/ChromaDB)
↓
Cross-Encoder Reranking
↓
(optional) Context Compression
↓
Gemini (LCEL chain, structured output)
↓
Grounded Answer + Sources

## Tech Stack

- **API**: FastAPI, Pydantic
- **Vector DB**: ChromaDB (persistent)
- **Sparse Retrieval**: BM25 (rank-bm25)
- **Embeddings**: sentence-transformers (all-MiniLM-L6-v2)
- **Reranking**: cross-encoder/ms-marco-MiniLM-L-6-v2
- **LLM**: Google Gemini (via google-genai SDK + LangChain LCEL)
- **Database**: PostgreSQL + SQLAlchemy
- **Auth**: JWT (python-jose) + bcrypt

## Setup

1. Clone the repo, create a virtual environment: `python3.11 -m venv .venv && source .venv/bin/activate`
2. Install dependencies: `pip install -r requirements.txt`
3. Set up PostgreSQL: `createdb rag_db`
4. Copy `.env.example` to `.env` and fill in your values (see below)
5. Initialize the database: `python init_db.py`
6. Run the server: `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
7. Visit `http://127.0.0.1:8000/docs` for interactive API docs

## Environment Variables
GOOGLE_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.6-flash
DATABASE_URL=postgresql://user@localhost:5432/rag_db
JWT_SECRET_KEY=your_random_secret

## API Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/health` | GET | No | Health check |
| `/auth/register` | POST | No | Create a user account |
| `/auth/login` | POST | No | Get a JWT access token |
| `/ingest` | POST | JWT | Ingest and chunk a document |
| `/query` | POST | JWT | Ask a question, get a grounded answer |
| `/query/structured` | POST | JWT | Same, with structured JSON output (answer/confidence/sources/used_retrieval) |
| `/query/tools` | POST | JWT | Ask a question with calculator tool-calling enabled |
| `/query/profile` | POST | JWT | Same as `/query`, with per-stage latency breakdown |
| `/query/history/{session_id}` | GET | JWT | Retrieve conversation history for a session |

## Chunking Strategies

Select via `"strategy"` field on `/ingest`: `"recursive"`, `"semantic"`, or `"contextual"`.

## Query Options

- `use_multi_query`: generate query variants for wider retrieval recall
- `use_context_compression`: trim retrieved chunks to only relevant sentences
- `session_id`: enables conversational memory and query rewriting for follow-ups

## Testing

```bash
pytest tests/test_integration.py -v
```

## Known Limitations

- Conversation memory is currently in-memory (not persisted to PostgreSQL) — resets on server restart
- BM25 index rebuilds from ChromaDB on startup (not independently persisted)
- Google Gemini free tier is capped at 20 requests/day; heavy testing may require a paid tier or provider switch