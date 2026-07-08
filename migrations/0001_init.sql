-- 0001_init — the persistent user store.
--
-- One row per user. `data` holds the serialized TasteMemory (the same shape the JSON
-- FileStore writes), so the two backends are wire-compatible and a user can be migrated
-- from files to Postgres by copying the JSON in. The gate never reads this table — taste
-- only nudges ranking — so nothing here is safety-critical.
CREATE TABLE IF NOT EXISTS taste (
    user_id     text        PRIMARY KEY,
    data        jsonb       NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
