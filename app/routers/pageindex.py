"""
PageIndex Router
=================
Exposes document intelligence endpoints under /pageindex prefix.
All routes require a valid PlacementCoach JWT (get_current_user).

Endpoints:
  POST   /pageindex/upload           — PDF → PageIndex tree
  GET    /pageindex/documents        — List indexed documents
  GET    /pageindex/tree/{id}        — Inspect tree structure
  DELETE /pageindex/{id}             — Remove document
  POST   /pageindex/chat             — LLM reasoning traversal query
  POST   /pageindex/chat/stream      — SSE streaming answer
  POST   /pageindex/chat/multi       — Multi-doc comparative query
  GET    /pageindex/explain/{id}     — Dry-run traversal trace (debugging)
"""
import uuid
import time
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.dependencies import get_current_user

from app.pageindex.models.tree import ChatRequest, MultiChatRequest, ChatResponse
from app.pageindex.services.pdf_parser import extract_pages
from app.pageindex.services.tree_builder import build_tree
from app.pageindex.services.tree_store import (
    save_tree, load_tree, document_exists, list_documents, _node_to_dict
)
from app.pageindex.services.faiss_service import build_faiss_index
from app.pageindex.services.cache_service import cache_invalidate
from app.pageindex.services.chat_orchestrator import (
    answer_query, stream_query, multi_document_query
)

router = APIRouter(prefix="/pageindex", tags=["pageindex"])

ALLOWED_TYPES = {"application/pdf", "application/octet-stream"}
MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB


# ── Document management ───────────────────────────────────────────────────────

@router.post("/upload", status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload a PDF and build its PageIndex tree.

    The tree is built synchronously (5-30s for large docs).
    FAISS vector index is built in the background.

    Returns: { document_id, filename, total_pages, total_nodes, created_at }
    """
    if file.content_type not in ALLOWED_TYPES and not (file.filename or "").endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(status_code=400, detail=f"File too large. Max {MAX_PDF_BYTES // (1024*1024)} MB.")

    document_id = str(uuid.uuid4())
    filename = file.filename or "document.pdf"
    start = time.time()

    # Parse PDF → pages
    pages = extract_pages(pdf_bytes)

    # Build PageIndex tree (LLM call)
    index = await build_tree(pages, document_id, filename)

    # Persist tree
    save_tree(index)

    # Build FAISS index asynchronously (non-blocking)
    background_tasks.add_task(build_faiss_index, document_id, index.tree)

    # Persist original PDF
    uploads_dir = Path(settings.PAGEINDEX_DATA_DIR) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    with open(uploads_dir / f"{document_id}.pdf", "wb") as f:
        f.write(pdf_bytes)

    return {
        "document_id": document_id,
        "filename": filename,
        "total_pages": index.total_pages,
        "total_nodes": index.total_nodes,
        "created_at": index.created_at.isoformat(),
        "index_time_seconds": round(time.time() - start, 2),
        "message": "Document indexed. FAISS index building in background.",
    }


@router.get("/documents")
async def list_all_documents(current_user: dict = Depends(get_current_user)):
    """List all indexed documents with metadata."""
    docs = list_documents()
    return {"documents": docs, "count": len(docs)}


@router.get("/tree/{document_id}")
async def get_tree(document_id: str, current_user: dict = Depends(get_current_user)):
    """Return the full hierarchical PageIndex tree for a document."""
    index = load_tree(document_id)
    if not index:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")
    return {
        "document_id": index.document_id,
        "filename": index.filename,
        "total_pages": index.total_pages,
        "total_nodes": index.total_nodes,
        "created_at": index.created_at.isoformat(),
        "tree": _node_to_dict(index.tree),
    }


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove a document's tree, FAISS index, and cache entries."""
    import os
    if not document_exists(document_id):
        raise HTTPException(status_code=404, detail="Document not found.")

    tree_path = Path(settings.PAGEINDEX_DATA_DIR) / "trees" / f"{document_id}.json"
    if tree_path.exists():
        os.remove(tree_path)

    for ext in [".faiss", ".faiss.npy", ".meta.pkl"]:
        fp = Path(settings.PAGEINDEX_DATA_DIR) / "faiss_indexes" / f"{document_id}{ext}"
        if fp.exists():
            os.remove(fp)

    cache_invalidate(document_id)
    return None


# ── Chat / query ──────────────────────────────────────────────────────────────

def _get_index_or_404(document_id: str):
    index = load_tree(document_id)
    if not index:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{document_id}' not found. Upload it first via POST /pageindex/upload.",
        )
    return index


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Query a document using PageIndex LLM reasoning traversal.

    The system navigates the document tree using reasoning (no keyword matching),
    falls back to FAISS vector search if confidence is low, and returns a grounded
    answer with a full explainability trace.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    if len(request.query) > 2000:
        raise HTTPException(status_code=400, detail="Query too long (max 2000 chars).")

    index = _get_index_or_404(request.document_id)

    try:
        return await answer_query(index, request.query, request.explainability)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Stream a query response via Server-Sent Events (SSE).

    Events:
      {"event": "status", "message": "..."}          — progress
      {"event": "traversal_complete", "path": "..."}  — traversal done
      {"event": "answer_start"}                        — streaming begins
      {"event": "token", "text": "..."}               — answer token
      {"event": "done", "sources": [...], ...}         — final metadata
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    index = _get_index_or_404(request.document_id)

    async def event_generator():
        try:
            async for chunk in stream_query(index, request.query):
                yield chunk
        except Exception as e:
            yield f"data: {{\"event\": \"error\", \"message\": \"{str(e)}\"}}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/multi")
async def multi_chat(
    request: MultiChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Query multiple documents and synthesise a comparative answer.
    Useful for comparing resumes: "Which candidate has stronger ML experience?"
    Max 5 documents per request.
    """
    if not request.documents:
        raise HTTPException(status_code=400, detail="At least one document_id required.")
    if len(request.documents) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 documents per multi-chat.")
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    indexes = []
    for doc_id in request.documents:
        idx = load_tree(doc_id)
        if not idx:
            raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
        indexes.append(idx)

    try:
        return await multi_document_query(indexes, request.query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Multi-chat failed: {str(e)}")


@router.get("/explain/{document_id}")
async def explain_traversal(
    document_id: str,
    query: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Dry-run: explain how the traversal engine would navigate the tree
    for a given query, WITHOUT generating a final answer.
    Useful for debugging and demos.
    """
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query required.")

    index = _get_index_or_404(document_id)

    from app.pageindex.services.reasoning_engine import traverse_and_answer
    from app.pageindex.services.tree_store import find_node_by_id

    (
        collected_ids,
        reasoning_steps,
        reasoning_path,
        confidence,
        method,
    ) = await traverse_and_answer(index.tree, query, document_id)

    source_titles = []
    for nid in collected_ids:
        node = find_node_by_id(index.tree, nid)
        if node:
            source_titles.append(node.title)

    return {
        "document_id": document_id,
        "query": query,
        "reasoning_path": reasoning_path,
        "reasoning_steps": [s.model_dump() for s in reasoning_steps],
        "collected_nodes": source_titles,
        "traversal_confidence": round(confidence, 3),
        "would_trigger_fallback": confidence < settings.CONFIDENCE_THRESHOLD,
        "note": "Dry-run explanation. No answer was generated.",
    }
