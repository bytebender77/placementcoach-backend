from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.db.connection import create_pool, close_pool
from app.routers import auth, resume, analysis, results, opportunities


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await create_pool()
    yield
    # Shutdown
    await close_pool()


app = FastAPI(
    title="PlacementCoach API",
    description="AI-powered placement guidance for Indian college students",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:3000",
        "https://placementcoach.vercel.app",
        "https://placementcoach-frontend-ig6q.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(resume.router)
app.include_router(analysis.router)
app.include_router(results.router)
app.include_router(opportunities.router)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.APP_ENV, "version": "2.0.0"}
