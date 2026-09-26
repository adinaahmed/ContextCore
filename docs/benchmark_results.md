# Benchmark Results

Generated: 2026-09-26 14:57  
Embedding model: local:all-MiniLM-L6-v2  
Chunk size / overlap: 500 / 50  
Hybrid weights (dense / sparse): 0.6 / 0.4

## 1. Chunking Strategy Comparison

Test document: a fictional lab handbook (3,556 characters, 8 sections), 12 questions with known answer phrases. Retrieval uses the same hybrid (dense + BM25) scoring and cross-encoder reranking as the application.

| Strategy | Chunks | Avg chunk length | Hit@1 | Hit@3 | Hit@5 | MRR | MRR without reranker | Chunking time (s) | Embedding time (s) |
|---|---|---|---|---|---|---|---|---|---|
| recursive | 10 | 354 | 100% | 100% | 100% | 1.000 | 1.000 | 0.00 | 0.26 |
| semantic | 21 | 168 | 92% | 92% | 92% | 0.917 | 0.917 | 0.05 | 0.03 |

Best MRR: **recursive** (1.000).

## 2. Latency Profiling

10 questions run through `/query/trace`. LLM provider(s) used: gemini:gemini-3.6-flash, ollama:gemma3:4b.

| Question | Route | Routing (ms) | Retrieval (ms) | Reranking (ms) | Generation (ms) | Total (ms) |
|---|---|---|---|---|---|---|
| What time does the lab open on Saturdays? | simple | 0.0 | 10.0 | 34.6 | 2627.4 | 2672.1 |
| Who approves after-hours access to the lab? | simple | 0.0 | 60.0 | 45.9 | 2674.2 | 2780.2 |
| When is the chemical safety course held? | simple | 0.1 | 52.6 | 48.7 | 1767.1 | 1868.5 |
| Where is the emergency eyewash station? | simple | 0.0 | 41.5 | 52.4 | 1934.2 | 2028.1 |
| How many equipment booking slots can one person book per week? | simple | 0.0 | 76.6 | 51.9 | 3134.7 | 3263.2 |
| Who provides training on the mass spectrometer? | simple | 0.1 | 63.9 | 46.3 | 3628.7 | 3739.1 |
| How long are server backups kept? | simple | 0.0 | 62.2 | 50.5 | 8871.6 | 8984.4 |
| Which grant must publications acknowledge? | simple | 0.0 | 271.3 | 49.7 | 4055.5 | 4376.5 |
| What is the maximum travel reimbursement for international conferences? | simple | 0.0 | 89.7 | 51.5 | 1741.8 | 1883.1 |
| How often does a mentor meet a new member? | simple | 0.0 | 61.0 | 43.6 | 3196.7 | 3301.3 |

| Summary | Value |
|---|---|
| Mean routing (ms) | 0.0 |
| Mean retrieval (ms) | 78.9 |
| Mean reranking (ms) | 47.5 |
| Mean generation (ms) | 3363.2 |
| Median total (ms) | 3021.7 |
| 95th percentile total (ms) | 8984.4 |
| Slowest stage (bottleneck) | generation |

## 3. Grounding Check (Out-of-Scope Questions)

These questions cannot be answered from the uploaded document. A grounded system should decline.

| Question | Declined? | Answer (first 160 characters) |
|---|---|---|
| What is the capital of Australia? | Yes | There is not enough information in the provided sources to answer the question. |
| Who won the football World Cup in 2018? | Yes | There is not enough information. None of the provided documents contain information about sports results, specifically the 2018 football World Cup. |
