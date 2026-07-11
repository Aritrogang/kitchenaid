-- 0004_session — the last meal per user, so feedback attaches to it across turns.
--
-- One row per user holding the serialized last recommended Recipe. This makes the "that was
-- too spicy" flow work even when turns land on different stateless (serverless) instances:
-- the session lives in the store, not in a process's memory. Cleared on erasure.
CREATE TABLE IF NOT EXISTS session (
    user_id     text        PRIMARY KEY,
    data        jsonb       NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
