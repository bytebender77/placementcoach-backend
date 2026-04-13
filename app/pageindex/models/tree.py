"""
PageIndex Data Models
======================
The PageIndex tree is a hierarchical structure that mirrors a document's
logical organisation — exactly how a human reader would mentally navigate it.

Document
 └─ Chapter / Section (level 1)
     └─ Subsection (level 2)
         └─ Paragraph / Block (level 3)

Each node holds:
  - Its own text content (summary or full text for leaf nodes)
  - Metadata (page range, type, level)
  - Children references

This is NOT chunked embedding — the hierarchy is the index.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid


class PageIndexNode(BaseModel):
    """A single node in the PageIndex tree."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str                              # e.g. "Work Experience", "Section 2.3"
    content: str                            # full text content of this node
    summary: str = ""                       # LLM-generated one-line summary
    level: int                              # 0=root, 1=chapter, 2=section, 3=block
    node_type: str = "section"             # "root" | "chapter" | "section" | "block" | "table" | "list"
    page_start: int = 0
    page_end: int = 0
    parent_id: Optional[str] = None
    children: List["PageIndexNode"] = []
    metadata: Dict[str, Any] = {}          # arbitrary extras (font size, table cols, etc.)

    class Config:
        arbitrary_types_allowed = True


# Required for self-referential model
PageIndexNode.model_rebuild()


class DocumentIndex(BaseModel):
    """The complete PageIndex for one document."""
    document_id: str
    filename: str
    total_pages: int
    total_nodes: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tree: PageIndexNode                    # root node


class ChatRequest(BaseModel):
    document_id: str
    query: str
    stream: bool = False
    explainability: bool = True            # return full reasoning trace


class MultiChatRequest(BaseModel):
    documents: List[str]                   # list of document_ids
    query: str
    stream: bool = False


class ReasoningStep(BaseModel):
    """One decision step in the traversal loop."""
    step: int
    node_id: str
    node_title: str
    decision: str                          # "explore" | "go_deeper" | "skip" | "collect" | "stop"
    reasoning: str                         # LLM's explanation for this decision
    confidence: float                      # 0-1


class ChatResponse(BaseModel):
    """Full structured response from /pageindex/chat."""
    document_id: str
    query: str
    answer: str
    sources: List[str]                     # node IDs used
    source_titles: List[str]              # human-readable node titles
    reasoning_path: List[str]             # ordered list: "Introduction → Work Experience → Google"
    reasoning_steps: List[ReasoningStep]  # full explainability trace
    confidence: float                      # 0-1
    explanation: str                       # why these nodes were selected
    retrieval_method: str                 # "pageindex" | "hybrid" | "faiss_fallback"
    tokens_used: int
    latency_ms: int
