from fastapi import APIRouter, Depends, UploadFile, File
from app.db.connection import get_db
from app.core.dependencies import get_current_user
from app.services import resume_service
from app.services.storage_service import get_presigned_url

router = APIRouter(prefix="/resume", tags=["resume"])


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await resume_service.process_upload(
        file=file,
        user_id=str(current_user["id"]),
        db=db,
    )
    return {
        "resume_id": str(result["id"]),
        "filename": result["filename"],
        "text_preview": result["text_preview"],
        "uploaded_at": result["uploaded_at"],
    }


@router.get("/{resume_id}/download-url")
async def get_download_url(
    resume_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT s3_key FROM resumes WHERE id = $1 AND user_id = $2",
        resume_id, str(current_user["id"]),
    )
    if not row:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")

    url = get_presigned_url(row["s3_key"])
    return {"download_url": url, "expires_in_seconds": 3600}
