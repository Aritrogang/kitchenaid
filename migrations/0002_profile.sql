-- 0002_profile — server-side user profiles.
--
-- One row per user. `data` is the serialized Profile (allergies, diet, budget, skill, …) —
-- the same shape `Profile.to_dict()` writes and the JSON FileStore uses, so the backends are
-- wire-compatible. Allergies here are HARD rules the Dietitian enforces, but the gate reads
-- them from the resolved request Profile at decision time. This table is durable storage, not
-- the gate's authority.
CREATE TABLE IF NOT EXISTS profile (
    user_id     text        PRIMARY KEY,
    data        jsonb       NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
