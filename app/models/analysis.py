from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid


class PlacementScore(BaseModel):
    low: int
    high: int
    label: str          # "Low" | "Moderate" | "Good" | "Strong"
    reasoning: str


class ATSFeedback(BaseModel):
    score: int          # 0–100
    strengths: List[str]
    weaknesses: List[str]
    missing_keywords: List[str]


class AnalysisRequest(BaseModel):
    resume_id: uuid.UUID
    cgpa: float
    college_tier: str
    year: str
    skills: List[str]
    target_roles: List[str] = []
    target_companies: List[str] = []


class AnalysisOut(BaseModel):
    id: uuid.UUID
    placement: PlacementScore
    ats: ATSFeedback
    created_at: datetime


class PlanRequest(BaseModel):
    analysis_id: uuid.UUID


class WeekPlan(BaseModel):
    week: int
    theme: str
    tasks: List[str]
    resources: List[str]


class ActionPlanOut(BaseModel):
    id: uuid.UUID
    weeks: List[WeekPlan]
    priority_skills: List[str]
    duration_weeks: int
    created_at: datetime


class DashboardOut(BaseModel):
    analysis: Optional[AnalysisOut]
    plan: Optional[ActionPlanOut]
