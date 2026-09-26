# ContextCore — Design Decisions

This document records the research and trade-offs behind the main technical choices, as required by the development plan. Measured results are in [benchmark_results.md](benchmark_results.md).

## 1. Vector Database Selection

| Criterion | ChromaDB | FAISS | Pinecone | Weaviate |
|---|---|---|---|---|
| Type | Open-source vector database | Similarity-search library (Meta) | Fully managed cloud service | Open-source vector database |
| Local setup | `pip install`, runs inside the app | `pip install`, library only | Not available locally | Separate server (usually Docker) |
| Persistence | Built-in, on disk | Manual (save/load index files) | Managed by the provider | Built-in |
| Metadata filtering | Yes (`where` filters) | No native support | Yes | Yes |
| Cost | Free | Free | Free starter tier, then paid | Free self-hosted, paid cloud |
| Network dependency | None | None | Requires internet and API key | None when self-hosted |

**Decision: ChromaDB.** It runs locally with no extra server, persists to disk automatically and supports metadata filtering, which the project relies on for per-user data isolation, scoped search and incremental re-indexing. FAISS would need a separate store for metadata and manual persistence. Pinecone adds a network dependency and a usage limit. Weaviate is powerful but needs a separate server, which is unnecessary at this scale.

**Hosted vs local:** a local store keeps documents on the user's machine, costs nothing and has no network latency; a hosted store survives server restarts and scales further. The vector store sits behind an interface (`app/core/vector_stores/`), so switching to a hosted option (for example Qdrant Cloud for deployment) only requires one new class.

## 2. Embedding Model Selection

| Criterion | all-MiniLM-L6-v2 (chosen) | all-mpnet-base-v2 | Paid API embeddings (e.g. Gemini, OpenAI) |
|---|---|---|---|
| Dimensions | 384 | 768 | Typically 768 to 3072 |
| Model size | About 90 MB | About 420 MB | Hosted by the provider |
| Speed on CPU | Fast | Several times slower | Depends on network |
| Quality | Good for short passages | Higher | High |
| Cost per call | Free | Free | Per-request pricing and rate limits |
| Privacy | Text never leaves the machine | Text never leaves the machine | Text sent to a third party |

**Decision: all-MiniLM-L6-v2.** It runs locally with no per-call cost or rate limits, which matters because the Gemini free tier is already the main bottleneck. It is fast enough on an ordinary laptop CPU, and document text stays private. Its 384-dimensional vectors are fully supported by ChromaDB. The quality gap to larger models is reduced in practice by hybrid search and cross-encoder reranking.

## 3. Chunking Strategies

| Strategy | How it works | Strengths | Costs |
|---|---|---|---|
| Recursive (default) | Fixed-size chunks (500 characters, 50 overlap), split at paragraph and sentence boundaries | Fast, predictable, no API calls | Can split a fact across two chunks |
| Semantic | Groups consecutive sentences whose embeddings are similar | Keeps each chunk on one topic | Chunk sizes vary widely |
| Contextual | Recursive chunks, each prefixed with a one-sentence LLM summary of where it fits in the document | Chunks remain understandable out of context | One LLM call per chunk: slow and uses API quota |

Chunk size, overlap and the default strategy are configurable in `.env`. Measured retrieval quality for each strategy is in [benchmark_results.md](benchmark_results.md).

## 4. Retrieval Pipeline

1. **Routing:** questions are classified as direct, calculation, simple or complex. A rule-based router is the default (instant, no API call); the LLM router chain can be enabled with `ROUTER_MODE=llm`.
2. **Query rewriting:** a single LLM call resolves references to earlier turns, fixes spelling and expands the question.
3. **Hybrid retrieval:** dense (embedding) and sparse (BM25) scores are normalised and combined with configurable weights (default 0.6 / 0.4).
4. **Multi-query and context compression:** enabled automatically for complex questions, or manually in the interface.
5. **Reranking:** a cross-encoder (ms-marco-MiniLM-L-6-v2) re-scores candidates jointly with the question.
6. **Generation:** the answer is written only from the retrieved context, with citations.

All retrieval stages filter by the logged-in user, so users never see each other's documents.

## 5. Deliberate Differences from the Development Plan

| Plan | Implementation | Reason |
|---|---|---|
| Router: "retrieval" or "direct" | Four routes: direct, calculation, simple, complex | Finer control over cost and depth of retrieval |
| LLM router chain | LLM router available; rule-based router by default | Avoids an extra API call per question under the free-tier limit |
| LangChain `BM25Retriever` and `langchain-chroma` | `rank-bm25` and ChromaDB used directly | Needed for per-user filtering, incremental indexing and index-consistency checks |
| LCEL for generation | LCEL chain with JSON output parser on `/query/structured`; main endpoint uses the provider layer | Keeps automatic failover from Gemini to a local Ollama model |
| `/api/auth/*` | `/auth/*` | Naming only |
| `google-generativeai` SDK | `google-genai` SDK | Official successor SDK |

## 6. Beyond the Plan

Multi-format ingestion (PDF, DOCX, PPTX, XLSX, CSV, JSON, HTML, TXT, Markdown), OCR for scanned pages, image and chart descriptions, page-level citations, document versioning with incremental re-indexing, per-user data isolation, LLM failover with a local calculator fallback, retrieval evaluation (Recall@K, MRR), index health monitoring, Docker support and a full web interface.

## 7. Known Limitations

- **Gemini free tier:** about 20 requests per day for the default model; the app falls back to the local Ollama model when the limit is reached.
- **Scoped search:** when a question is limited to specific documents, only dense retrieval is used, because the BM25 index has no metadata filter.
- **Document IDs** are unique across the whole system; a name already used by another account is rejected with a clear message.
- **Document viewer links** carry the login token in the URL; a short-lived signed link would be safer for public deployment.
