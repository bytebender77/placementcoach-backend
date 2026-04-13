"""
FAISS Vector Fallback — PageIndex
===================================
When the LLM reasoning traversal returns low confidence (< CONFIDENCE_THRESHOLD),
we fall back to vector similarity search over the document's nodes.

Falls back gracefully to numpy cosine if faiss-cpu is not installed.
"""
import os
import json
import pickle
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional

from openai import AsyncOpenAI
from app.core.config import settings
from app.pageindex.models.tree import PageIndexNode
from app.pageindex.services.tree_store import find_node_by_id

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
EMBEDDING_MODEL = "text-embedding-3-small"

FAISS_AVAILABLE = True
try:
    import faiss
except ImportError:
    FAISS_AVAILABLE = False


def _faiss_dir() -> Path:
    idx_dir = Path(settings.PAGEINDEX_DATA_DIR) / "faiss_indexes"
    idx_dir.mkdir(parents=True, exist_ok=True)
    return idx_dir


def _faiss_path(document_id: str) -> Path:
    return _faiss_dir() / f"{document_id}.faiss"


def _meta_path(document_id: str) -> Path:
    return _faiss_dir() / f"{document_id}.meta.pkl"


def _collect_all_nodes(root: PageIndexNode) -> List[PageIndexNode]:
    result = []
    queue = [root]
    while queue:
        node = queue.pop(0)
        result.append(node)
        queue.extend(node.children)
    return result


async def _embed_texts(texts: List[str]) -> np.ndarray:
    BATCH_SIZE = 100
    all_embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        response = await client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        all_embeddings.extend(item.embedding for item in response.data)
    return np.array(all_embeddings, dtype=np.float32)


async def build_faiss_index(document_id: str, root: PageIndexNode) -> None:
    nodes = _collect_all_nodes(root)
    texts = [node.summary or node.content[:500] for node in nodes]

    try:
        embeddings = await _embed_texts(texts)
        node_ids = [n.id for n in nodes]
        node_titles = [n.title for n in nodes]

        if FAISS_AVAILABLE:
            dim = embeddings.shape[1]
            faiss.normalize_L2(embeddings)
            index = faiss.IndexFlatIP(dim)
            index.add(embeddings)
            faiss.write_index(index, str(_faiss_path(document_id)))
        else:
            # numpy fallback: store raw embeddings
            np.save(str(_faiss_path(document_id)) + ".npy", embeddings)

        meta = {"node_ids": node_ids, "node_titles": node_titles}
        with open(_meta_path(document_id), "wb") as f:
            pickle.dump(meta, f)

    except Exception:
        pass  # FAISS index is purely for fallback — non-fatal if it fails


async def faiss_search(
    document_id: str,
    root: PageIndexNode,
    query: str,
    top_k: int = 5,
) -> Tuple[List[str], List[str], str]:
    meta_file = _meta_path(document_id)
    if not meta_file.exists():
        return [], [], "faiss_missing"

    try:
        with open(meta_file, "rb") as f:
            meta = pickle.load(f)
        node_ids = meta["node_ids"]
        node_titles = meta["node_titles"]

        query_emb = await _embed_texts([query])
        collected_ids, collected_titles = [], []

        if FAISS_AVAILABLE and _faiss_path(document_id).exists():
            import faiss as _faiss
            _faiss.normalize_L2(query_emb)
            index = _faiss.read_index(str(_faiss_path(document_id)))
            distances, indices = index.search(query_emb, top_k)
            for idx, dist in zip(indices[0], distances[0]):
                if 0 <= idx < len(node_ids) and dist >= 0.3:
                    collected_ids.append(node_ids[idx])
                    collected_titles.append(node_titles[idx])
        else:
            # numpy cosine fallback
            npy_path = str(_faiss_path(document_id)) + ".npy"
            if os.path.exists(npy_path):
                stored = np.load(npy_path)
                norms = np.linalg.norm(stored, axis=1, keepdims=True)
                stored_norm = stored / (norms + 1e-10)
                q_norm = query_emb / (np.linalg.norm(query_emb) + 1e-10)
                scores = (stored_norm @ q_norm.T).flatten()
                top_indices = np.argsort(scores)[::-1][:top_k]
                for idx in top_indices:
                    if scores[idx] >= 0.3:
                        collected_ids.append(node_ids[idx])
                        collected_titles.append(node_titles[idx])

        return collected_ids, collected_titles, "faiss_fallback"

    except Exception:
        return [], [], "faiss_error"
