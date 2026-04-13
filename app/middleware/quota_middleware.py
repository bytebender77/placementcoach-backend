"""
Quota Middleware
=================
FastAPI dependencies that enforce subscription limits.
Inject these into route functions that should be gated.

Usage in routes:
    @router.post("/analyze-profile")
    async def analyze(
        data: AnalysisRequest,
        current_user: dict = Depends(get_current_user),
        db = Depends(get_db),
        _quota = Depends(require_analysis_quota),   # ← add this
    ):
        ...

Design: We use FastAPI dependency injection rather than middleware because:
  1. We need access to the current user (from JWT) — middleware runs before auth
  2. We need the DB connection
  3. Dependencies compose cleanly with existing auth dependencies
"""
from fastapi import Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.db.connection import get_db
from app.services.subscription_service import check_quota, record_usage


async def require_analysis_quota(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Dependency: Check that the user has analysis quota remaining.
    Raises HTTP 402 if over limit with upgrade info in the body.
    Inject into any route that costs 1 analysis.
    """
    await check_quota(str(current_user["id"]), "analysis", db)
    return current_user


async def require_opportunities_feature(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Dependency: Opportunities tab requires Basic or Pro plan."""
    await check_quota(str(current_user["id"]), "opportunity", db)
    return current_user


async def require_career_path_feature(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Dependency: Career path requires Basic or Pro plan."""
    await check_quota(str(current_user["id"]), "career_path", db)
    return current_user


async def require_mock_interview_feature(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Dependency: Mock interview requires Pro plan."""
    await check_quota(str(current_user["id"]), "mock_interview", db)
    return current_user


# ── Usage recorder (call AFTER action succeeds) ───────────────────────────────

async def record_analysis_usage(user_id: str, analysis_id: str, db) -> None:
    """Call this after a successful analysis to increment usage counter."""
    await record_usage(user_id, "analysis", analysis_id, db)
