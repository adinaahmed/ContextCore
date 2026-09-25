from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
from app.db.database import get_db
from app.schemas.query import QueryRequest, QueryResponse, Citation
from app.schemas.structured_answer import StructuredAnswer
from app.core.hybrid_retrieval import hybrid_retriever
from app.core.reranker import reranker_service
from app.core.llm import llm_service
from app.core.auth import get_current_user
from app.core.memory import conversation_memory
from app.core.query_rewriter import query_rewriter
from app.core.fast_router import classify_question
from app.core.lcel_chain import run_structured_chain
from app.core.multi_query import multi_query_retrieve
from app.core.context_compression import context_compressor
from app.core.tool_calling import answer_with_tools
from app.core.latency_profiler import LatencyProfiler
from app.models.conversation import ConversationMessage, ConversationSession

router = APIRouter()


def _build_citations(reranked: list[dict]) -> list[Citation]:
    citations = []
    for c in reranked:
        meta = c.get("metadata", {}) or {}
        page = meta.get("page_number")
        citations.append(Citation(document_id=meta.get("document_id"), source=meta.get("source"),
            page_number=page if isinstance(page, int) and page >= 0 else None, chunk_index=meta.get("chunk_index")))
    return citations


def _build_where(document_ids: list[str] | None) -> dict | None:
    if not document_ids:
        return None
    if len(document_ids) == 1:
        return {"document_id": document_ids[0]}
    return {"document_id": {"$in": document_ids}}


def _retrieve(search_question: str, top_k: int, use_multi_query: bool, document_ids: list[str] | None):
    where = _build_where(document_ids)
    if use_multi_query and not where:
        return multi_query_retrieve(search_question, top_k=top_k)
    return hybrid_retriever.retrieve(search_question, top_k=top_k * 2, where=where)


@router.post("/query", response_model=QueryResponse)
def query_documents(request: QueryRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        classification = classify_question(request.question)

        if classification == "direct":
            answer = llm_service.generate_direct_answer(request.question)
            if request.session_id:
                conversation_memory.add_turn(db, request.session_id, request.question, answer, owner_id=current_user["user_id"])
            return QueryResponse(answer=answer, sources=[], citations=[], session_id=request.session_id, classification=classification)

        if classification == "calculation":
            tool_result = answer_with_tools(request.question)
            answer = tool_result.get("answer", "Calculation failed.")
            if request.session_id:
                conversation_memory.add_turn(db, request.session_id, request.question, answer, owner_id=current_user["user_id"])
            return QueryResponse(answer=answer, sources=[], citations=[], session_id=request.session_id, classification=classification)

        search_question = request.question
        if request.session_id:
            history = conversation_memory.get_history(db, request.session_id)
            search_question = query_rewriter.rewrite(request.question, history)

        use_multi_query = request.use_multi_query or (classification == "complex")
        use_compression = request.use_context_compression or (classification == "complex")

        candidates = _retrieve(search_question, request.top_k, use_multi_query, request.document_ids)

        if not candidates:
            answer = "I don't have enough information to answer that."
            if request.session_id:
                conversation_memory.add_turn(db, request.session_id, request.question, answer, owner_id=current_user["user_id"])
            return QueryResponse(answer=answer, sources=[], citations=[], session_id=request.session_id, classification=classification)

        reranked = reranker_service.rerank(search_question, candidates, top_k=request.top_k)
        retrieved_texts = [c["text"] for c in reranked]
        citations = _build_citations(reranked)

        if use_compression:
            retrieved_texts = context_compressor.compress(request.question, retrieved_texts)

        try:
            answer = llm_service.generate_answer(request.question, retrieved_texts)
        except Exception:
            answer = "Answer generation is temporarily unavailable. Here are the most relevant source chunks retrieved instead."

        if request.session_id:
            conversation_memory.add_turn(db, request.session_id, request.question, answer, owner_id=current_user["user_id"])

        return QueryResponse(answer=answer, sources=retrieved_texts, citations=citations, session_id=request.session_id, classification=classification)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.post("/query/structured", response_model=StructuredAnswer)
def query_structured(request: QueryRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        classification = classify_question(request.question)
        if classification == "direct":
            try:
                result = run_structured_chain(question=request.question, context="(No context retrieved.)")
            except Exception:
                result = {"answer": llm_service.generate_direct_answer(request.question), "confidence": 0.7, "used_retrieval": False}
            result["sources"] = []
            return StructuredAnswer(**result)

        candidates = _retrieve(request.question, request.top_k, False, request.document_ids)
        if not candidates:
            return StructuredAnswer(answer="I don't have enough information to answer that.", confidence=0.0, sources=[], used_retrieval=False)

        reranked = reranker_service.rerank(request.question, candidates, top_k=request.top_k)
        retrieved_texts = [c["text"] for c in reranked]
        try:
            result = run_structured_chain(question=request.question, context="\n\n".join(retrieved_texts))
        except Exception:
            result = llm_service.generate_structured_answer(request.question, retrieved_texts)
        result["sources"] = retrieved_texts
        return StructuredAnswer(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Structured query failed: {str(e)}")


@router.post("/query/tools")
def query_with_tools(request: QueryRequest, current_user: dict = Depends(get_current_user)):
    return answer_with_tools(request.question)


@router.post("/query/trace")
def query_with_trace(request: QueryRequest, current_user: dict = Depends(get_current_user)):
    profiler = LatencyProfiler()
    trace = {"question": request.question}
    with profiler.measure("routing"):
        classification = classify_question(request.question)
    trace["classification"] = classification
    if classification == "direct":
        with profiler.measure("generation"):
            answer = llm_service.generate_direct_answer(request.question)
        trace.update({"answer": answer, **profiler.get_report()})
        return trace
    if classification == "calculation":
        with profiler.measure("tool_calling"):
            tool_result = answer_with_tools(request.question)
        trace.update({"answer": tool_result.get("answer", ""), **profiler.get_report()})
        return trace
    with profiler.measure("retrieval"):
        candidates = _retrieve(request.question, request.top_k, False, request.document_ids)
    trace["fused_candidates"] = len(candidates)
    trace["top_candidate_scores"] = [round(c["score"], 4) for c in candidates[:5]]
    if not candidates:
        trace.update({"answer": "I don't have enough information to answer that.", "reranked_count": 0, **profiler.get_report()})
        return trace
    with profiler.measure("reranking"):
        reranked = reranker_service.rerank(request.question, candidates, top_k=request.top_k)
    trace["reranked_count"] = len(reranked)
    retrieved_texts = [c["text"] for c in reranked]
    trace["context_chars"] = sum(len(t) for t in retrieved_texts)
    with profiler.measure("generation"):
        try:
            answer = llm_service.generate_answer(request.question, retrieved_texts)
        except Exception:
            answer = "Answer generation is temporarily unavailable."
    trace["answer"] = answer
    trace["citations"] = _build_citations(reranked)
    trace.update(profiler.get_report())
    return trace


@router.get("/query/sessions")
def list_sessions(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return conversation_memory.list_sessions(db, current_user["user_id"])


@router.get("/query/history/{session_id}")
def get_session_history(session_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    owner_id = conversation_memory.get_owner(db, session_id)
    if owner_id is not None and owner_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You do not have access to this session")
    history = conversation_memory.get_history(db, session_id)
    summary = conversation_memory.get_summary(db, session_id)
    return {"session_id": session_id, "turns": history, "summary": summary}


@router.delete("/query/sessions/{session_id}")
def delete_session(session_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    owner_id = conversation_memory.get_owner(db, session_id)
    if owner_id is not None and owner_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You do not have access to this session")
    conversation_memory.clear_session(db, session_id)
    return {"status": "deleted", "session_id": session_id}


@router.get("/query/usage")
def get_usage(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    count = (
        db.query(func.count(ConversationMessage.id))
        .join(ConversationSession, ConversationMessage.session_id == ConversationSession.session_id)
        .filter(ConversationSession.owner_id == current_user["user_id"], ConversationMessage.created_at >= today_start)
        .scalar()
    )
    return {"questions_today": count or 0}
