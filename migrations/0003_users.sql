-- 0003_users — accounts for username/password login.
--
-- One row per account. `user_id` is the stable identity everything else keys on (profile,
-- taste, the token subject); `username` is the human handle and can be changed without
-- rewriting a user's data. Only the PBKDF2 hash is stored — never a plaintext password.
CREATE TABLE IF NOT EXISTS users (
    user_id       text        PRIMARY KEY,
    username      text        UNIQUE NOT NULL,
    password_hash text        NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);
