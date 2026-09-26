# ContextCore — AI Document Intelligence

ContextCore lets you upload your own documents and ask questions about them in plain language. Instead of relying on an AI model's general knowledge, it first searches your documents for the most relevant passages and then generates an answer based only on that content, showing the exact sources and page numbers it used.

## Screenshots

| Login | Ask AI with cited answer |
|---|---|
| ![Login](docs/images/login.png) | ![Ask AI](docs/images/ask-ai.png) |

| Documents — Simple mode | Documents — Advanced mode |
|---|---|
| ![Documents in Simple mode](docs/images/documents1.png) | ![Documents in Advanced mode](docs/images/documents2.png) |

**RAG Pipeline trace (Advanced mode)**

![RAG Pipeline trace](docs/images/pipeline.png)

Simple mode (the default) keeps the interface clean for everyday users. Advanced mode, switched on in Settings, adds chunking strategy selection, collections, processing details, pipeline tracing and evaluation.

## Results

Measured with `scripts/benchmark.py` (full report: [docs/benchmark_results.md](docs/benchmark_results.md)):

| Metric | Result |
|---|---|
| Retrieval accuracy (recursive chunking) | 12 / 12 questions answered from the correct passage (MRR 1.000) |
| Retrieval accuracy (semantic chunking) | 11 / 12 (MRR 0.917) |
| Search time (retrieval + reranking) | About 130 ms per question |
| Median total response time | About 3 seconds (mostly the LLM writing the answer) |
| Out-of-scope questions | 2 / 2 correctly declined instead of inventing an answer |
| Automated tests | 41 / 41 passing |

## Key Features

- **Multi-format document support:** PDF, DOCX, PPTX, XLSX, CSV, JSON, HTML, TXT and Markdown
- **OCR for scanned documents:** reads image-only PDF pages using Tesseract
- **Smart document parsing:** handles multi-column layouts, tables, headings and broken symbol fonts, and describes embedded images and charts
- **Hybrid search:** combines semantic (meaning-based) search with keyword (BM25) search
- **Reranking:** a cross-encoder reorders results so the most relevant passages reach the AI
- **Adaptive query routing:** simple questions are answered quickly; complex ones automatically get deeper retrieval
- **Query rewriting:** fixes spelling, resolves follow-up references and expands questions before searching
- **Cited answers:** every answer lists the documents and page numbers it came from, with a confidence indicator
- **Multi-document chat:** search all documents, or restrict a question to specific ones
- **Persistent chat history:** continue, search and export previous conversations; long chats are summarised automatically
- **Incremental indexing:** re-uploading an edited document only reprocesses the parts that changed
- **Automatic fallback:** if Gemini is unavailable, a local model (Ollama) answers instead, and calculations still work without any AI
- **Built-in evaluation:** measures retrieval accuracy with Recall@K and MRR
- **Secure multi-user accounts:** JWT authentication, with each user's documents searchable only by that user
- **Clean interface:** Simple mode for everyday users, Advanced mode for technical tools, plus light and dark themes

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic |
| Database | PostgreSQL, SQLAlchemy |
| Vector search | ChromaDB + BM25 |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2, runs locally) |
| Reranking | Cross-encoder (ms-marco-MiniLM-L-6-v2) |
| LLM | Google Gemini, with Ollama (Gemma 3) as local fallback |
| Orchestration | LangChain (LCEL, output parsers) |
| OCR | Tesseract |
| Frontend | HTML, CSS, JavaScript |
| Deployment | Docker, Docker Compose |

## How It Works

1. **Upload:** documents are parsed, split into smaller chunks and converted into searchable vectors.
2. **Ask:** your question is routed, rewritten for clarity and matched against those chunks using hybrid search and reranking.
3. **Answer:** the most relevant chunks are sent to the AI model, which writes an answer grounded in them, with citations.

## Architecture

```mermaid
flowchart LR
    U[Browser UI] -->|REST + JWT| API[FastAPI]
    API --> R{Router}
    R -->|direct| LLM[LLM: Gemini, fallback Ollama]
    R -->|calculation| T[Calculator tool]
    R -->|simple / complex| QR[Query rewriting]
    QR --> H[Hybrid retrieval<br/>ChromaDB + BM25]
    H --> RR[Cross-encoder reranking]
    RR --> LLM
    API --> PG[(PostgreSQL<br/>users, documents, chats)]
    ING[Upload] --> P[Parser + OCR] --> C[Chunking] --> E[Embeddings] --> H
```

**Ingestion:** documents are parsed (with OCR for scanned pages), split into chunks, embedded locally and stored in ChromaDB and the BM25 index. Metadata, versions and ownership are stored in PostgreSQL.

**Querying:** each question is routed, rewritten, matched using hybrid search, reranked, and answered by the LLM using only the retrieved passages, with citations. All retrieval is restricted to the logged-in user's documents.

Design decisions and comparisons: [docs/DESIGN.md](docs/DESIGN.md). Measured results: [docs/benchmark_results.md](docs/benchmark_results.md).

## Configuration

All settings are read from `.env` (copy `.env.example` to start):

| Setting | Default | Description |
|---|---|---|
| `GOOGLE_API_KEY` | (required) | Gemini API key |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Gemini model used for generation |
| `DATABASE_URL` | (required) | PostgreSQL connection string |
| `JWT_SECRET_KEY` | (required) | Secret used to sign login tokens |
| `LLM_PROVIDER` / `LLM_FALLBACK_PROVIDER` | `gemini` / `ollama` | Primary and backup language model |
| `OLLAMA_MODEL` / `OLLAMA_BASE_URL` | `gemma3:4b` / `http://localhost:11434` | Local fallback model |
| `EMBEDDING_PROVIDER` | `local` | Embedding backend (all-MiniLM-L6-v2) |
| `VECTOR_STORE_PROVIDER` / `CHROMA_PERSIST_DIRECTORY` | `chroma` / `./chroma_db` | Vector database and storage folder |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `500` / `50` | Chunk size and overlap in characters |
| `DEFAULT_CHUNK_STRATEGY` | `recursive` | `recursive`, `semantic` or `contextual` |
| `DENSE_WEIGHT` / `SPARSE_WEIGHT` | `0.6` / `0.4` | Hybrid retrieval weighting |
| `ROUTER_MODE` | `fast` | `fast` (rule-based) or `llm` (LLM router chain) |
| `QUERY_REWRITE_EXPAND` | `true` | Rewrite and expand every question before retrieval |

## API Documentation and Testing

- Interactive API docs (Swagger): http://127.0.0.1:8000/docs
- A Postman collection is included in the `postman/` folder.
- Run the test suite and benchmarks:

```bash
pytest -v                   # all tests
pytest -v -m "not llm"      # skip tests that call the language model
python scripts/benchmark.py # chunking comparison and latency report
```

**About the Evaluation page:** it measures retrieval accuracy (Recall@K, MRR) against `evaluation_dataset.json`, which lists sample questions and the document each answer should come from. It shows 0% until that file matches your own uploaded documents. To measure the pipeline without editing anything, run `python scripts/benchmark.py`, which uses a built-in test document.

## Getting Started

### Requirements
- Python 3.11 (not 3.12+, some libraries aren't compatible yet)
- PostgreSQL
- Tesseract OCR (only needed for scanned PDFs)
- A free Google Gemini API key from https://aistudio.google.com/apikey (use a personal Google account; many university accounts are blocked)
- Optional: Ollama with the `gemma3:4b` model, as a local fallback

### Setup
```bash
git clone https://github.com/adinaahmed/ContextCore.git
cd ContextCore
python3.11 -m venv .venv          # Windows: py -3.11 -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt   # Mac/Linux: optionally also run  pip install uvloop  for extra speed
```

Copy `.env.example` to `.env` and fill in your own values:
```
GOOGLE_API_KEY=your_gemini_key
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/rag_db
JWT_SECRET_KEY=any_long_random_text
```

Create the database and tables, then start the server:
```bash
psql -U postgres -c "CREATE DATABASE rag_db;"
python init_db.py
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open http://127.0.0.1:8000/ui/ and register an account.

## Authors
- Hifsa Khattak
- Adina Ahmed
