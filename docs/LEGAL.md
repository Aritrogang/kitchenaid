# Legal — TEMPLATE, NOT LEGAL ADVICE

> ⚠️ **This is scaffolding, not counsel.** An app that makes allergen/health claims carries real
> liability. A qualified lawyer must review and finalize the disclaimer, terms, and liability
> stance **before launch**. The text below is a starting point for that conversation.

## In-product disclaimer (already live)

Returned with every API answer (`disclaimer` field) and must be shown in every client:

> kitchenaid checks each dish against the allergies and diet in your profile, but it can't
> guarantee safety: ingredient labels and recipes change, and cross-contamination happens.
> Always read the packaging yourself, and consult a medical professional for medical dietary
> needs or a diagnosed allergy.

## Terms of Service — outline for counsel

- **Nature of service.** Assistive meal suggestions, not medical or dietary advice.
- **No warranty of safety.** The allergen gate is best-effort and fail-closed; the user remains
  responsible for verifying labels. Spell out the limits.
- **Limitation of liability** appropriate to a health-adjacent tool (counsel to draft).
- **Acceptable use**, account terms, termination, governing law.
- **Age / capacity** and, if minors may use it, parental-consent handling.

## Liability stance to decide with counsel

- Positioning: "assistive tool, verify yourself" vs. any stronger claim (the former is far safer).
- Whether to gate first use behind explicit acceptance of the disclaimer/terms.
- Insurance (product/professional liability) before serving real allergic users.

## Required before launch

- [ ] Lawyer-reviewed Terms of Service and disclaimer.
- [ ] Explicit user acceptance flow (clickwrap) recorded per user.
- [ ] Liability position + insurance confirmed.
- [ ] Allergen-data sign-off (see `ALLERGEN_DATA.md`) — legal and safety are intertwined here.
