// =========================================================================
// app.js — UI controller. Wires the composer + profile dialog to the API,
// renders chat messages, meal cards, grocery lists, and the trace panel.
// =========================================================================

import { sendChat, checkHealth, ApiError, normalizeBaseUrl } from "./api.js";
import {
  ALLERGENS, DEFAULT_API_URL,
  getUserId, getApiUrl, setApiUrl, getTheme, setTheme,
  loadProfile, saveProfile, hasProfile, toWireProfile,
} from "./store.js";

// ---------- Element handles ----------
const $ = (sel) => document.querySelector(sel);
const conversation = $("#conversation");
const composer = $("#composer");
const queryInput = $("#query-input");
const sendBtn = $("#send-btn");
const suggestions = $("#suggestions");
const healthBadge = $("#health-badge");
const healthLabel = healthBadge.querySelector(".health-label");
const themeBtn = $("#theme-btn");
const profileBtn = $("#profile-btn");
const dialog = $("#profile-dialog");
const profileForm = $("#profile-form");

// A11y-friendly labels for allergen chips (snake_case -> Title Case).
const ALLERGEN_LABELS = {
  peanut: "Peanut", tree_nut: "Tree nut", milk: "Milk", egg: "Egg",
  soy: "Soy", wheat: "Wheat", fish: "Fish", shellfish: "Shellfish", sesame: "Sesame",
};

// ---------- App state ----------
const userId = getUserId();
let inFlight = false; // guard against double-sends

// ============================================================
// Small DOM helpers
// ============================================================

/** Create an element with optional class, text and attributes. */
function el(tag, { cls, text, html, attrs } = {}) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  if (html != null) node.innerHTML = html;
  if (attrs) for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

/** Format money as $X.XX; tolerant of null/undefined. */
function money(n) {
  const v = Number(n);
  return Number.isFinite(v) ? `$${v.toFixed(2)}` : "—";
}

/** Round grams for display (whole numbers read cleaner on a list). */
function grams(g) {
  const v = Number(g);
  return Number.isFinite(v) ? `${Math.round(v)} g` : "";
}

/** Keep the conversation scrolled to the newest message. */
function scrollToEnd() {
  conversation.scrollTop = conversation.scrollHeight;
}

// ============================================================
// Rendering: user + assistant messages
// ============================================================

function renderUserMessage(text) {
  const msg = el("div", { cls: "msg msg--user" });
  msg.append(
    el("div", { cls: "avatar", text: "🧑‍🍳", attrs: { "aria-hidden": "true" } }),
    el("div", { cls: "bubble", text })
  );
  conversation.append(msg);
  scrollToEnd();
}

/** Insert the animated "thinking" indicator and return its node for removal. */
function renderTyping() {
  const tpl = $("#tpl-typing");
  const node = tpl.content.firstElementChild.cloneNode(true);
  conversation.append(node);
  scrollToEnd();
  return node;
}

/**
 * Render a full assistant turn: the message bubble, an optional meal card,
 * an optional grocery card, and the collapsible trace panel.
 */
function renderAssistantResponse(data) {
  const msg = el("div", { cls: "msg msg--assistant" });
  msg.append(el("div", { cls: "avatar", text: "🍳", attrs: { "aria-hidden": "true" } }));

  const stack = el("div", { cls: "msg-stack" });

  // Message text (may be multi-line — preserve line breaks as paragraphs).
  const bubble = el("div", { cls: "bubble" });
  const lines = String(data.message ?? "").split("\n");
  for (const line of lines) {
    // Empty lines become spacing; non-empty become <p>.
    if (line.trim() === "") continue;
    bubble.append(el("p", { text: line }));
  }
  if (!bubble.childElementCount) bubble.append(el("p", { text: "…" }));
  stack.append(bubble);

  if (data.meal) stack.append(renderMealCard(data.meal));
  if (data.grocery) stack.append(renderGroceryCard(data.grocery));

  // Trace panel — the multi-agent highlight.
  if (Array.isArray(data.trace) && data.trace.length) {
    stack.append(renderTrace(data));
  }

  msg.append(stack);
  conversation.append(msg);
  scrollToEnd();
}

/** Cuisine → emoji so meal cards get a quick visual anchor. */
const CUISINE_EMOJI = {
  american: "🍔", indian: "🍛", chinese: "🥡", thai: "🍜", mexican: "🌮",
  mediterranean: "🫒", french: "🥐", italian: "🍝", japanese: "🍱", greek: "🥗",
};

function renderMealCard(meal) {
  const card = el("div", { cls: "meal-card" });

  const head = el("div", { cls: "meal-head" });
  const emoji = CUISINE_EMOJI[String(meal.cuisine || "").toLowerCase()] || "🍽️";
  const titleRow = el("div", { cls: "meal-title-row" });
  titleRow.append(el("span", { cls: "meal-emoji", text: emoji, attrs: { "aria-hidden": "true" } }));
  titleRow.append(el("h3", { cls: "meal-title", text: meal.name || "Your meal" }));
  head.append(titleRow);
  const meta = [meal.cuisine, meal.time_min ? `${meal.time_min} min` : null,
    meal.servings ? `serves ${meal.servings}` : null].filter(Boolean).join(" · ");
  if (meta) head.append(el("p", { cls: "meal-cuisine", text: meta }));
  card.append(head);

  // Stat strip
  const stats = el("div", { cls: "meal-stats" });
  const stat = (value, label) => {
    const s = el("div", { cls: "stat" });
    s.append(el("div", { cls: "stat-value", text: value }));
    s.append(el("div", { cls: "stat-label", text: label }));
    return s;
  };
  stats.append(
    stat(money(meal.cost_per_serving_usd), "$ / serving"),
    stat(meal.time_min != null ? `${meal.time_min}m` : "—", "time"),
    stat(meal.calories_per_serving != null ? Math.round(meal.calories_per_serving) : "—", "cal / serv"),
    stat(meal.protein_per_serving_g != null ? `${Math.round(meal.protein_per_serving_g)}g` : "—", "protein"),
  );
  card.append(stats);

  const body = el("div", { cls: "meal-body" });

  // Gentle warning flags
  if (Array.isArray(meal.flags) && meal.flags.length) {
    const flags = el("div", { cls: "flags" });
    for (const f of meal.flags) flags.append(el("div", { cls: "flag", text: f }));
    body.append(flags);
  }

  // "Why" bullets
  if (Array.isArray(meal.why) && meal.why.length) {
    const why = el("ul", { cls: "why-list" });
    for (const w of meal.why) why.append(el("li", { text: w }));
    body.append(why);
  }

  // Ingredients
  if (Array.isArray(meal.ingredients) && meal.ingredients.length) {
    const wrap = el("div");
    wrap.append(el("div", { cls: "section-label", text: "Ingredients" }));
    const list = el("ul", { cls: "ingredient-list" });
    for (const ing of meal.ingredients) {
      const li = el("li");
      li.append(el("span", { cls: "name", text: ing.item }));
      li.append(el("span", { cls: "qty", text: grams(ing.grams) }));
      list.append(li);
    }
    wrap.append(list);
    body.append(wrap);
  }

  // One-tap feedback → the Taster learns and future ranking shifts.
  const fb = el("div", { cls: "feedback-bar" });
  fb.append(el("span", { cls: "feedback-label", text: "How was it?" }));
  const fbBtn = (emoji, label, query) => {
    const b = el("button", { cls: "fb-btn", attrs: { type: "button" } });
    b.append(el("span", { text: emoji, attrs: { "aria-hidden": "true" } }));
    b.append(document.createTextNode(` ${label}`));
    b.addEventListener("click", () => {
      if (inFlight) return; // don't show "sent" state for a turn that would silently no-op
      fb.querySelectorAll(".fb-btn").forEach((x) => (x.disabled = true));
      b.classList.add("fb-btn--chosen");
      submitQuery(query);
    });
    return b;
  };
  fb.append(
    fbBtn("😍", "Loved it", `loved the ${meal.name}`),
    fbBtn("🌶️", "Too spicy", `the ${meal.name} was too spicy`),
    fbBtn("⏱️", "Took too long", `the ${meal.name} took too long`),
  );
  body.append(fb);

  card.append(body);
  return card;
}

function renderGroceryCard(grocery) {
  const card = el("div", { cls: "grocery-card" });

  const head = el("div", { cls: "grocery-head" });
  head.append(el("span", { text: "🛒", attrs: { "aria-hidden": "true" } }));
  head.append(el("h3", { text: "Shopping list" }));

  // Copy the list as plain text — the small utility people actually use.
  const copyBtn = el("button", { cls: "copy-btn", attrs: { type: "button", "aria-label": "Copy shopping list" } });
  copyBtn.textContent = "⧉ Copy";
  copyBtn.addEventListener("click", async () => {
    const lines = (grocery.items || []).map((i) => `${Math.round(i.grams)}g ${i.item} (${money(i.est_cost_usd)})`);
    lines.push(`Total: ${money(grocery.total_cost_usd)}`);
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      copyBtn.textContent = "✓ Copied";
    } catch {
      copyBtn.textContent = "✗ Can't copy";
    }
    setTimeout(() => (copyBtn.textContent = "⧉ Copy"), 1600);
  });
  head.append(copyBtn);
  card.append(head);

  const body = el("div", { cls: "grocery-body" });

  if (Array.isArray(grocery.items) && grocery.items.length) {
    const list = el("ul", { cls: "grocery-list" });
    for (const item of grocery.items) {
      const li = el("li");
      li.append(el("span", { cls: "g-item", text: item.item }));
      li.append(el("span", { cls: "g-qty", text: grams(item.grams) }));
      li.append(el("span", { cls: "g-cost", text: money(item.est_cost_usd) }));
      list.append(li);
    }
    body.append(list);
  }

  // Total + per-serving
  const total = el("div", { cls: "grocery-total" });
  total.append(el("span", { text: "Total" }));
  const right = el("span");
  right.append(el("span", { cls: "amount", text: money(grocery.total_cost_usd) }));
  if (grocery.cost_per_serving_usd != null) {
    right.append(el("span", { cls: "per-serving", text: ` (${money(grocery.cost_per_serving_usd)}/serving)` }));
  }
  total.append(right);
  body.append(total);

  // Substitutions
  if (Array.isArray(grocery.substitutions) && grocery.substitutions.length) {
    const subs = el("div", { cls: "subs" });
    subs.append(el("div", { cls: "section-label", text: "Smart swaps" }));
    for (const s of grocery.substitutions) {
      const row = el("div", { cls: "sub" });
      row.append(el("span", { cls: "from", text: s.original }));
      row.append(el("span", { cls: "arrow", text: "→", attrs: { "aria-hidden": "true" } }));
      row.append(el("span", { cls: "to", text: s.replacement }));
      if (s.reason) row.append(el("span", { cls: "reason", text: s.reason }));
      subs.append(row);
    }
    body.append(subs);
  }

  card.append(body);
  return card;
}

/**
 * The collapsible "how this was decided" panel. A subtle button expands a
 * panel listing agents_used / used_llm plus each handoff step with its ms.
 */
/** Per-agent identity for the pipeline strip. */
const AGENT_META = {
  Concierge:  { emoji: "🎩", cls: "agent--concierge" },
  Chef:       { emoji: "👨‍🍳", cls: "agent--chef" },
  Dietitian:  { emoji: "🛡️", cls: "agent--dietitian" },
  Shopper:    { emoji: "🛒", cls: "agent--shopper" },
  Taster:     { emoji: "👅", cls: "agent--taster" },
};

let traceSeq = 0;
function renderTrace(data) {
  const id = `trace-${++traceSeq}`;
  const wrap = el("div", { cls: "trace" });

  // Always-visible pipeline strip: which agents touched this answer, in order.
  const strip = el("div", { cls: "pipeline", attrs: { "aria-label": "Agents involved" } });
  const seen = [];
  for (const step of data.trace) {
    if (!seen.includes(step.agent)) seen.push(step.agent);
  }
  seen.forEach((name, i) => {
    if (i > 0) strip.append(el("span", { cls: "pipe-arrow", text: "→", attrs: { "aria-hidden": "true" } }));
    const meta = AGENT_META[name] || { emoji: "⚙️", cls: "" };
    const chipEl = el("span", { cls: `agent-chip ${meta.cls}` });
    chipEl.append(el("span", { text: meta.emoji, attrs: { "aria-hidden": "true" } }));
    chipEl.append(document.createTextNode(` ${name}`));
    strip.append(chipEl);
  });
  strip.append(el("span", {
    cls: `pipe-llm ${data.used_llm ? "pipe-llm--on" : ""}`,
    text: data.used_llm ? "LLM" : "no LLM",
    attrs: { title: data.used_llm ? "This turn used a language model" : "Fully deterministic turn — no model call" },
  }));
  wrap.append(strip);

  const toggle = el("button", {
    cls: "trace-toggle",
    attrs: { type: "button", "aria-expanded": "false", "aria-controls": id },
  });
  toggle.append(el("span", { cls: "chevron", text: "▸", attrs: { "aria-hidden": "true" } }));
  toggle.append(document.createTextNode("How this was decided "));
  toggle.append(el("span", { cls: "trace-badge", text: `${data.agents_used ?? data.trace.length} agents` }));

  const panel = el("div", { cls: "trace-panel", attrs: { id, hidden: "" } });

  // Meta pills
  const meta = el("div", { cls: "trace-meta" });
  if (data.intent) meta.append(el("span", { cls: "pill", text: `intent: ${data.intent}` }));
  meta.append(el("span", { cls: "pill", text: `${data.agents_used ?? data.trace.length} agents used` }));
  meta.append(el("span", {
    cls: `pill ${data.used_llm ? "llm-on" : ""}`,
    text: data.used_llm ? "LLM assisted" : "deterministic (no LLM)",
  }));
  panel.append(meta);

  // Steps
  const steps = el("ol", { cls: "trace-steps" });
  for (const step of data.trace) {
    const li = el("li", { cls: "trace-step" });
    li.append(el("span", { cls: "trace-agent", text: step.agent }));
    const detail = el("span", { cls: "trace-detail" });
    detail.append(el("span", { cls: "action", text: step.action }));
    if (step.detail) detail.append(document.createTextNode(` — ${step.detail}`));
    li.append(detail);
    const ms = Number(step.ms);
    li.append(el("span", { cls: "trace-ms", text: Number.isFinite(ms) ? `${ms.toFixed(1)} ms` : "" }));
    steps.append(li);
  }
  panel.append(steps);

  toggle.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!open));
    panel.hidden = open;
    if (!open) scrollToEnd();
  });

  wrap.append(toggle, panel);
  return wrap;
}

/** Friendly, actionable error card (backend down vs. other errors). */
function renderError(err) {
  const msg = el("div", { cls: "msg msg--assistant" });
  msg.append(el("div", { cls: "avatar", text: "🍳", attrs: { "aria-hidden": "true" } }));

  const note = el("div", { cls: "error-note" });
  if (err instanceof ApiError && err.unreachable) {
    note.innerHTML = `
      <p><strong>I can't reach the kitchen right now.</strong></p>
      <p>The backend doesn't seem to be running at <code>${escapeHtml(getApiUrl())}</code>.</p>
      <p>Start it from the repo root with
        <code>uvicorn kitchenaid.api:app</code>, then try again.
        If it's running elsewhere, update the API URL in your Profile → Connection settings.</p>`;
  } else {
    const text = err instanceof ApiError ? err.message : "Something went wrong on this turn.";
    note.innerHTML = `<p><strong>Sorry — ${escapeHtml(text)}</strong></p>
      <p>Please try again in a moment.</p>`;
  }
  msg.append(note);
  conversation.append(msg);
  scrollToEnd();
}

/** Minimal HTML escaping for the few spots we build markup by string. */
function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ============================================================
// Welcome state
// ============================================================

function renderWelcome() {
  const name = loadProfile().name;
  const greeting = name ? `Welcome back, ${escapeHtml(name)}!` : "Welcome to kitchenaid";
  const welcome = el("div", { cls: "welcome", attrs: { id: "welcome" } });
  welcome.innerHTML = `
    <span class="wave" aria-hidden="true">🍳</span>
    <h2>${greeting}</h2>
    <p>Tell me what you're in the mood for and a small team of kitchen agents — a chef,
       a safety-checking dietitian, a shopper — will put dinner together.</p>
    <div class="welcome-cards" role="group" aria-label="Example requests">
      <button class="example-card" type="button" data-query="quick dinner, I have chicken and spinach, 20 minutes">
        <span class="ex-emoji" aria-hidden="true">⏱️</span>
        <span class="ex-title">Beat the clock</span>
        <span class="ex-sub">“Quick dinner — chicken, spinach, 20 min”</span>
      </button>
      <button class="example-card" type="button" data-query="what do I need to buy for dinner with rice?">
        <span class="ex-emoji" aria-hidden="true">🛒</span>
        <span class="ex-title">Build my list</span>
        <span class="ex-sub">“What do I need to buy for dinner?”</span>
      </button>
      <button class="example-card" type="button" data-query="plan my week">
        <span class="ex-emoji" aria-hidden="true">📅</span>
        <span class="ex-title">Plan the week</span>
        <span class="ex-sub">“Plan my week”</span>
      </button>
    </div>
    <p class="welcome-note">Allergies in your profile are <strong>hard rules</strong> — a
       deterministic gate checks every dish, every time.</p>`;
  welcome.querySelectorAll(".example-card").forEach((cardBtn) => {
    cardBtn.addEventListener("click", () => submitQuery(cardBtn.dataset.query));
  });
  conversation.append(welcome);
}

/** Always-visible pills for the hard rules the gate is enforcing right now. */
function renderSafetyStrip() {
  const strip = $("#safety-strip");
  const p = loadProfile();
  const pills = [];
  for (const a of p.allergies || []) {
    pills.push(`<button class="safety-pill safety-pill--allergy" type="button" title="Hard rule — the Dietitian rejects any dish containing this">🚫 ${escapeHtml(ALLERGEN_LABELS[a] || a)}</button>`);
  }
  if (p.diet && p.diet !== "none") {
    pills.push(`<button class="safety-pill safety-pill--diet" type="button" title="Dietary rule — enforced on every dish">🌿 ${escapeHtml(p.diet)}</button>`);
  }
  if (p.budget_per_meal_usd != null && p.budget_per_meal_usd !== "") {
    pills.push(`<button class="safety-pill" type="button" title="Soft goal — flagged when over">💵 $${Number(p.budget_per_meal_usd).toFixed(2)}/meal</button>`);
  }
  strip.innerHTML = pills.join("");
  strip.hidden = pills.length === 0;
  strip.querySelectorAll(".safety-pill").forEach((b) => b.addEventListener("click", openProfile));
}

function clearWelcome() {
  document.querySelector("#welcome")?.remove();
}

// ============================================================
// Sending a turn
// ============================================================

async function submitQuery(rawQuery) {
  const query = rawQuery.trim();
  if (!query || inFlight) return;

  clearWelcome();
  renderUserMessage(query);
  queryInput.value = "";
  setBusy(true);

  const typing = renderTyping();
  const profile = toWireProfile(loadProfile(), userId);

  try {
    const data = await sendChat(getApiUrl(), { user_id: userId, query, profile });
    typing.remove();
    renderAssistantResponse(data);
    // A successful turn proves the backend is up — recover the badge if it was down.
    if (!healthBadge.classList.contains("health-badge--ok")) refreshHealth();
  } catch (err) {
    typing.remove();
    renderError(err);
    // A failed turn is a good moment to re-check the health badge.
    refreshHealth();
  } finally {
    setBusy(false);
    queryInput.focus();
  }
}

function setBusy(busy) {
  inFlight = busy;
  sendBtn.disabled = busy;
  queryInput.disabled = busy;
}

// ============================================================
// Health badge
// ============================================================

async function refreshHealth() {
  setHealth("unknown", "Checking…");
  try {
    const data = await checkHealth(getApiUrl());
    const n = Array.isArray(data.agents) ? data.agents.length : 0;
    setHealth("ok", n ? `${n} agents ready` : "Connected");
    healthBadge.title = Array.isArray(data.agents)
      ? `Backend online — agents: ${data.agents.join(", ")}`
      : "Backend online";
  } catch {
    setHealth("down", "Backend offline");
    healthBadge.title = `Can't reach ${getApiUrl()} — start the backend with 'uvicorn kitchenaid.api:app'`;
  }
}

function setHealth(state, label) {
  healthBadge.className = `health-badge health-badge--${state}`;
  healthLabel.textContent = label;
}

// ============================================================
// Theme
// ============================================================

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const isDark = theme === "dark";
  themeBtn.setAttribute("aria-pressed", String(isDark));
  themeBtn.querySelector(".theme-icon").textContent = isDark ? "☀️" : "🌙";
}

themeBtn.addEventListener("click", () => {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  setTheme(next);
  applyTheme(next);
});

// ============================================================
// Profile dialog
// ============================================================

/** Build the 9 allergen toggle chips into the dialog once. */
function buildAllergenChips() {
  const host = $("#pf-allergies");
  host.innerHTML = "";
  for (const a of ALLERGENS) {
    const label = el("label", { cls: "allergen" });
    const input = el("input", { attrs: { type: "checkbox", name: "allergy", value: a } });
    label.append(input, document.createTextNode(ALLERGEN_LABELS[a] || a));
    host.append(label);
  }
}

/** Copy the stored profile into the dialog form fields. */
function fillProfileForm() {
  const p = loadProfile();
  profileForm.name.value = p.name;
  profileForm.diet.value = p.diet;
  profileForm.budget.value = p.budget_per_meal_usd ?? "";
  profileForm.skill.value = p.skill;
  profileForm.dislikes.value = (p.dislikes || []).join(", ");
  $("#pf-api").value = getApiUrl();
  const set = new Set(p.allergies || []);
  for (const box of profileForm.querySelectorAll('input[name="allergy"]')) {
    box.checked = set.has(box.value);
  }
}

/** Read the dialog form into a stored-profile shape and persist it. */
function readAndSaveProfile() {
  const allergies = [...profileForm.querySelectorAll('input[name="allergy"]:checked')].map((b) => b.value);
  const dislikes = profileForm.dislikes.value
    .split(",").map((s) => s.trim()).filter(Boolean);
  const budgetRaw = profileForm.budget.value.trim();

  const profile = {
    name: profileForm.name.value.trim(),
    allergies,
    diet: profileForm.diet.value || "none",
    budget_per_meal_usd: budgetRaw === "" ? null : Number(budgetRaw),
    skill: profileForm.skill.value || "",
    dislikes,
  };
  saveProfile(profile);

  // Connection settings live alongside the profile in the dialog.
  const apiUrl = normalizeBaseUrl($("#pf-api").value) || DEFAULT_API_URL;
  setApiUrl(apiUrl);
}

function openProfile() {
  fillProfileForm();
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", ""); // very old fallback
  profileForm.name.focus();
}

function closeProfile() {
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
}

profileBtn.addEventListener("click", openProfile);
$("#profile-cancel").addEventListener("click", closeProfile);
$("#profile-cancel-2").addEventListener("click", closeProfile);

// Submit = save. The form uses method="dialog"; we intercept to persist first.
profileForm.addEventListener("submit", (e) => {
  // Only the Save button should persist; Cancel buttons are type="button".
  if (e.submitter && e.submitter.id !== "profile-save") return;
  readAndSaveProfile();
  applyPostProfileState();
  // let the dialog close naturally via method="dialog"
});

/** After a profile save, refresh anything that depends on it. */
function applyPostProfileState() {
  refreshHealth(); // API URL may have changed
  renderSafetyStrip(); // hard rules may have changed
  // If the conversation is still just the welcome card, refresh its greeting.
  if (document.querySelector("#welcome")) {
    clearWelcome();
    renderWelcome();
  }
}

// ============================================================
// Wiring: composer + suggestion chips
// ============================================================

composer.addEventListener("submit", (e) => {
  e.preventDefault();
  submitQuery(queryInput.value);
});

suggestions.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  submitQuery(chip.dataset.query || chip.textContent);
});

// ============================================================
// Boot
// ============================================================

function boot() {
  applyTheme(getTheme());
  buildAllergenChips();
  renderWelcome();
  renderSafetyStrip();
  refreshHealth();

  // First-time users: nudge them to set up a profile.
  if (!hasProfile()) {
    // Defer so the dialog opens after the first paint (feels smoother).
    setTimeout(openProfile, 350);
  }

  queryInput.focus();
}

boot();
