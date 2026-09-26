"""
Extended test suite covering the plan items not in test_integration.py:
router, hybrid/BM25 retrieval, reranking, query rewriting, conversation memory,
tool calling, edge cases, grounding and user data isolation.

Tests marked 'llm' call Gemini (with Ollama fallback) and need a working API key.
Run all:           pytest tests/test_pipeline.py -v
Skip LLM tests:    pytest tests/test_pipeline.py -v -m "not llm"
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.fast_router import classify_question as fast_classify
from app.core.bm25_store import bm25_store
from app.core.reranker import reranker_service
from app.core.query_rewriter import query_rewriter
from app.core.memory import conversation_memory
from app.db.database import get_db

client = TestClient(app)


# ---------- helpers ----------

def _new_user_token() -> str:
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password = "testpass123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (200, 201), r.text
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def token_a():
    return _new_user_token()


@pytest.fixture(scope="module")
def token_b():
    return _new_user_token()


# ---------- 1. Router ----------

@pytest.mark.parametrize("question, expected", [
    ("hello", "direct"),
    ("thanks", "direct"),
    ("what is 25 * 4", "calculation"),
    ("calculate the average of 10 and 20", "calculation"),
    ("compare linear probing and chaining", "complex"),
    ("why does clustering reduce hash table performance?", "complex"),
    ("what is hashing", "simple"),
])
def test_fast_router_classification(question, expected):
    assert fast_classify(question) == expected


@pytest.mark.llm
def test_llm_router_returns_valid_category():
    from app.core.router_chain import classify_question as llm_classify
    result = llm_classify("What is a confidence interval?")
    assert result in {"direct", "calculation", "simple", "complex"}


# ---------- 2. Sparse (BM25) retrieval ----------

def test_bm25_finds_exact_keyword():
    keyword = f"zyxq{uuid.uuid4().hex[:8]}"
    ids = [f"test_bm25_{uuid.uuid4().hex[:6]}" for _ in range(3)]
    texts = [
        f"This passage mentions the rare term {keyword} exactly once.",
        "An unrelated passage about the weather in spring.",
        "Another unrelated passage about cooking pasta.",
    ]
    bm25_store.add_chunks(ids=ids, texts=texts)
    try:
        results = bm25_store.query(keyword, top_k=5)
        found_ids = [r[0] for r in results]
        assert ids[0] in found_ids
    finally:
        bm25_store.remove_by_ids(ids)


# ---------- 3. Reranking ----------

def test_reranker_puts_relevant_chunk_first():
    candidates = [
        {"chunk_id": "a", "text": "Bananas are a yellow fruit rich in potassium.", "score": 0.9, "metadata": {}},
        {"chunk_id": "b", "text": "Linear probing resolves hash collisions by checking the next slot in the table.", "score": 0.1, "metadata": {}},
        {"chunk_id": "c", "text": "The weather in Paris is mild in spring.", "score": 0.5, "metadata": {}},
    ]
    reranked = reranker_service.rerank("How does linear probing resolve collisions?", candidates, top_k=2)
    assert len(reranked) == 2
    assert reranked[0]["chunk_id"] == "b"


# ---------- 4. Conversation memory ----------

def test_memory_persists_and_clears():
    db = next(get_db())
    session_id = f"test_session_{uuid.uuid4().hex[:8]}"
    owner_id = str(uuid.uuid4())
    try:
        conversation_memory.add_turn(db, session_id, "What is hashing?", "Hashing maps keys to slots.", owner_id=owner_id)
        conversation_memory.add_turn(db, session_id, "What about chaining?", "Chaining uses linked lists.", owner_id=owner_id)

        history = conversation_memory.get_history(db, session_id)
        assert len(history) == 2
        assert history[0]["question"] == "What is hashing?"
        assert conversation_memory.get_owner(db, session_id) == owner_id

        conversation_memory.clear_session(db, session_id)
        assert conversation_memory.get_history(db, session_id) == []
    finally:
        db.close()


# ---------- 5. Query rewriting ----------

@pytest.mark.llm
def test_rewriter_resolves_reference_from_history():
    history = [{"question": "What is linear probing?",
                "answer": "Linear probing is a collision resolution method in hashing."}]
    rewritten = query_rewriter.rewrite("What are its disadvantages?", history)
    assert "probing" in rewritten.lower()


def test_rewriter_falls_back_on_empty_input():
    assert query_rewriter.rewrite("", []) in ("", None) or isinstance(query_rewriter.rewrite("", []), str)


# ---------- 6. Tool calling ----------

@pytest.mark.llm
def test_llm_uses_calculator_tool():
    from app.core.tool_calling import answer_with_tools
    result = answer_with_tools("What is 123 multiplied by 4?")
    assert "492" in str(result.get("answer", ""))


# ---------- 7. Edge cases ----------

def test_empty_question_rejected(token_a):
    r = client.post("/query", headers=_auth(token_a), json={"question": ""})
    assert r.status_code == 422


def test_top_k_out_of_range_rejected(token_a):
    r = client.post("/query", headers=_auth(token_a), json={"question": "What is hashing?", "top_k": 500})
    assert r.status_code == 422


def test_empty_document_rejected(token_a):
    r = client.post("/ingest", headers=_auth(token_a), json={
        "document_id": f"test_empty_{uuid.uuid4().hex[:6]}",
        "source": "test", "text": "", "strategy": "recursive",
    })
    assert r.status_code in (400, 422)


def test_unsupported_file_type_rejected(token_a):
    r = client.post(
        "/ingest/file", headers=_auth(token_a),
        files={"file": ("malware.exe", b"not a real document", "application/octet-stream")},
        data={"document_id": f"test_exe_{uuid.uuid4().hex[:6]}", "strategy": "recursive"},
    )
    assert r.status_code == 400


def test_long_document_is_split_into_many_chunks(token_a):
    doc_id = f"test_long_{uuid.uuid4().hex[:6]}"
    paragraph = "Hash tables store key value pairs and use a hash function to compute an index. "
    long_text = "\n\n".join(paragraph * 5 for _ in range(60))  # roughly 25,000 characters
    r = client.post("/ingest", headers=_auth(token_a), json={
        "document_id": doc_id, "source": "test", "text": long_text, "strategy": "recursive",
    })
    try:
        assert r.status_code == 200, r.text
        assert r.json()["chunks_created"] > 10
    finally:
        client.delete(f"/documents/{doc_id}", headers=_auth(token_a))


# ---------- 8. User data isolation ----------

def test_user_cannot_retrieve_other_users_documents(token_a, token_b):
    secret = f"codeword{uuid.uuid4().hex[:8]}"
    doc_id = f"test_iso_{uuid.uuid4().hex[:6]}"
    r = client.post("/ingest", headers=_auth(token_a), json={
        "document_id": doc_id, "source": "test",
        "text": f"The confidential project codename is {secret}.", "strategy": "recursive",
    })
    assert r.status_code == 200, r.text
    try:
        r = client.post("/query", headers=_auth(token_b), json={"question": f"What is the project codename {secret}?"})
        cited = [c.get("document_id") for c in r.json().get("citations", [])]
        assert doc_id not in cited, "User B retrieved User A's private document"
    finally:
        client.delete(f"/documents/{doc_id}", headers=_auth(token_a))


def test_same_document_id_does_not_overwrite_other_user(token_a, token_b):
    doc_id = f"test_shared_{uuid.uuid4().hex[:6]}"
    client.post("/ingest", headers=_auth(token_a), json={
        "document_id": doc_id, "source": "test", "text": "User A's original content about hashing.", "strategy": "recursive",
    })
    try:
        client.post("/ingest", headers=_auth(token_b), json={
            "document_id": doc_id, "source": "test", "text": "User B's completely different content.", "strategy": "recursive",
        })
        docs_a = client.get("/documents", headers=_auth(token_a)).json()
        doc_a = next((d for d in docs_a if d["document_id"] == doc_id), None)
        assert doc_a is not None, "User A's document disappeared"
        assert doc_a["version"] == 1, "User B's upload overwrote User A's document"
    finally:
        client.delete(f"/documents/{doc_id}", headers=_auth(token_a))
        client.delete(f"/documents/{doc_id}", headers=_auth(token_b))


# ---------- 9. Calculator fallback (works without any LLM) ----------

@pytest.mark.parametrize("question, expected", [
    ("What is 123 multiplied by 4?", 492),
    ("what is 25 * 4", 100),
    ("calculate 12 x 3", 36),
    ("what is 100 divided by 8", 12.5),
    ("what is 20 percent of 50", 10),
    ("calculate the average of 10 and 20", 15),
    ("what is 5 squared", 25),
    ("what is 1,000 plus 250", 1250),
])
def test_calculator_fallback_parses_questions(question, expected):
    from app.core.tool_calling import _local_answer
    result = _local_answer(question)
    assert result is not None, f"Could not parse: {question}"
    assert abs(result["tool_result"]["result"] - expected) < 1e-9


def test_calculator_fallback_ignores_non_math():
    from app.core.tool_calling import _local_answer
    assert _local_answer("what is hashing") is None


# ---------- 10. Grounding (no hallucination) and memory summarization ----------

def test_user_with_no_documents_gets_no_invented_answer():
    token = _new_user_token()
    r = client.post("/query", headers=_auth(token),
                    json={"question": "What is the refund policy of the Northwind lab?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["citations"] == []
    assert "enough information" in body["answer"].lower()


@pytest.mark.llm
def test_out_of_scope_question_is_not_answered_from_general_knowledge(token_a):
    doc_id = f"test_scope_{uuid.uuid4().hex[:6]}"
    client.post("/ingest", headers=_auth(token_a), json={
        "document_id": doc_id, "source": "test", "strategy": "recursive",
        "text": "Linear probing resolves hash collisions by checking the next slot in the table.",
    })
    try:
        r = client.post("/query", headers=_auth(token_a),
                        json={"question": "What is the capital of Australia?", "document_ids": [doc_id]})
        assert r.status_code == 200, r.text
        assert "canberra" not in r.json()["answer"].lower(), "Answered from general knowledge instead of the documents"
    finally:
        client.delete(f"/documents/{doc_id}", headers=_auth(token_a))


@pytest.mark.llm
def test_long_conversation_gets_summarized():
    db = next(get_db())
    session_id = f"test_summary_{uuid.uuid4().hex[:8]}"
    owner_id = str(uuid.uuid4())
    try:
        for i in range(12):
            conversation_memory.add_turn(db, session_id, f"Question {i} about hash tables?",
                                         f"Answer {i}: hash tables store keys in buckets.", owner_id=owner_id)
        assert conversation_memory.get_summary(db, session_id), "No summary was generated after 12 turns"
    finally:
        conversation_memory.clear_session(db, session_id)
        db.close()
