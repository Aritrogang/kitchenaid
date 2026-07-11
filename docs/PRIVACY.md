# Privacy — TEMPLATE, needs review

> ⚠️ Profiles contain **health data** (allergies, medical diets). That is a sensitive category
> under GDPR (Art. 9) and CCPA/CPRA. This template documents the current handling and what a
> privacy/legal review must finalize **before launch**.

## What data we hold

| Data | Why | Where |
|---|---|---|
| Profile — allergies, diet, budget, skill, dislikes | to gate meals safely and personalize | `profile` store (Postgres or JSON) |
| Learned taste | to improve suggestions from feedback | `taste` store |
| `user_id` | to key the above | store + token subject |
| Spend ledger (model, tokens, cost, user) | cost control | ledger (file today) |

No passwords are stored here (auth issuance is delegated — see `SECURITY.md`). No payment data.

## Handling today

- **Access control:** with auth on, a user can only reach their own data (token identity).
- **Erasure:** `DELETE /profile/{user_id}` removes a user's profile and taste — a right-to-erasure
  primitive, tested. (The spend ledger is pseudonymous by `user_id`; include it in the erasure
  routine before launch.)
- **Encryption in transit:** TLS at the proxy (deployment responsibility).
- **Encryption at rest:** provide via the datastore/disk (e.g. RDS encryption, encrypted volumes)
  — configure at deploy time; app-level field encryption for allergies is a possible hardening.

## What review must finalize

- [ ] Published privacy policy (what's collected, why, retention, sharing = none by default).
- [ ] Lawful basis for processing health data (explicit consent under GDPR Art. 9).
- [ ] Data-retention window and automatic deletion of inactive accounts.
- [ ] DSAR flow (access/export/delete) — export endpoint to add alongside `DELETE`.
- [ ] Encryption-at-rest confirmed for the profile store and the ledger.
- [ ] Sub-processor list (Anthropic for generation) and a DPA where required.
- [ ] Cookie/telemetry disclosure for the web client.
