-- ── PlacementCoach v2 Schema Additions ──────────────────────────────
-- Run after 001_init.sql
-- psql $DATABASE_URL -f app/db/migrations/002_v2_features.sql

-- ── Co-curricular activities (added to profile) ───────────────────────
ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS co_curricular       TEXT[]  DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS achievements        TEXT[]  DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS certifications      TEXT[]  DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS github_url          TEXT,
  ADD COLUMN IF NOT EXISTS linkedin_url        TEXT,
  ADD COLUMN IF NOT EXISTS open_to_remote      BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS preferred_locations TEXT[]  DEFAULT '{}';

-- ── Internship/job opportunities (fetched per user) ──────────────────
CREATE TABLE IF NOT EXISTS opportunities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    analysis_id     UUID REFERENCES analyses(id),
    type            TEXT NOT NULL CHECK (type IN ('internship','job','hackathon','contest')),
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location        TEXT,
    stipend_or_ctc  TEXT,
    duration        TEXT,
    apply_url       TEXT NOT NULL,
    source          TEXT,          -- 'internshala' | 'unstop' | 'linkedin' | 'naukri' | 'gpt'
    deadline        TEXT,
    match_score     INT,           -- 0-100 fit score for this student
    match_reason    TEXT,
    skills_needed   TEXT[]  DEFAULT '{}',
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opp_user ON opportunities(user_id);
CREATE INDEX IF NOT EXISTS idx_opp_type ON opportunities(type);

-- ── Career path suggestions ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS career_paths (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    analysis_id     UUID REFERENCES analyses(id),
    primary_path    JSONB,         -- { title, description, fit_score, roadmap[] }
    alternate_paths JSONB,         -- array of alternate career options
    co_curricular_insights JSONB,  -- analysis of their activities
    motivation_note TEXT,          -- personalised if profile doesn't fit targets
    reality_check   TEXT,          -- honest assessment of target company fit
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_career_user ON career_paths(user_id);

-- ── Saved/bookmarked opportunities ───────────────────────────────────
CREATE TABLE IF NOT EXISTS saved_opportunities (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID REFERENCES users(id) ON DELETE CASCADE,
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE CASCADE,
    applied        BOOLEAN DEFAULT FALSE,
    applied_at     TIMESTAMPTZ,
    saved_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, opportunity_id)
);
