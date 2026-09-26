"""
Benchmark script covering two items from the development plan:

1. Chunking strategy comparison: chunks the same document with each strategy
   (recursive, semantic, contextual) and measures retrieval quality with the
   real hybrid retrieval + reranking pipeline. A question counts as answered
   when a retrieved chunk contains its known answer phrase.
   Metrics: Hit@1, Hit@3, Hit@5 and MRR, with and without the reranker.

2. Latency profiling: runs sample questions through /query/trace and reports
   the time spent in each pipeline stage, plus a grounding check on
   out-of-scope questions (the system should not invent answers).

Usage (from the project root, with the virtual environment active):
    python scripts/benchmark.py                   # both benchmarks
    python scripts/benchmark.py --chunking        # chunking comparison only
    python scripts/benchmark.py --latency         # latency profiling only
    python scripts/benchmark.py --skip-contextual # skip the LLM-heavy strategy

Results are printed and saved to docs/benchmark_results.md
"""
import argparse
import os
import re
import statistics
import sys
import time
import uuid
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)  # so the .env file is found

import numpy as np
from rank_bm25 import BM25Okapi

from app.config import settings
from app.core.chunking import chunking_service
from app.core.embeddings import embedding_service
from app.core.reranker import reranker_service


# A fictional handbook, so the LLM cannot answer from general knowledge.
DOCUMENT = """Northwind Research Lab Handbook

SECTION: Opening Hours and Access
The Northwind Research Lab is open from 7:30 am to 9:00 pm on weekdays and from 10:00 am to 4:00 pm on Saturdays. The lab is closed on Sundays and public holidays. After-hours access requires a signed approval form from the lab director, Dr. Amara Okafor, submitted at least 48 hours in advance. Access cards are issued by the front office on the ground floor and must be renewed every six months. Lost cards should be reported immediately; a replacement fee of 15 dollars applies.

SECTION: Safety
All new members must complete the chemical safety course within their first two weeks. The course is offered every Tuesday at 2:00 pm in room B-104. Protective goggles and lab coats are mandatory in wet labs at all times. The emergency eyewash station is located next to the north staircase, and fire extinguishers are placed at both ends of each corridor. Any accident, however minor, must be logged in the incident register within 24 hours.

SECTION: Equipment Booking
The confocal microscope and the mass spectrometer must be booked through the online scheduler. Each booking slot lasts two hours, and a single user may book at most three slots per week. Cancellations made less than 12 hours before the slot count as a used booking. The scheduler opens new slots every Friday at noon for the following week. Training on the mass spectrometer is required before the first booking and is provided by the instrument manager, Leo Brandt.

SECTION: Data Storage
Research data must be stored on the lab's central server, not on personal laptops. Each project receives 2 terabytes of storage by default, which can be increased to 5 terabytes on request. The server is backed up every night at 1:00 am, and backups are retained for 90 days. Sensitive participant data must be encrypted and stored in the restricted folder named SECURE-DATA, which only approved staff can open.

SECTION: Publication Policy
Before submitting a paper, authors must share the final draft with all co-authors at least ten working days in advance. The lab director must approve any publication that uses shared lab equipment. Preprints may be posted to public archives after internal approval. All publications must acknowledge the Horizon Science Grant, reference number HSG-2291, which funds most of the lab's work.

SECTION: Travel Funding
Each researcher may apply for conference travel funding once per academic year. The maximum reimbursement is 1,200 dollars for domestic conferences and 2,500 dollars for international ones. Applications must be submitted at least six weeks before travel. Receipts must be submitted within 30 days of returning, otherwise the reimbursement request is rejected. Priority is given to researchers presenting their own work.

SECTION: Onboarding
New members receive a welcome pack containing their access card, a lab notebook and the handbook. During the first week, each newcomer is paired with a mentor from the same research group. The mentor meets the newcomer at least twice a week for the first month. A short onboarding survey is sent after 30 days to collect feedback on the process.

SECTION: IT Support
Technical problems should be reported through the IT help desk portal or by emailing it-help@northwind-lab.example. The help desk responds within four working hours. Software licences for statistics packages are managed centrally; requests are approved within three working days. Passwords must be changed every 90 days and must contain at least twelve characters.
"""

# (question, phrase that must appear in a retrieved chunk for it to count as found)
QUESTIONS = [
    ("What time does the lab open on Saturdays?", "10:00 am to 4:00 pm on Saturdays"),
    ("Who approves after-hours access to the lab?", "Dr. Amara Okafor"),
    ("When is the chemical safety course held?", "every Tuesday at 2:00 pm"),
    ("Where is the emergency eyewash station?", "next to the north staircase"),
    ("How many equipment booking slots can one person book per week?", "at most three slots per week"),
    ("Who provides training on the mass spectrometer?", "Leo Brandt"),
    ("How long are server backups kept?", "retained for 90 days"),
    ("Which grant must publications acknowledge?", "HSG-2291"),
    ("What is the maximum travel reimbursement for international conferences?", "2,500 dollars"),
    ("How often does a mentor meet a new member?", "twice a week"),
    ("How quickly does the IT help desk respond?", "within four working hours"),
    ("How many characters must a password contain?", "at least twelve characters"),
]

# Questions the handbook cannot answer: a grounded system should say so
OUT_OF_SCOPE = [
    "What is the capital of Australia?",
    "Who won the football World Cup in 2018?",
]
REFUSAL_HINTS = ("enough information", "not mentioned", "does not", "doesn't", "no information",
                 "not provided", "cannot", "can't", "not contain", "not specified")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _minmax(x: np.ndarray) -> np.ndarray:
    rng = x.max() - x.min()
    return (x - x.min()) / rng if rng > 0 else np.ones_like(x)


def _rank_of_key(texts: list[str], key: str):
    key = _norm(key)
    for i, t in enumerate(texts, start=1):
        if key in _norm(t):
            return i
    return None


def _hit(ranks, k):
    return sum(1 for r in ranks if r and r <= k) / len(ranks)


def _mrr(ranks):
    return sum(1 / r for r in ranks if r) / len(ranks)


def _fmt(value, digits=1):
    return "n/a" if value is None else f"{value:.{digits}f}"


# ---------------- 1. Chunking strategy comparison ----------------

def run_chunking(strategies: list[str], top_k: int = 5) -> list[dict]:
    w_dense = getattr(settings, "dense_weight", 0.6)
    w_sparse = getattr(settings, "sparse_weight", 0.4)
    results = []

    for strategy in strategies:
        print(f"  Chunking with '{strategy}'...")
        t0 = time.perf_counter()
        chunks = chunking_service.chunk_text(DOCUMENT, strategy=strategy)
        chunk_seconds = time.perf_counter() - t0

        t1 = time.perf_counter()
        embeddings = np.array(embedding_service.embed_batch(chunks), dtype=float)
        embed_seconds = time.perf_counter() - t1
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        bm25 = BM25Okapi([_tokens(c) for c in chunks])

        ranks_hybrid, ranks_reranked = [], []
        for question, key in QUESTIONS:
            q = np.array(embedding_service.embed_text(question), dtype=float)
            q = q / np.linalg.norm(q)
            dense = embeddings @ q
            sparse = np.array(bm25.get_scores(_tokens(question)), dtype=float)
            combined = w_dense * _minmax(dense) + w_sparse * _minmax(sparse)
            order = list(np.argsort(-combined))

            hybrid_texts = [chunks[i] for i in order[:top_k]]
            candidates = [
                {"chunk_id": str(i), "text": chunks[i], "score": float(combined[i]), "metadata": {}}
                for i in order[: top_k * 2]
            ]
            reranked_texts = [c["text"] for c in reranker_service.rerank(question, candidates, top_k=top_k)]

            ranks_hybrid.append(_rank_of_key(hybrid_texts, key))
            ranks_reranked.append(_rank_of_key(reranked_texts, key))

        results.append({
            "strategy": strategy,
            "chunks": len(chunks),
            "avg_len": statistics.mean(len(c) for c in chunks),
            "chunk_s": chunk_seconds,
            "embed_s": embed_seconds,
            "hit1": _hit(ranks_reranked, 1),
            "hit3": _hit(ranks_reranked, 3),
            "hit5": _hit(ranks_reranked, 5),
            "mrr": _mrr(ranks_reranked),
            "mrr_no_rerank": _mrr(ranks_hybrid),
        })
    return results


# ---------------- 2. Latency profiling ----------------

def run_latency(n_questions: int = 10):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.llm import llm_service

    client = TestClient(app)
    email = f"bench_{uuid.uuid4().hex[:8]}@example.com"
    password = "benchpass123"
    client.post("/auth/register", json={"email": email, "password": password})
    login = client.post("/auth/login", json={"email": email, "password": password})
    if login.status_code != 200:
        raise RuntimeError(f"Login failed: {login.text}")
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    doc_id = f"bench_doc_{uuid.uuid4().hex[:6]}"
    ingest = client.post("/ingest", headers=headers, json={
        "document_id": doc_id, "source": "benchmark", "text": DOCUMENT, "strategy": "recursive",
    })
    if ingest.status_code != 200:
        raise RuntimeError(f"Ingest failed: {ingest.text}")

    rows, grounding = [], []
    try:
        for question, _ in QUESTIONS[:n_questions]:
            print(f"  Tracing: {question}")
            t0 = time.perf_counter()
            r = client.post("/query/trace", headers=headers, json={"question": question, "top_k": 5})
            wall_ms = (time.perf_counter() - t0) * 1000
            data = r.json()
            stages = data.get("stages_ms", {}) or {}
            rows.append({
                "question": question,
                "classification": data.get("classification"),
                "routing": stages.get("routing"),
                "retrieval": stages.get("retrieval"),
                "reranking": stages.get("reranking"),
                "generation": stages.get("generation"),
                "total": data.get("total_ms") or wall_ms,
                "provider": getattr(llm_service, "last_provider_used", "unknown"),
            })

        for question in OUT_OF_SCOPE:
            print(f"  Grounding check: {question}")
            r = client.post("/query", headers=headers, json={"question": question})
            answer = r.json().get("answer", "")
            grounding.append({
                "question": question,
                "answer": answer.replace("\n", " ")[:160],
                "refused": any(h in answer.lower() for h in REFUSAL_HINTS),
            })
    finally:
        client.delete(f"/documents/{doc_id}", headers=headers)

    return rows, grounding


# ---------------- Report ----------------

def build_report(chunking_results, latency_rows, grounding) -> str:
    lines = [
        "# Benchmark Results",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"Embedding model: {embedding_service.provider_name}  ",
        f"Chunk size / overlap: {settings.chunk_size} / {settings.chunk_overlap}  ",
        f"Hybrid weights (dense / sparse): {getattr(settings, 'dense_weight', 0.6)} / {getattr(settings, 'sparse_weight', 0.4)}",
        "",
    ]

    if chunking_results:
        lines += [
            "## 1. Chunking Strategy Comparison",
            "",
            f"Test document: a fictional lab handbook ({len(DOCUMENT):,} characters, 8 sections), "
            f"{len(QUESTIONS)} questions with known answer phrases. Retrieval uses the same hybrid "
            "(dense + BM25) scoring and cross-encoder reranking as the application.",
            "",
            "| Strategy | Chunks | Avg chunk length | Hit@1 | Hit@3 | Hit@5 | MRR | MRR without reranker | Chunking time (s) | Embedding time (s) |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in chunking_results:
            lines.append(
                f"| {r['strategy']} | {r['chunks']} | {r['avg_len']:.0f} | {r['hit1']:.0%} | {r['hit3']:.0%} | "
                f"{r['hit5']:.0%} | {r['mrr']:.3f} | {r['mrr_no_rerank']:.3f} | {r['chunk_s']:.2f} | {r['embed_s']:.2f} |"
            )
        best = max(chunking_results, key=lambda r: (r["mrr"], -r["chunk_s"]))
        lines += ["", f"Best MRR: **{best['strategy']}** ({best['mrr']:.3f}).", ""]

    if latency_rows:
        def mean_of(key):
            vals = [r[key] for r in latency_rows if isinstance(r[key], (int, float))]
            return statistics.mean(vals) if vals else None

        totals = sorted(r["total"] for r in latency_rows if isinstance(r["total"], (int, float)))
        p95 = totals[max(0, int(round(0.95 * len(totals))) - 1)] if totals else None
        stage_means = {s: mean_of(s) for s in ("routing", "retrieval", "reranking", "generation")}
        known = {s: v for s, v in stage_means.items() if v is not None}
        slowest = max(known, key=known.get) if known else "n/a"
        providers = sorted({r["provider"] for r in latency_rows})

        lines += [
            "## 2. Latency Profiling",
            "",
            f"{len(latency_rows)} questions run through `/query/trace`. LLM provider(s) used: {', '.join(providers)}.",
            "",
            "| Question | Route | Routing (ms) | Retrieval (ms) | Reranking (ms) | Generation (ms) | Total (ms) |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in latency_rows:
            lines.append(
                f"| {r['question']} | {r['classification']} | {_fmt(r['routing'])} | {_fmt(r['retrieval'])} | "
                f"{_fmt(r['reranking'])} | {_fmt(r['generation'])} | {_fmt(r['total'])} |"
            )
        lines += [
            "",
            "| Summary | Value |",
            "|---|---|",
            f"| Mean routing (ms) | {_fmt(stage_means['routing'])} |",
            f"| Mean retrieval (ms) | {_fmt(stage_means['retrieval'])} |",
            f"| Mean reranking (ms) | {_fmt(stage_means['reranking'])} |",
            f"| Mean generation (ms) | {_fmt(stage_means['generation'])} |",
            f"| Median total (ms) | {_fmt(statistics.median(totals) if totals else None)} |",
            f"| 95th percentile total (ms) | {_fmt(p95)} |",
            f"| Slowest stage (bottleneck) | {slowest} |",
            "",
        ]

    if grounding:
        lines += [
            "## 3. Grounding Check (Out-of-Scope Questions)",
            "",
            "These questions cannot be answered from the uploaded document. A grounded system should decline.",
            "",
            "| Question | Declined? | Answer (first 160 characters) |",
            "|---|---|---|",
        ]
        for g in grounding:
            lines.append(f"| {g['question']} | {'Yes' if g['refused'] else 'No, review'} | {g['answer']} |")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="ContextCore benchmark")
    parser.add_argument("--chunking", action="store_true", help="run only the chunking comparison")
    parser.add_argument("--latency", action="store_true", help="run only latency profiling")
    parser.add_argument("--skip-contextual", action="store_true", help="skip the LLM-heavy contextual strategy")
    args = parser.parse_args()
    run_both = not args.chunking and not args.latency

    chunking_results, latency_rows, grounding = [], [], []

    if args.chunking or run_both:
        print("\n[1/2] Chunking strategy comparison")
        strategies = ["recursive", "semantic"] + ([] if args.skip_contextual else ["contextual"])
        chunking_results = run_chunking(strategies)

    if args.latency or run_both:
        print("\n[2/2] Latency profiling")
        latency_rows, grounding = run_latency()

    report = build_report(chunking_results, latency_rows, grounding)
    os.makedirs("docs", exist_ok=True)
    with open(os.path.join("docs", "benchmark_results.md"), "w", encoding="utf-8") as f:
        f.write(report)

    print("\n" + report)
    print("\nSaved to docs/benchmark_results.md")


if __name__ == "__main__":
    main()
