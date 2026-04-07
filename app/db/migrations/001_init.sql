-- Run once against your Neon DB
-- psql $DATABASE_URL -f app/db/migrations/001_init.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Users ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name     TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ── Profiles ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS profiles (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID REFERENCES users(id) ON DELETE CASCADE,
    cgpa             NUMERIC(3,2) NOT NULL,
    college_tier     TEXT NOT NULL CHECK (college_tier IN ('tier1','tier2','tier3')),
    year             TEXT NOT NULL CHECK (year IN ('2nd','3rd','4th','fresher')),
    skills           TEXT[] NOT NULL DEFAULT '{}',
    target_roles     TEXT[] DEFAULT '{}',
    target_companies TEXT[] DEFAULT '{}',
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

-- ── Resumes ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS resumes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    s3_key      TEXT NOT NULL,
    filename    TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Analyses ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analyses (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID REFERENCES users(id) ON DELETE CASCADE,
    resume_id         UUID REFERENCES resumes(id),
    profile_id        UUID REFERENCES profiles(id),
    placement_low     INT NOT NULL,
    placement_high    INT NOT NULL,
    placement_label   TEXT NOT NULL,
    ats_score         INT NOT NULL,
    ats_strengths     TEXT[] DEFAULT '{}',
    ats_weaknesses    TEXT[] DEFAULT '{}',
    missing_keywords  TEXT[] DEFAULT '{}',
    raw_llm_response  JSONB,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- ── Action Plans ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS action_plans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    analysis_id     UUID REFERENCES analyses(id),
    weeks           JSONB NOT NULL,
    priority_skills TEXT[] DEFAULT '{}',
    duration_weeks  INT DEFAULT 6,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_resumes_user    ON resumes(user_id);
CREATE INDEX IF NOT EXISTS idx_analyses_user   ON analyses(user_id);
CREATE INDEX IF NOT EXISTS idx_plans_user      ON action_plans(user_id);
CREATE INDEX IF NOT EXISTS idx_plans_analysis  ON action_plans(analysis_id);
