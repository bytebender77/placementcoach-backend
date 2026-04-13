"""
PageIndex Tree Builder
=======================
Takes extracted page content and builds a hierarchical PageIndex tree
using an LLM to understand document structure.

Two-pass approach:
  Pass 1 — Structure analysis: GPT reads the document outline and returns
            the hierarchical section structure as JSON.
  Pass 2 — Node summarisation: For each node, GPT generates a one-line
            summary used during traversal for routing decisions.
"""
import json
import uuid
from typing import List
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.pageindex.models.tree import PageIndexNode, DocumentIndex
from app.pageindex.services.pdf_parser import PageContent

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


STRUCTURE_PROMPT = """You are a document structure analyst. Analyse the provided document text and return its hierarchical structure as JSON.

DOCUMENT TEXT:
{document_text}

Identify all logical sections, subsections, and content blocks. Structure them hierarchically.

Rules:
1. The root node represents the entire document
2. Level 1 = major sections (Introduction, Methods, Work Experience, Chapter 1, etc.)
3. Level 2 = subsections within sections
4. Level 3 = individual content blocks (paragraphs, tables, bullet lists)
5. Capture the COMPLETE text content of each node
6. Generate a concise one-line summary for each node (10-15 words max)
7. Identify node_type: "root" | "chapter" | "section" | "block" | "table" | "list"
8. Track page ranges (page_start, page_end) from the markers [PAGE N] in the text

Return ONLY valid JSON in this exact structure:
{{
  "id": "root",
  "title": "Document root",
  "content": "<full document text or first 500 chars>",
  "summary": "<one-line summary of entire document>",
  "level": 0,
  "node_type": "root",
  "page_start": 1,
  "page_end": {total_pages},
  "children": [
    {{
      "id": "<uuid>",
      "title": "<section title>",
      "content": "<full text of this section>",
      "summary": "<one-line summary>",
      "level": 1,
      "node_type": "section",
      "page_start": <n>,
      "page_end": <n>,
      "children": [...]
    }}
  ]
}}"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def _call_gpt_json(prompt: str) -> dict:
    # Tree building needs more tokens than regular chat — 4096 minimum
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=4096,
    )
    return json.loads(response.choices[0].message.content)


def _build_node_from_dict(data: dict, parent_id: str | None = None) -> PageIndexNode:
    children = [
        _build_node_from_dict(child_data, parent_id=data.get("id") or "root")
        for child_data in data.get("children", [])
    ]
    return PageIndexNode(
        id=data.get("id") or str(uuid.uuid4()),
        title=data.get("title", "Untitled"),
        content=data.get("content", ""),
        summary=data.get("summary", ""),
        level=data.get("level", 0),
        node_type=data.get("node_type", "section"),
        page_start=data.get("page_start", 0),
        page_end=data.get("page_end", 0),
        parent_id=parent_id,
        children=children,
        metadata=data.get("metadata", {}),
    )


def _prepare_document_text(pages: List[PageContent]) -> str:
    parts = []
    total_chars = 0
    MAX_CHARS = 30000  # ~7500 tokens

    for page in pages:
        if total_chars >= MAX_CHARS:
            parts.append(f"\n[TRUNCATED — {len(pages) - page.page_number + 1} more pages]")
            break
        marker = f"\n[PAGE {page.page_number}]\n"
        content = page.raw_text[:3000] if len(page.raw_text) > 3000 else page.raw_text
        parts.append(marker + content)
        total_chars += len(content)

    return "".join(parts)


def _count_nodes(node: PageIndexNode) -> int:
    return 1 + sum(_count_nodes(child) for child in node.children)


def _build_fallback_tree(pages: List[PageContent]) -> dict:
    children = [
        {
            "id": str(uuid.uuid4()),
            "title": f"Page {page.page_number}",
            "content": page.raw_text,
            "summary": f"Page {page.page_number} content",
            "level": 1,
            "node_type": "section",
            "page_start": page.page_number,
            "page_end": page.page_number,
            "children": [],
        }
        for page in pages
    ]
    return {
        "id": "root",
        "title": "Document",
        "content": " ".join(p.raw_text[:200] for p in pages[:3]),
        "summary": "Full document content",
        "level": 0,
        "node_type": "root",
        "page_start": 1,
        "page_end": len(pages),
        "children": children,
    }


async def build_tree(
    pages: List[PageContent],
    document_id: str,
    filename: str,
) -> DocumentIndex:
    """
    Main entry point: build a complete PageIndex tree for a document.
    """
    document_text = _prepare_document_text(pages)
    total_pages = len(pages)

    prompt = STRUCTURE_PROMPT.format(
        document_text=document_text,
        total_pages=total_pages,
    )

    try:
        raw_tree = await _call_gpt_json(prompt)
        # Validate that GPT gave us actual children
        if not raw_tree.get("children"):
            print(f"[PageIndex] GPT returned tree with no children — using fallback")
            raw_tree = _build_fallback_tree(pages)
    except Exception as e:
        print(f"[PageIndex] GPT tree build failed ({e}) — using flat fallback")
        raw_tree = _build_fallback_tree(pages)

    raw_tree["id"] = "root"
    root_node = _build_node_from_dict(raw_tree, parent_id=None)
    total_nodes = _count_nodes(root_node)

    return DocumentIndex(
        document_id=document_id,
        filename=filename,
        total_pages=total_pages,
        total_nodes=total_nodes,
        tree=root_node,
    )
