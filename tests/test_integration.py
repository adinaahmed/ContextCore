import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

TEST_EMAIL = "integration_test_user@example.com"
TEST_PASSWORD = "IntegrationTest123"


@pytest.fixture(scope="module")
def auth_token():
    """Registers a test user (if not already registered) and returns a valid JWT."""
    client.post("/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    response = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_and_login(auth_token):
    assert auth_token is not None
    assert len(auth_token) > 10


def test_ingest_requires_auth():
    response = client.post("/ingest", json={
        "text": "test", "document_id": "no_auth_test", "source": "test", "strategy": "recursive"
    })
    assert response.status_code == 401


def test_ingest_with_auth(auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.post("/ingest", json={
        "text": "Integration testing verifies the whole system works together correctly.",
        "document_id": "integration_test_doc",
        "source": "pytest",
        "strategy": "recursive",
    }, headers=headers)
    assert response.status_code in (200, 400)  # 400 if document_id already exists from a prior run


def test_query_requires_auth():
    response = client.post("/query", json={"question": "test", "top_k": 3})
    assert response.status_code == 401


def test_query_retrieval_pipeline(auth_token):
    """Tests retrieval + reranking work WITHOUT requiring a live Gemini call to succeed,
    since generation failure is handled gracefully by the fallback."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.post("/query", json={
        "question": "What does integration testing verify?", "top_k": 3
    }, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "sources" in data


def test_calculator_tool_direct():
    """Tests the calculator's safety sandbox directly, no API/Gemini involved."""
    from app.core.tools.calculator import calculator_tool

    result = calculator_tool.calculate("10 + 5")
    assert result["success"] is True
    assert result["result"] == 15

    injection_attempt = calculator_tool.calculate('__import__("os").system("echo hacked")')
    assert injection_attempt["success"] is False


def test_context_compression_direct():
    """Tests compression logic directly, no Gemini involved."""
    from app.core.context_compression import context_compressor

    chunks = ["BM25 handles keywords. PostgreSQL handles storage. FastAPI handles routing."]
    compressed = context_compressor.compress("What handles keywords?", chunks)
    assert len(compressed) == 1
    assert "BM25" in compressed[0]