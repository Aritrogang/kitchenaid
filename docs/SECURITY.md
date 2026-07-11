# Security posture

What the app enforces today, and what a deployment still must do. This describes real,
tested controls — not aspirations.

## Enforced in code

- **Deterministic, fail-closed safety gate.** Allergen and diet rules are hard constraints
  checked by deterministic tools (`tools.gate`), never by model judgment. Unknown ingredients
  fail *closed* (block the dish). The eval harness asserts **0 unsafe approvals** on a frozen
  corpus of real model output, and CI runs it on every push.
- **Auth (opt-in).** With `KITCHENAID_AUTH_SECRET` set, every request carries a signed Bearer
  token and identity comes from the token — not the client. A user can only read/write their
  own profile and taste. HS256, fixed algorithm at verify time (no alg-confusion / `none`),
  constant-time signature compare, expiry enforced. See `docs/AUTH` notes in `kitchenaid/auth.py`.
- **Spend guardrail.** A hard budget gate refuses paid LLM calls before they fire, with global
  and opt-in **per-user** daily caps and a persistent ledger. Fail-closed on an unreadable ledger.
- **Data erasure.** `DELETE /profile/{user_id}` removes a user's profile and taste (right to
  erasure). Idempotent.
- **Secrets never in the image or repo.** `.env` is git- and docker-ignored; CI scans confirm no
  API keys in tracked files. Config is injected at runtime.
- **Safety disclaimer** returned with every answer (`disclaimer` field) — the product never
  implies an allergen guarantee.

## The deployment must still do

- **Restrict CORS.** `allow_origins=["*"]` is for local dev only — pin it to your web origin.
- **TLS.** Terminate HTTPS at a reverse proxy; never serve the API plaintext in production.
- **Secrets manager.** Move `DATABASE_URL`, `ANTHROPIC_API_KEY`, `KITCHENAID_AUTH_SECRET` out of
  `.env` into your platform's secret store; rotate the auth secret.
- **Token issuance.** Wire `create_token` to a real credential source (OAuth / SSO / password).
- **Rate limiting** at the edge (per-IP / per-token) — the spend cap limits cost, not request volume.
- **Dependency & image scanning** in CI (e.g. `pip-audit`, Trivy) before publishing images.

## Reporting

Security issues: open a private advisory on the GitHub repo rather than a public issue.
