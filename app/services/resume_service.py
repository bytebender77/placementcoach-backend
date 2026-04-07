import io
import pdfplumber
from fastapi import UploadFile, HTTPException, status

from app.services import storage_service

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _validate_pdf(file: UploadFile):
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted.",
        )


def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF file (bytes). Returns plain text string."""
    text_parts = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse PDF: {str(e)}",
        )

    full_text = "\n".join(text_parts).strip()
    if not full_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PDF appears to be empty or image-only. Please upload a text-based PDF.",
        )
    return full_text


async def process_upload(file: UploadFile, user_id: str, db) -> dict:
    """
    Full pipeline:
      1. Validate file type
      2. Read bytes + check size
      3. Extract text (pdfplumber)
      4. Upload to S3
      5. Insert resume row in DB
    Returns resume record dict.
    """
    _validate_pdf(file)

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 5 MB.",
        )

    resume_text = extract_text_from_bytes(pdf_bytes)
    s3_key = storage_service.upload_resume(pdf_bytes, user_id, file.filename)

    row = await db.fetchrow(
        """
        INSERT INTO resumes (user_id, s3_key, filename)
        VALUES ($1, $2, $3)
        RETURNING id, user_id, s3_key, filename, uploaded_at
        """,
        user_id, s3_key, file.filename,
    )

    return {
        **dict(row),
        "resume_text": resume_text,
        "text_preview": resume_text[:300],
    }
