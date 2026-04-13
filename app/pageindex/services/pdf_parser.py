"""
PDF Parser — PageIndex
=======================
Extracts structured text from PDFs using pdfplumber.
Returns a list of PageContent objects — one per page — with:
  - raw text
  - detected blocks (paragraphs, headers, tables)
  - page number

This is the input to the tree builder. We deliberately keep this layer
separate from tree construction so either can be swapped independently.
"""
import io
import pdfplumber
from dataclasses import dataclass, field
from typing import List
from fastapi import HTTPException, status

MAX_PDF_SIZE = 20 * 1024 * 1024  # 20 MB


@dataclass
class TextBlock:
    """A detected block of text on a page."""
    text: str
    block_type: str        # "header" | "paragraph" | "table" | "list" | "footer"
    font_size: float = 12.0
    is_bold: bool = False
    bbox: tuple = field(default_factory=tuple)


@dataclass
class PageContent:
    page_number: int       # 1-indexed
    raw_text: str
    blocks: List[TextBlock] = field(default_factory=list)
    has_table: bool = False
    word_count: int = 0


def _classify_block(chars: list, text: str) -> TextBlock:
    """
    Heuristically classify a text block based on font properties.
    Headers tend to be larger font size or bold.
    """
    if not chars or not text.strip():
        return TextBlock(text=text, block_type="paragraph")

    sizes = [c.get("size", 12) for c in chars if c.get("size")]
    avg_size = sum(sizes) / len(sizes) if sizes else 12
    is_bold = any(
        "Bold" in str(c.get("fontname", "")) or "bold" in str(c.get("fontname", ""))
        for c in chars
    )

    is_header = (avg_size >= 14 or is_bold) and len(text.split()) <= 15
    is_list = text.strip().startswith(("•", "-", "*", "○", "–", "·")) or (
        len(text) > 2 and text.strip()[0].isdigit() and text.strip()[1] in (".", ")")
    )

    block_type = "header" if is_header else "list" if is_list else "paragraph"

    return TextBlock(
        text=text,
        block_type=block_type,
        font_size=round(avg_size, 1),
        is_bold=is_bold,
    )


def extract_pages(pdf_bytes: bytes) -> List[PageContent]:
    """
    Main extraction function.
    Returns one PageContent per page, with classified text blocks.
    """
    if len(pdf_bytes) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PDF too large. Maximum size is {MAX_PDF_SIZE // (1024*1024)} MB.",
        )

    pages: List[PageContent] = []

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if len(pdf.pages) == 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="PDF has no pages.",
                )

            for i, page in enumerate(pdf.pages, start=1):
                raw_text = page.extract_text() or ""
                words = page.extract_words(
                    extra_attrs=["fontname", "size"],
                    use_text_flow=True,
                )

                blocks: List[TextBlock] = []
                has_table = False

                tables = page.extract_tables()
                if tables:
                    has_table = True
                    for table in tables:
                        table_text = "\n".join(
                            " | ".join(str(cell) for cell in row if cell)
                            for row in table if row
                        )
                        blocks.append(TextBlock(text=table_text, block_type="table"))

                if raw_text:
                    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
                    current_block_lines = []
                    current_chars = []

                    for line in lines:
                        if line:
                            current_block_lines.append(line)
                            line_chars = [
                                w for w in words
                                if any(word in line for word in w.get("text", "").split())
                            ]
                            current_chars.extend(line_chars)
                        else:
                            if current_block_lines:
                                block_text = " ".join(current_block_lines)
                                blocks.append(_classify_block(current_chars, block_text))
                                current_block_lines = []
                                current_chars = []

                    if current_block_lines:
                        block_text = " ".join(current_block_lines)
                        blocks.append(_classify_block(current_chars, block_text))

                pages.append(PageContent(
                    page_number=i,
                    raw_text=raw_text,
                    blocks=blocks,
                    has_table=has_table,
                    word_count=len(raw_text.split()),
                ))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse PDF: {str(e)}. Ensure it is a text-based PDF.",
        )

    return pages
