# kitchenaid — web frontend

A tiny, static, **zero-build** browser client for the kitchenaid daily
kitchen-assistant API. Plain HTML + CSS + vanilla JS (ES modules). No npm, no
bundler, no framework — just serve the folder and open it.

```
web/
├── index.html   # markup, profile dialog, templates
├── styles.css   # warm "kitchen" design system (light + dark)
├── api.js        # fetch client for /health and /chat
├── store.js      # localStorage: profile, settings, stable user_id (uuid)
└── app.js        # UI controller: render chat, meal/grocery cards, trace panel
```

## Run it

### 1. Start the backend (from the repo root)

```bash
pip install fastapi uvicorn      # one-time
uvicorn kitchenaid.api:app        # serves http://localhost:8000
```

`kitchenaid/api.py` already enables permissive CORS (`allow_origins=["*"]`),
so a static page on another port can call it directly during local dev.

### 2. Serve this folder (in a second terminal)

```bash
cd web
python3 -m http.server 5500
```

### 3. Open it

<http://localhost:5500>

> **Why serve instead of double-clicking?** The app uses ES modules
> (`<script type="module">`), which browsers block over the `file://`
> protocol. A local HTTP server is required.

### Backend on a different host/port?

Open **Profile → Connection settings** and set the **API base URL**
(default `http://localhost:8000`). It's persisted in `localStorage`.

## Features

- **Profile setup** — name, 9 allergen chips, diet, budget, skill, dislikes.
  Saved to `localStorage`; a stable `user_id` (uuid) is generated and persisted
  so the backend can remember your taste across turns.
- **Chat** — type a request or tap a suggestion chip
  (*quick dinner*, *what to buy*, *plan my week*, *use up the fridge*).
  Each turn `POST`s `{user_id, query, profile}` to `/chat`.
- **Rich responses** — the assistant message plus, when present:
  - a **meal card** (name, cuisine, time, $/serving, calories, protein,
    "why" bullets, ingredient list, and any budget/nutrition **flags** shown as
    gentle warnings);
  - a **shopping list** (per-item quantity + cost, total, per-serving) with any
    **substitutions** (`original → replacement`, with the reason).
- **"How this was decided"** — a subtle collapsible panel per response that
  shows `agents_used`, whether an LLM was used, and the full agent handoff
  `trace` (agent → action → detail, with ms). This surfaces the multi-agent
  system without cluttering the conversation.
- **Health badge** — polls `/health`; shows how many agents are ready, or a
  clear "backend offline" state.
- **Graceful errors** — if the API is unreachable, you get a friendly message
  with the exact command to start the backend.
- **Accessible & responsive** — real `<label>`s, keyboard support, visible
  focus rings, good contrast, dark mode, and a layout that works on phones.
  Honors `prefers-reduced-motion`.

## Notes / assumptions

- Built against the documented API contract (the backend was not run during
  development). Optional profile fields (`budget_per_meal_usd`, `skill`,
  `dislikes`) are omitted from the request when empty rather than sent as null.
- All state is browser-local. Clearing site data resets your profile and
  generates a new `user_id`.
- No external assets or CDNs — everything is self-contained and works offline
  once the backend is reachable.
