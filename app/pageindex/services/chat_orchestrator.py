"""
Chat Orchestrator — PageIndex
================================
Top-level coordinator:
  1. Cache check (Redis)
  2. PageIndex reasoning traversal
  3. Confidence check → FAISS fallback if needed
  4. Context assembly
  5. Answer generation (or streaming)
  6. Response packaging with full explainability trace
"""
import time
from typing import AsyncGenerator

from app.core.config import settings
from app.pageindex.models.tree import ChatResponse, ReasoningStep, DocumentIndex
from app.pageindex.services import cache_service, reasoning_engine, faiss_service
from app.pageindex.services.tree_store import find_node_by_id


async def answer_query(
    index: DocumentIndex,
    query: str,
    explainability: bool = True,
) -> ChatResponse:
    start_ms = int(time.time() * 1000)
    document_id = index.document_id
    root = index.tree

    # 1. Cache check
    cached = cache_service.cache_get(document_id, query)
    if cached:
        cached["from_cache"] = True
        return ChatResponse(**cached)

    # 2. PageIndex reasoning traversal
    (
        collected_ids,
        reasoning_steps,
        reasoning_path,
        traversal_confidence,
        retrieval_method,
    ) = await reasoning_engine.traverse_and_answer(root, query, document_id)

    # 3. FAISS fallback if confidence is low
    if traversal_confidence < settings.CONFIDENCE_THRESHOLD or not collected_ids:
        faiss_ids, faiss_titles, faiss_method = await faiss_service.faiss_search(
            document_id, root, query, top_k=5
        )
        if faiss_ids:
            for fid in faiss_ids:
                if fid not in collected_ids:
                    collected_ids.append(fid)
            retrieval_method = "hybrid"
            reasoning_steps.append(ReasoningStep(
                step=len(reasoning_steps) + 1,
                node_id="faiss_fallback",
                node_title="FAISS vector search",
                decision="faiss_fallback",
                reasoning=(
                    f"Reasoning confidence ({traversal_confidence:.2f}) below threshold. "
                    f"Used vector search as fallback. Found: {', '.join(faiss_titles[:3])}"
                ),
                confidence=0.6,
            ))

    # 4. Assemble context
    context = reasoning_engine.assemble_context(root, collected_ids)

    # 5. Generate answer
    answer, answer_confidence, explanation = await reasoning_engine.generate_answer(
        query, context, reasoning_path
    )

    # 6. Build response
    source_titles = []
    for nid in collected_ids:
        node = find_node_by_id(root, nid)
        if node:
            source_titles.append(node.title)

    elapsed_ms = int(time.time() * 1000) - start_ms
    tokens_used = (len(context) + len(answer)) // 4

    response = ChatResponse(
        document_id=document_id,
        query=query,
        answer=answer,
        sources=collected_ids,
        source_titles=source_titles,
        reasoning_path=reasoning_path,
        reasoning_steps=reasoning_steps if explainability else [],
        confidence=answer_confidence,
        explanation=explanation,
        retrieval_method=retrieval_method,
        tokens_used=tokens_used,
        latency_ms=elapsed_ms,
    )

    # 7. Cache
    cache_service.cache_set(document_id, query, response.model_dump())
    return response


async def stream_query(
    index: DocumentIndex,
    query: str,
) -> AsyncGenerator[str, None]:
    document_id = index.document_id
    root = index.tree

    yield f"data: {{\"event\": \"status\", \"message\": \"Starting document traversal...\"}}\n\n"

    (
        collected_ids,
        reasoning_steps,
        reasoning_path,
        traversal_confidence,
        retrieval_method,
    ) = await reasoning_engine.traverse_and_answer(root, query, document_id)

    path_str = " → ".join(reasoning_path[:5])
    yield f"data: {{\"event\": \"traversal_complete\", \"path\": \"{path_str}\", \"nodes\": {len(collected_ids)}}}\n\n"

    if traversal_confidence < settings.CONFIDENCE_THRESHOLD or not collected_ids:
        yield f"data: {{\"event\": \"status\", \"message\": \"Low confidence — activating vector search...\"}}\n\n"
        faiss_ids, _, _ = await faiss_service.faiss_search(document_id, root, query)
        for fid in faiss_ids:
            if fid not in collected_ids:
                collected_ids.append(fid)
        retrieval_method = "hybrid"

    context = reasoning_engine.assemble_context(root, collected_ids)
    yield f"data: {{\"event\": \"status\", \"message\": \"Generating answer...\"}}\n\n"

    yield "data: {\"event\": \"answer_start\"}\n\n"
    async for token in reasoning_engine.stream_answer(query, context, reasoning_path):
        safe = token.replace('"', '\\"').replace('\n', '\\n')
        yield f"data: {{\"event\": \"token\", \"text\": \"{safe}\"}}\n\n"

    import json
    source_titles = []
    for nid in collected_ids:
        node = find_node_by_id(root, nid)
        if node:
            source_titles.append(node.title)

    meta = {
        "event": "done",
        "sources": source_titles[:5],
        "reasoning_path": reasoning_path,
        "retrieval_method": retrieval_method,
        "confidence": round(traversal_confidence, 2),
    }
    yield f"data: {json.dumps(meta)}\n\n"


async def multi_document_query(indexes: list, query: str) -> dict:
    from openai import AsyncOpenAI
    import asyncio

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    tasks = [answer_query(index, query, explainability=False) for index in indexes]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    doc_summaries = []
    for i, (index, result) in enumerate(zip(indexes, results)):
        if isinstance(result, Exception):
            doc_summaries.append(f"Document {i+1} ({index.filename}): Error — {str(result)}")
        else:
            doc_summaries.append(f"Document {i+1} ({index.filename}):\n{result.answer}")

    synthesis_prompt = f"""You have received answers from multiple documents for the same query.
Synthesise them into a coherent comparative response.

QUERY: {query}

INDIVIDUAL DOCUMENT ANSWERS:
{chr(10).join(doc_summaries)}

Provide a synthesis that:
1. Compares and contrasts the documents where relevant
2. Highlights agreements and contradictions
3. Gives an overall conclusion
4. Cites which document says what"""

    synthesis_response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": synthesis_prompt}],
        temperature=0.3,
        max_tokens=1500,
    )

    return {
        "query": query,
        "synthesis": synthesis_response.choices[0].message.content,
        "per_document": [
            {
                "document_id": index.document_id,
                "filename": index.filename,
                "answer": r.answer if not isinstance(r, Exception) else f"Error: {r}",
                "confidence": r.confidence if not isinstance(r, Exception) else 0.0,
                "sources": r.source_titles if not isinstance(r, Exception) else [],
            }
            for index, r in zip(indexes, results)
        ],
        "documents_queried": len(indexes),
    }
