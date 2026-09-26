# Benchmark Results

Generated: 2026-09-26 12:23  
Embedding model: local:all-MiniLM-L6-v2  
Chunk size / overlap: 500 / 50  
Hybrid weights (dense / sparse): 0.6 / 0.4

## 1. Chunking Strategy Comparison

Test document: a fictional lab handbook (3,556 characters, 8 sections), 12 questions with known answer phrases. Retrieval uses the same hybrid (dense + BM25) scoring and cross-encoder reranking as the application.

| Strategy | Chunks | Avg chunk length | Hit@1 | Hit@3 | Hit@5 | MRR | MRR without reranker | Chunking time (s) | Embedding time (s) |
|---|---|---|---|---|---|---|---|---|---|
| recursive | 10 | 354 | 100% | 100% | 100% | 1.000 | 1.000 | 0.00 | 0.16 |
| semantic | 21 | 168 | 92% | 92% | 92% | 0.917 | 0.917 | 0.20 | 0.18 |

Best MRR: **recursive** (1.000).

## 2. Latency Profiling

10 questions run through `/query/trace`. LLM provider(s) used: gemini:gemini-3.6-flash, ollama:gemma3:4b.

| Question | Route | Routing (ms) | Retrieval (ms) | Reranking (ms) | Generation (ms) | Total (ms) |
|---|---|---|---|---|---|---|
| What time does the lab open on Saturdays? | simple | 0.1 | 19.9 | 234.1 | 2917.2 | 3171.3 |
| Who approves after-hours access to the lab? | simple | 0.0 | 20.5 | 149.2 | 3477.0 | 3646.8 |
| When is the chemical safety course held? | simple | 0.0 | 19.7 | 150.5 | 1648.7 | 1818.9 |
| Where is the emergency eyewash station? | simple | 0.0 | 17.2 | 139.9 | 2721.1 | 2878.2 |
| How many equipment booking slots can one person book per week? | simple | 0.0 | 20.5 | 146.1 | 1643.0 | 1809.7 |
| Who provides training on the mass spectrometer? | simple | 0.0 | 18.7 | 139.5 | 2780.5 | 2938.8 |
| How long are server backups kept? | simple | 0.0 | 19.7 | 161.0 | 25075.7 | 25256.4 |
| Which grant must publications acknowledge? | simple | 0.0 | 25.5 | 216.7 | 3113.2 | 3355.4 |
| What is the maximum travel reimbursement for international conferences? | simple | 0.0 | 22.4 | 203.3 | 1954.7 | 2180.5 |
| How often does a mentor meet a new member? | simple | 0.0 | 21.1 | 176.4 | 16326.6 | 16524.2 |

| Summary | Value |
|---|---|
| Mean routing (ms) | 0.0 |
| Mean retrieval (ms) | 20.5 |
| Mean reranking (ms) | 171.7 |
| Mean generation (ms) | 6165.8 |
| Median total (ms) | 3055.0 |
| 95th percentile total (ms) | 25256.4 |
| Slowest stage (bottleneck) | generation |

## 3. Grounding Check (Out-of-Scope Questions)

These questions cannot be answered from the uploaded document. A grounded system should decline.

| Question | Declined? | Answer (first 160 characters) |
|---|---|---|
| What is the capital of Australia? | Yes | There is not enough information provided to answer this question. |
| Who won the football World Cup in 2018? | Yes | There is not enough information. The provided documents contain details about the Northwind Research Lab’s hours, safety procedures, equipment booking, and acce |
