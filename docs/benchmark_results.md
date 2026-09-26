# Benchmark Results

Generated: 2026-09-26 08:30  
Embedding model: local:all-MiniLM-L6-v2  
Chunk size / overlap: 500 / 50  
Hybrid weights (dense / sparse): 0.6 / 0.4

## 1. Chunking Strategy Comparison

Test document: a fictional lab handbook (3,556 characters, 8 sections), 12 questions with known answer phrases. Retrieval uses the same hybrid (dense + BM25) scoring and cross-encoder reranking as the application.

| Strategy | Chunks | Avg chunk length | Hit@1 | Hit@3 | Hit@5 | MRR | MRR without reranker | Chunking time (s) | Embedding time (s) |
|---|---|---|---|---|---|---|---|---|---|
| recursive | 10 | 354 | 100% | 100% | 100% | 1.000 | 1.000 | 0.00 | 0.30 |
| semantic | 21 | 168 | 92% | 92% | 92% | 0.917 | 0.917 | 0.06 | 0.03 |

Best MRR: **recursive** (1.000).

## 2. Latency Profiling

10 questions run through `/query/trace`. LLM provider(s) used: ollama:gemma3:4b.

| Question | Route | Routing (ms) | Retrieval (ms) | Reranking (ms) | Generation (ms) | Total (ms) |
|---|---|---|---|---|---|---|
| What time does the lab open on Saturdays? | simple | 0.0 | 11.2 | 31.1 | 3466.7 | 3509.0 |
| Who approves after-hours access to the lab? | simple | 0.0 | 88.5 | 25.2 | 3282.1 | 3395.8 |
| When is the chemical safety course held? | simple | 0.0 | 60.0 | 24.1 | 2962.1 | 3046.3 |
| Where is the emergency eyewash station? | simple | 0.0 | 52.2 | 22.7 | 2293.7 | 2368.6 |
| How many equipment booking slots can one person book per week? | simple | 0.0 | 42.9 | 24.3 | 2198.4 | 2265.5 |
| Who provides training on the mass spectrometer? | simple | 0.0 | 45.5 | 24.1 | 1964.6 | 2034.2 |
| How long are server backups kept? | simple | 0.1 | 47.5 | 23.3 | 3290.0 | 3360.9 |
| Which grant must publications acknowledge? | simple | 0.0 | 48.2 | 23.9 | 3026.0 | 3098.1 |
| What is the maximum travel reimbursement for international conferences? | simple | 0.0 | 62.9 | 25.8 | 3474.0 | 3562.7 |
| How often does a mentor meet a new member? | simple | 0.0 | 71.7 | 23.8 | 1959.7 | 2055.2 |

| Summary | Value |
|---|---|
| Mean routing (ms) | 0.0 |
| Mean retrieval (ms) | 53.1 |
| Mean reranking (ms) | 24.8 |
| Mean generation (ms) | 2791.7 |
| Median total (ms) | 3072.2 |
| 95th percentile total (ms) | 3562.7 |
| Slowest stage (bottleneck) | generation |

## 3. Grounding Check (Out-of-Scope Questions)

These questions cannot be answered from the uploaded document. A grounded system should decline.

| Question | Declined? | Answer (first 160 characters) |
|---|---|---|
| What is the capital of Australia? | Yes | There is not enough information. The provided documents contain details about the Northwind Research Lab’s hours, access procedures, safety protocols, equipment |
| Who won the football World Cup in 2018? | Yes | There is not enough information. The provided documents contain details about the Northwind Research Lab's operations, safety procedures, and equipment booking  |
