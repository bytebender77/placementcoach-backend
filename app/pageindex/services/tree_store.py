"""
Tree Storage Service — PageIndex
==================================
Persists and retrieves DocumentIndex objects.
Supports local filesystem and S3. Defaults to local.

Each document gets its own tree.json keyed by document_id.
"""
import json
import os
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.pageindex.models.tree import DocumentIndex, PageIndexNode


def _tree_path(document_id: str) -> Path:
    trees_dir = Path(settings.PAGEINDEX_DATA_DIR) / "trees"
    trees_dir.mkdir(parents=True, exist_ok=True)
    return trees_dir / f"{document_id}.json"


def _node_to_dict(node: PageIndexNode) -> dict:
    return {
        "id": node.id,
        "title": node.title,
        "content": node.content,
        "summary": node.summary,
        "level": node.level,
        "node_type": node.node_type,
        "page_start": node.page_start,
        "page_end": node.page_end,
        "parent_id": node.parent_id,
        "metadata": node.metadata,
        "children": [_node_to_dict(c) for c in node.children],
    }


def _dict_to_node(data: dict, parent_id: str | None = None) -> PageIndexNode:
    children = [_dict_to_node(c, parent_id=data["id"]) for c in data.get("children", [])]
    return PageIndexNode(
        id=data["id"],
        title=data["title"],
        content=data["content"],
        summary=data.get("summary", ""),
        level=data["level"],
        node_type=data.get("node_type", "section"),
        page_start=data.get("page_start", 0),
        page_end=data.get("page_end", 0),
        parent_id=parent_id or data.get("parent_id"),
        children=children,
        metadata=data.get("metadata", {}),
    )


def save_tree(index: DocumentIndex) -> None:
    payload = {
        "document_id": index.document_id,
        "filename": index.filename,
        "total_pages": index.total_pages,
        "total_nodes": index.total_nodes,
        "created_at": index.created_at.isoformat(),
        "tree": _node_to_dict(index.tree),
    }
    if settings.PAGEINDEX_STORAGE_MODE == "s3":
        _save_to_s3(index.document_id, payload)
    else:
        path = _tree_path(index.document_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)


def load_tree(document_id: str) -> Optional[DocumentIndex]:
    if settings.PAGEINDEX_STORAGE_MODE == "s3":
        payload = _load_from_s3(document_id)
    else:
        path = _tree_path(document_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

    if not payload:
        return None

    from datetime import datetime
    return DocumentIndex(
        document_id=payload["document_id"],
        filename=payload["filename"],
        total_pages=payload["total_pages"],
        total_nodes=payload["total_nodes"],
        created_at=datetime.fromisoformat(payload["created_at"]),
        tree=_dict_to_node(payload["tree"]),
    )


def document_exists(document_id: str) -> bool:
    if settings.PAGEINDEX_STORAGE_MODE == "s3":
        return _s3_key_exists(document_id)
    return _tree_path(document_id).exists()


def list_documents() -> list[dict]:
    trees_dir = Path(settings.PAGEINDEX_DATA_DIR) / "trees"
    if not trees_dir.exists():
        return []
    docs = []
    for path in trees_dir.glob("*.json"):
        try:
            with open(path) as f:
                meta = json.load(f)
            docs.append({
                "document_id": meta["document_id"],
                "filename": meta["filename"],
                "total_pages": meta["total_pages"],
                "total_nodes": meta["total_nodes"],
                "created_at": meta["created_at"],
            })
        except Exception:
            continue
    return sorted(docs, key=lambda x: x["created_at"], reverse=True)


# ── Tree traversal utilities ──────────────────────────────────────────────────

def find_node_by_id(root: PageIndexNode, node_id: str) -> Optional[PageIndexNode]:
    queue = [root]
    while queue:
        node = queue.pop(0)
        if node.id == node_id:
            return node
        queue.extend(node.children)
    return None


def get_node_path(root: PageIndexNode, node_id: str) -> list[str]:
    def dfs(node: PageIndexNode, target_id: str, path: list) -> Optional[list]:
        path = path + [node.title]
        if node.id == target_id:
            return path
        for child in node.children:
            result = dfs(child, target_id, path)
            if result:
                return result
        return None
    return dfs(root, node_id, []) or []


def get_subtree_text(node: PageIndexNode, max_depth: int = 2) -> str:
    parts = [f"[{node.title}]\n{node.content}"]
    if max_depth > 0:
        for child in node.children:
            parts.append(get_subtree_text(child, max_depth - 1))
    return "\n\n".join(filter(None, parts))


# ── S3 backend ────────────────────────────────────────────────────────────────

def _save_to_s3(document_id: str, payload: dict) -> None:
    import boto3, json as _json
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    s3.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=f"pageindex/trees/{document_id}.json",
        Body=_json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )


def _load_from_s3(document_id: str) -> Optional[dict]:
    import boto3, json as _json
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    try:
        obj = s3.get_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=f"pageindex/trees/{document_id}.json",
        )
        return _json.loads(obj["Body"].read())
    except Exception:
        return None


def _s3_key_exists(document_id: str) -> bool:
    import boto3
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    try:
        s3.head_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=f"pageindex/trees/{document_id}.json",
        )
        return True
    except Exception:
        return False
