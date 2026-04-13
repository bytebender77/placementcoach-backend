from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    # AWS S3 (optional in dev — set STORAGE_BACKEND=local to skip)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-south-1"
    S3_BUCKET_NAME: str = "placementcoach-resumes"

    # Storage backend: "local" for dev (saves to uploads/), "s3" for production
    STORAGE_BACKEND: str = "local"

    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_MAX_TOKENS: int = 2000

    # ── PageIndex settings ────────────────────────────────
    PAGEINDEX_DATA_DIR: str = "./data"
    PAGEINDEX_STORAGE_MODE: str = "local"   # "local" | "s3"

    # Reasoning engine tuning
    MAX_TRAVERSAL_DEPTH: int = 6
    MAX_NODES_VISITED: int = 20
    CONFIDENCE_THRESHOLD: float = 0.65
    MAX_CONTEXT_TOKENS: int = 6000

    # Redis (optional — PageIndex cache; degrades gracefully if unavailable)
    REDIS_URL: str = ""
    CACHE_TTL_SECONDS: int = 3600

    # ── Razorpay (payment gateway for INR subscriptions) ─────────────────
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # App
    APP_ENV: str = "development"
    FRONTEND_URL: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
