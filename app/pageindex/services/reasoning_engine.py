"""
Reasoning Engine — PageIndex Traversal
========================================
This is the heart of the system. It implements multi-step LLM-driven
traversal of the PageIndex tree to answer queries WITHOUT keyword matching.

The Algorithm (mimics how a human reads a document):
─────────────────────────────────────────────────────
1. START at the root node
2. ASK the LLM: "Given this query and the available children, which node
   should I explore next?"
3. MOVE to the selected node
4. ASK: "Should I go deeper into this node's children, or is this enough?"
5. If enough context is collected, STOP
6. Otherwise, continue traversal
7. ASSEMBLE all collected context
8. GENERATE the final answer using the assembled context
"""
import json
import time
from typing import List, Set, Tuple, Optional, AsyncGenerator
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.pageindex.models.tree import PageIndexNode, ReasoningStep, ChatResponse
from app.pageindex.services.tree_store import find_node_by_id, get_node_path, get_subtree_text

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


NAVIGATION_PROMPT = """You are navigating a document index tree to answer a user query.

USER QUERY: {query}

CURRENT NODE: "{current_title}"
CURRENT NODE CONTENT PREVIEW: {content_preview}

AVAILABLE CHILDREN (nodes you can explore next):
{children_list}

ALREADY VISITED: {visited_titles}

TASK:
- If this node or its content is relevant to the query, collect it.
- If it has children worth exploring, select them.
- If you have gathered enough context, stop.

IMPORTANT: If there are NO children (leaf node) and the content is relevant, set decision to "collect" and has_enough_context based on whether you need more.

Return ONLY valid JSON:
{{
  "decision": "<'explore' | 'collect' | 'collect_and_continue' | 'go_deeper' | 'stop'>",
  "selected_node_ids": ["<id1>", "<id2>"],
  "reasoning": "<Why you made this decision>",
  "confidence": <0.0 to 1.0>,
  "has_enough_context": <true|false>
}}"""


ANSWER_PROMPT = """You are an expert document analyst. Answer the user's question based ONLY on the provided document context.

USER QUERY: {query}

RETRIEVED DOCUMENT CONTEXT:
{context}

REASONING PATH TAKEN: {reasoning_path}

Instructions:
1. Answer directly and completely based on the context
2. If the context does not contain the answer, say so explicitly
3. Cite specific sections by referencing node titles in [brackets]
4. Do not make up information not present in the context

Return ONLY valid JSON:
{{
  "answer": "<your complete answer>",
  "confidence": <0.0-1.0>,
  "explanation": "<why you selected these sources>",
  "sources_used": ["<node_title1>", "<node_title2>"]
}}"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def _navigate(prompt: str) -> dict:
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=800,
    )
    return json.loads(response.choices[0].message.content)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def _answer(prompt: str) -> dict:
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=settings.OPENAI_MAX_TOKENS,
    )
    return json.loads(response.choices[0].message.content)


def _format_children_list(children: List[PageIndexNode]) -> str:
    if not children:
        return "No children (this is a leaf node)"
    lines = []
    for child in children:
        lines.append(
            f"  - ID: {child.id}\n"
            f"    Title: {child.title}\n"
            f"    Type: {child.node_type}\n"
            f"    Summary: {child.summary or child.content[:100]}"
        )
    return "\n".join(lines)


def _get_visited_nodes(root: PageIndexNode, visited_ids: Set[str]) -> List[PageIndexNode]:
    result = []
    queue = [root]
    while queue:
        node = queue.pop(0)
        if node.id in visited_ids:
            result.append(node)
        queue.extend(node.children)
    return result


async def traverse_and_answer(
    root: PageIndexNode,
    query: str,
    document_id: str,
) -> Tuple[List[str], List[ReasoningStep], List[str], float, str]:
    """
    Core PageIndex reasoning traversal.

    Returns:
      - collected_node_ids
      - reasoning_steps (full explainability trace)
      - reasoning_path (human-readable)
      - confidence
      - retrieval_method
    """
    visited: Set[str] = set()
    collected_node_ids: List[str] = []
    reasoning_steps: List[ReasoningStep] = []
    reasoning_path: List[str] = [root.title]
    step_counter = 0

    queue = [(root, 0)]

    while queue and len(visited) < settings.MAX_NODES_VISITED:
        current_node, depth = queue.pop(0)

        if current_node.id in visited:
            continue
        visited.add(current_node.id)

        if depth > settings.MAX_TRAVERSAL_DEPTH:
            continue

        # ── Leaf node shortcut ────────────────────────────────────────────────
        # If a node has no children, ask the LLM if its content is relevant.
        # Skip the "select children" step — there are no children to select.
        is_leaf = len(current_node.children) == 0

        content_preview = current_node.content[:600].replace("\n", " ")
        visited_titles = [n.title for n in _get_visited_nodes(root, visited)]

        nav_prompt = NAVIGATION_PROMPT.format(
            query=query,
            current_title=current_node.title,
            content_preview=content_preview,
            children_list=_format_children_list(current_node.children),
            visited_titles=", ".join(visited_titles[-5:]) or "None yet",
        )

        try:
            nav_decision = await _navigate(nav_prompt)
        except Exception as nav_err:
            # Navigation failed — still make progress:
            # 1. Collect this node if it's a leaf (content is all we have)
            if is_leaf and current_node.id not in collected_node_ids:
                collected_node_ids.append(current_node.id)
                path = get_node_path(root, current_node.id)
                reasoning_path.extend(p for p in path if p not in reasoning_path)
            # 2. Always enqueue children so traversal continues
            for child in current_node.children:
                if child.id not in visited:
                    queue.append((child, depth + 1))
            continue

        step_counter += 1
        decision = nav_decision.get("decision", "explore")
        selected_ids = nav_decision.get("selected_node_ids", [])
        reasoning = nav_decision.get("reasoning", "")
        confidence = float(nav_decision.get("confidence", 0.5))
        has_enough = nav_decision.get("has_enough_context", False)

        reasoning_steps.append(ReasoningStep(
            step=step_counter,
            node_id=current_node.id,
            node_title=current_node.title,
            decision=decision,
            reasoning=reasoning,
            confidence=confidence,
        ))

        # Collect this node if the decision says so, or if it's a relevant leaf
        should_collect = (
            decision in ("collect", "collect_and_continue", "go_deeper")
            or (decision == "explore" and confidence >= 0.5)
            or (is_leaf and decision != "stop" and confidence >= 0.4)
        )

        if should_collect and current_node.id not in collected_node_ids:
            collected_node_ids.append(current_node.id)
            path = get_node_path(root, current_node.id)
            reasoning_path.extend(p for p in path if p not in reasoning_path)

        if has_enough or decision == "stop":
            break

        # Enqueue children for further traversal
        for child in current_node.children:
            if child.id in selected_ids and child.id not in visited:
                queue.insert(0, (child, depth + 1))

        # If LLM said "explore" without selecting specific children,
        # enqueue all unvisited children
        if decision in ("explore", "go_deeper", "collect_and_continue") and not selected_ids:
            for child in current_node.children:
                if child.id not in visited:
                    queue.append((child, depth + 1))

    # ── Hard fallback: if traversal collected nothing, take ALL leaf nodes ──
    # This handles: flat trees, API failures, low-confidence traversal
    if not collected_node_ids:
        def _collect_leaves(node: PageIndexNode):
            if not node.children:
                return [node.id]
            leaves = []
            for child in node.children:
                leaves.extend(_collect_leaves(child))
            return leaves

        leaf_ids = _collect_leaves(root)
        # If no leaves either (shouldn't happen), use root itself
        collected_node_ids = leaf_ids if leaf_ids else [root.id]
        reasoning_path = [root.title, "[hard-fallback: all leaves collected]"]
        reasoning_steps.append(ReasoningStep(
            step=step_counter + 1,
            node_id="fallback",
            node_title="Hard fallback",
            decision="collect",
            reasoning="Traversal collected no nodes — using all leaf content as context.",
            confidence=0.5,
        ))

    final_confidence = (
        sum(s.confidence for s in reasoning_steps) / len(reasoning_steps)
        if reasoning_steps else 0.5
    )

    return (collected_node_ids, reasoning_steps, reasoning_path, final_confidence, "pageindex")


def assemble_context(
    root: PageIndexNode,
    collected_node_ids: List[str],
    max_tokens: int = None,
) -> str:
    max_tokens = max_tokens or settings.MAX_CONTEXT_TOKENS
    parts = []
    total_chars = 0
    max_chars = max_tokens * 4  # rough: 1 token ≈ 4 chars

    for node_id in collected_node_ids:
        node = find_node_by_id(root, node_id)
        if not node:
            continue
        text = get_subtree_text(node, max_depth=1)
        header = f"\n{'='*40}\n[SOURCE: {node.title}]\n{'='*40}\n"
        chunk = header + text

        if total_chars + len(chunk) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 200:
                parts.append(chunk[:remaining] + "...[truncated]")
            break

        parts.append(chunk)
        total_chars += len(chunk)

    return "\n".join(parts)


async def generate_answer(
    query: str,
    context: str,
    reasoning_path: List[str],
) -> Tuple[str, float, str]:
    if not context.strip():
        return (
            "I could not find relevant information in the document to answer this query.",
            0.1,
            "No relevant nodes were collected during traversal.",
        )

    prompt = ANSWER_PROMPT.format(
        query=query,
        context=context,
        reasoning_path=" → ".join(reasoning_path),
    )

    try:
        result = await _answer(prompt)
        return (
            result.get("answer", "Unable to generate answer."),
            float(result.get("confidence", 0.5)),
            result.get("explanation", ""),
        )
    except Exception as e:
        return ("An error occurred while generating the answer.", 0.0, str(e))


async def stream_answer(
    query: str,
    context: str,
    reasoning_path: List[str],
) -> AsyncGenerator[str, None]:
    stream_prompt = f"""Answer this question based on the document context below.
Be concise and cite the source sections.

QUERY: {query}

CONTEXT:
{context[:8000]}

Answer directly:"""

    try:
        stream = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "user", "content": stream_prompt}],
            temperature=0.3,
            max_tokens=1000,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    except Exception as e:
        yield f"\n[Error during streaming: {str(e)}]"
