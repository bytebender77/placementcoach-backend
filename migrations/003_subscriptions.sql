-- ── PlacementCoach Subscription Schema ──────────────────────────────────────
-- Run after 001_init.sql and 002_v2_features.sql
-- psql $DATABASE_URL -f migrations/003_subscriptions.sql

-- ── Plans (static reference table) ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS plans (
    id              TEXT PRIMARY KEY,              -- 'free' | 'basic' | 'pro'
    name            TEXT NOT NULL,
    price_inr       INT  NOT NULL,                 -- ₹ per month, 0 for free
    analyses_per_month INT NOT NULL,               -- -1 = unlimited
    features        JSONB NOT NULL DEFAULT '{}',   -- feature flags
    razorpay_plan_id TEXT                          -- Razorpay plan ID for subscriptions
);

INSERT INTO plans (id, name, price_inr, analyses_per_month, features) VALUES
('free',  'Starter', 0,   3,  '{"opportunities":false,"career_path":false,"history_days":0,"mock_interview":false,"diff_view":false}'),
('basic', 'Basic',   49,  15, '{"opportunities":true,"career_path":true,"history_days":30,"mock_interview":false,"diff_view":true}'),
('pro',   'Pro',     149, -1, '{"opportunities":true,"career_path":true,"history_days":9999,"mock_interview":true,"diff_view":true,"linkedin_optimizer":true}')
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    price_inr = EXCLUDED.price_inr,
    analyses_per_month = EXCLUDED.analyses_per_month,
    features = EXCLUDED.features;

-- ── Subscriptions (one active per user) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS subscriptions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES users(id) ON DELETE CASCADE,
    plan_id             TEXT REFERENCES plans(id) NOT NULL DEFAULT 'free',
    status              TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active','cancelled','expired','pending')),
    -- Billing period
    current_period_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    current_period_end   TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 days'),
    -- Usage tracking
    analyses_used_this_period INT NOT NULL DEFAULT 0,
    -- Razorpay identifiers
    razorpay_subscription_id TEXT,
    razorpay_customer_id     TEXT,
    -- Metadata
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

-- ── Payments (audit log of every transaction) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS payments (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID REFERENCES users(id) ON DELETE CASCADE,
    subscription_id         UUID REFERENCES subscriptions(id),
    plan_id                 TEXT REFERENCES plans(id),
    amount_inr              INT NOT NULL,
    currency                TEXT NOT NULL DEFAULT 'INR',
    status                  TEXT NOT NULL
                                CHECK (status IN ('created','authorized','captured','failed','refunded')),
    -- Razorpay identifiers
    razorpay_order_id       TEXT UNIQUE,
    razorpay_payment_id     TEXT UNIQUE,
    razorpay_signature      TEXT,
    -- Metadata
    payment_method          TEXT,                  -- 'upi' | 'card' | 'netbanking'
    failure_reason          TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    captured_at             TIMESTAMPTZ
);

-- ── Usage events (every analysis counts against quota) ────────────────────────
CREATE TABLE IF NOT EXISTS usage_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL,                 -- 'analysis' | 'plan' | 'career_path' | 'opportunity'
    analysis_id     UUID REFERENCES analyses(id),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_subscriptions_user    ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status  ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_payments_user         ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_razorpay_ord ON payments(razorpay_order_id);
CREATE INDEX IF NOT EXISTS idx_usage_user_type       ON usage_events(user_id, event_type, created_at);

-- ── Auto-provision free plan for existing users ────────────────────────────────
INSERT INTO subscriptions (user_id, plan_id)
SELECT id, 'free' FROM users
WHERE id NOT IN (SELECT user_id FROM subscriptions)
ON CONFLICT (user_id) DO NOTHING;
