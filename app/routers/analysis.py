from fastapi import APIRouter, Depends, HTTPException, status
from app.db.connection import get_db
from app.core.dependencies import get_current_user
from app.models.analysis import AnalysisRequest
from app.services import analysis_service
from app.services.resume_service import extract_text_from_bytes
from app.services.storage_service import get_presigned_url
from app.middleware.quota_middleware import require_analysis_quota, record_analysis_usage
import httpx

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/analyze-profile")
async def analyze_profile(
    data: AnalysisRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
    _quota_check=Depends(require_analysis_quota),
):
    user_id = str(current_user["id"])

    # Fetch resume S3 key
    resume_row = await db.fetchrow(
        "SELECT id, s3_key FROM resumes WHERE id = $1 AND user_id = $2",
        str(data.resume_id), user_id,
    )
    if not resume_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found. Please upload your resume first.",
        )

    # Fetch resume text from S3 via presigned URL
    presigned_url = get_presigned_url(resume_row["s3_key"])
    async with httpx.AsyncClient() as client:
        response = await client.get(presigned_url)
        pdf_bytes = response.content

    resume_text = extract_text_from_bytes(pdf_bytes)

    result = await analysis_service.run_analysis(
        resume_text=resume_text,
        cgpa=data.cgpa,
        skills=data.skills,
        college_tier=data.college_tier,
        year=data.year,
        target_roles=data.target_roles,
        target_companies=data.target_companies,
        co_curricular=data.co_curricular,
        achievements=data.achievements,
        certifications=data.certifications,
        github_url=data.github_url,
        linkedin_url=data.linkedin_url,
        open_to_remote=data.open_to_remote,
        preferred_locations=data.preferred_locations,
        user_id=user_id,
        resume_id=str(resume_row["id"]),
        db=db,
    )

    # Record usage against monthly quota
    await record_analysis_usage(user_id, result["id"], db)

    return result


@router.post("/generate-plan")
async def generate_plan(
    data: dict,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    analysis_id = data.get("analysis_id")
    if not analysis_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="analysis_id is required",
        )

    try:
        result = await analysis_service.generate_plan(
            analysis_id=str(analysis_id),
            user_id=str(current_user["id"]),
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return result


@router.get("/history")
async def get_analysis_history(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Return last 5 analyses for the current user."""
    rows = await db.fetch(
        """
        SELECT id, placement_low, placement_high, placement_label,
               ats_score, created_at
        FROM analyses
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT 5
        """,
        str(current_user["id"]),
    )
    return [dict(r) for r in rows]
