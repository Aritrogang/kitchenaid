// =========================================================================
// app.js — UI controller. Composable render functions over a single state
// source (store.js). No framework, no emojis: inline SVG icons via <use>.
// =========================================================================

import { sendChat, checkHealth, fetchAgents, ApiError, normalizeBaseUrl } from "./api.js";
import {
  ALLERGENS, DEFAULT_API_URL,
  getUserId, getApiUrl, setApiUrl, getTheme, setTheme,
  loadProfile, saveProfile, hasProfile, toWireProfile,
  loadAgentOptions, setAgentOption,
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
const agentsBtn = $("#agents-btn");
const dialog = $("#profile-dialog");
const agentsDialog = $("#agents-dialog");
const agentsBody = $("#agents-body");
const profileForm = $("#profile-form");
const creativeIndicator = $("#creative-indicator");

const ALLERGEN_LABELS = {
  peanut: "Peanut", tree_nut: "Tree nut", milk: "Milk", egg: "Egg",
  soy: "Soy", wheat: "Wheat", fish: "Fish", shellfish: "Shellfish", sesame: "Sesame",
};

// ---------- App state ----------
const userId = getUserId();
let inFlight = false;        // guard against double-sends
let agentTeam = null;        // cached GET /agents payload

// ============================================================
// Small DOM helpers
// ============================================================

function el(tag, { cls, text, html, attrs } = {}) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  if (html != null) node.innerHTML = html;
  if (attrs) for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

/** Inline SVG icon referencing the sprite in index.html. */
function icon(name, cls = "icon") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

function money(n) {
  const v = Number(n);
  return Number.isFinite(v) ? `$${v.toFixed(2)}` : "—";
}

function grams(g) {
  const v = Number(g);
  return Number.isFinite(v) ? `${Math.round(v)} g` : "";
}

function scrollToEnd() {
  conversation.scrollTop = conversation.scrollHeight;
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ============================================================
// Messages
// ============================================================

function renderUserMessage(text) {
  const msg = el("div", { cls: "msg msg--user" });
  const avatar = el("div", { cls: "avatar", attrs: { "aria-hidden": "true" } });
  avatar.append(icon("user", "icon icon--sm"));
  msg.append(avatar, el("div", { cls: "bubble", text }));
  conversation.append(msg);
  scrollToEnd();
}

function renderTyping() {
  const tpl = $("#tpl-typing");
  const node = tpl.content.firstElementChild.cloneNode(true);
  conversation.append(node);
  scrollToEnd();
  return node;
}

function renderAssistantResponse(data) {
  const msg = el("div", { cls: "msg msg--assistant" });
  const avatar = el("div", { cls: "avatar", attrs: { "aria-hidden": "true" } });
  avatar.append(icon("pot", "icon icon--sm"));
  msg.append(avatar);

  const stack = el("div", { cls: "msg-stack" });

  const bubble = el("div", { cls: "bubble" });
  for (const line of String(data.message ?? "").split("\n")) {
    if (line.trim() === "") continue;
    bubble.append(el("p", { text: line }));
  }
  if (!bubble.childElementCount) bubble.append(el("p", { text: "…" }));
  stack.append(bubble);

  if (data.meal) stack.append(renderMealCard(data.meal));
  if (data.grocery) stack.append(renderGroceryCard(data.grocery));
  if (Array.isArray(data.trace) && data.trace.length) stack.append(renderTrace(data));

  msg.append(stack);
  conversation.append(msg);
  scrollToEnd();
}

// ============================================================
// Meal card
// ============================================================

function renderMealCard(meal) {
  const card = el("div", { cls: "meal-card" });

  const head = el("div", { cls: "meal-head" });
  head.append(el("h3", { cls: "meal-title", text: meal.name || "Your meal" }));
  const meta = [meal.cuisine, meal.time_min ? `${meal.time_min} min` : null,
    meal.servings ? `serves ${meal.servings}` : null].filter(Boolean).join(" · ");
  if (meta) head.append(el("p", { cls: "meal-cuisine", text: meta }));
  card.append(head);

  const stats = el("div", { cls: "meal-stats" });
  const stat = (value, label) => {
    const s = el("div", { cls: "stat" });
    s.append(el("div", { cls: "stat-value", text: value }));
    s.append(el("div", { cls: "stat-label", text: label }));
    return s;
  };
  stats.append(
    stat(money(meal.cost_per_serving_usd), "per serving"),
    stat(meal.time_min != null ? `${meal.time_min}m` : "—", "time"),
    stat(meal.calories_per_serving != null ? Math.round(meal.calories_per_serving) : "—", "calories"),
    stat(meal.protein_per_serving_g != null ? `${Math.round(meal.protein_per_serving_g)}g` : "—", "protein"),
  );
  card.append(stats);

  const body = el("div", { cls: "meal-body" });

  if (Array.isArray(meal.flags) && meal.flags.length) {
    const flags = el("div", { cls: "flags" });
    for (const f of meal.flags) {
      const flag = el("div", { cls: "flag" });
      flag.append(icon("alert", "icon icon--sm"), el("span", { text: f }));
      flags.append(flag);
    }
    body.append(flags);
  }

  if (Array.isArray(meal.why) && meal.why.length) {
    const why = el("ul", { cls: "why-list" });
    for (const w of meal.why) why.append(el("li", { text: w }));
    body.append(why);
  }

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

  // One-tap feedback -> the Taster. Guarded against in-flight turns so the UI
  // never shows a "sent" state for a click that silently no-ops.
  const fb = el("div", { cls: "feedback-bar" });
  fb.append(el("span", { cls: "feedback-label", text: "How was it?" }));
  const fbBtn = (label, query) => {
    const b = el("button", { cls: "fb-btn", text: label, attrs: { type: "button" } });
    b.addEventListener("click", () => {
      if (inFlight) return;
      fb.querySelectorAll(".fb-btn").forEach((x) => (x.disabled = true));
      b.classList.add("fb-btn--chosen");
      submitQuery(query);
    });
    return b;
  };
  fb.append(
    fbBtn("Loved it", `loved the ${meal.name}`),
    fbBtn("Too spicy", `the ${meal.name} was too spicy`),
    fbBtn("Took too long", `the ${meal.name} took too long`),
  );
  body.append(fb);

  card.append(body);
  return card;
}

// ============================================================
// Grocery card
// ============================================================

function renderGroceryCard(grocery) {
  const card = el("div", { cls: "grocery-card" });

  const head = el("div", { cls: "grocery-head" });
  head.append(icon("cart", "icon"));
  head.append(el("h3", { text: "Shopping list" }));

  const copyBtn = el("button", { cls: "copy-btn", attrs: { type: "button", "aria-label": "Copy shopping list" } });
  copyBtn.append(icon("copy", "icon icon--sm"), el("span", { text: "Copy" }));
  copyBtn.addEventListener("click", async () => {
    const lines = (grocery.items || []).map((i) => `${Math.round(i.grams)}g ${i.item} (${money(i.est_cost_usd)})`);
    lines.push(`Total: ${money(grocery.total_cost_usd)}`);
    const label = copyBtn.querySelector("span");
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      label.textContent = "Copied";
    } catch {
      label.textContent = "Copy failed";
    }
    setTimeout(() => (label.textContent = "Copy"), 1600);
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

  const total = el("div", { cls: "grocery-total" });
  total.append(el("span", { text: "Total" }));
  const right = el("span");
  right.append(el("span", { cls: "amount", text: money(grocery.total_cost_usd) }));
  if (grocery.cost_per_serving_usd != null) {
    right.append(el("span", { cls: "per-serving", text: ` (${money(grocery.cost_per_serving_usd)}/serving)` }));
  }
  total.append(right);
  body.append(total);

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

// ============================================================
// Trace: pipeline strip + collapsible detail
// ============================================================

const AGENT_CLS = {
  Concierge: "agent--concierge",
  Chef: "agent--chef",
  Dietitian: "agent--dietitian",
  Shopper: "agent--shopper",
  Taster: "agent--taster",
};

let traceSeq = 0;
function renderTrace(data) {
  const id = `trace-${++traceSeq}`;
  const wrap = el("div", { cls: "trace" });

  // Always-visible pipeline: which agents touched this answer, in order.
  const strip = el("div", { cls: "pipeline", attrs: { "aria-label": "Agents involved" } });
  const seen = [];
  for (const step of data.trace) if (!seen.includes(step.agent)) seen.push(step.agent);
  seen.forEach((name, i) => {
    if (i > 0) strip.append(el("span", { cls: "pipe-arrow", text: "→", attrs: { "aria-hidden": "true" } }));
    strip.append(el("span", { cls: `agent-chip ${AGENT_CLS[name] || ""}`, text: name }));
  });
  strip.append(el("span", {
    cls: `pipe-llm ${data.used_llm ? "pipe-llm--on" : ""}`,
    text: data.used_llm ? "AI" : "deterministic",
    attrs: { title: data.used_llm ? "A language model helped create this answer" : "Fully deterministic turn — no model call" },
  }));
  wrap.append(strip);

  const toggle = el("button", {
    cls: "trace-toggle",
    attrs: { type: "button", "aria-expanded": "false", "aria-controls": id },
  });
  toggle.append(icon("chevron", "icon icon--xs chevron"));
  toggle.append(el("span", { text: "How this was decided" }));
  toggle.append(el("span", { cls: "trace-badge", text: `${data.agents_used ?? data.trace.length} agents` }));

  const panel = el("div", { cls: "trace-panel", attrs: { id, hidden: "" } });

  const meta = el("div", { cls: "trace-meta" });
  if (data.intent) meta.append(el("span", { cls: "pill", text: `intent: ${data.intent}` }));
  meta.append(el("span", { cls: "pill", text: `${data.agents_used ?? data.trace.length} agents used` }));
  meta.append(el("span", {
    cls: `pill ${data.used_llm ? "llm-on" : ""}`,
    text: data.used_llm ? "AI assisted" : "no model call",
  }));
  panel.append(meta);

  const steps = el("ol", { cls: "trace-steps" });
  for (const step of data.trace) {
    const li = el("li", { cls: "trace-step" });
    li.append(el("span", { cls: `trace-agent ${AGENT_CLS[step.agent] || ""}`, text: step.agent }));
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

// ============================================================
// Errors
// ============================================================

function renderError(err) {
  const msg = el("div", { cls: "msg msg--assistant" });
  const avatar = el("div", { cls: "avatar", attrs: { "aria-hidden": "true" } });
  avatar.append(icon("pot", "icon icon--sm"));
  msg.append(avatar);

  const note = el("div", { cls: "error-note" });
  if (err instanceof ApiError && err.unreachable) {
    note.innerHTML = `
      <p><strong>I can't reach the kitchen right now.</strong></p>
      <p>The backend doesn't seem to be running at <code>${escapeHtml(getApiUrl())}</code>.</p>
      <p>Start it from the repo root with <code>uvicorn kitchenaid.api:app</code>, then try
        again. If it's running elsewhere, update the API URL in Profile → Connection settings.</p>`;
  } else {
    const text = err instanceof ApiError ? err.message : "Something went wrong on this turn.";
    note.innerHTML = `<p><strong>Sorry — ${escapeHtml(text)}</strong></p>
      <p>Please try again in a moment.</p>`;
  }
  msg.append(note);
  conversation.append(msg);
  scrollToEnd();
}

// ============================================================
// Welcome + safety strip
// ============================================================

function renderWelcome() {
  const name = loadProfile().name;
  const greeting = name ? `Welcome back, ${escapeHtml(name)}` : "Welcome to kitchenaid";
  const welcome = el("div", { cls: "welcome", attrs: { id: "welcome" } });
  welcome.innerHTML = `
    <h2>${greeting}</h2>
    <p>Tell me what you're in the mood for and a small team of kitchen agents — a chef,
       a safety-checking dietitian, a shopper — will put dinner together.</p>
    <div class="welcome-cards" role="group" aria-label="Example requests">
      <button class="example-card" type="button" data-query="quick dinner, I have chicken and spinach, 20 minutes">
        <svg viewBox="0 0 24 24" class="icon ex-icon" aria-hidden="true"><use href="#i-clock"/></svg>
        <span class="ex-title">Beat the clock</span>
        <span class="ex-sub">Quick dinner — chicken, spinach, 20 min</span>
      </button>
      <button class="example-card" type="button" data-query="what do I need to buy for dinner with rice?">
        <svg viewBox="0 0 24 24" class="icon ex-icon" aria-hidden="true"><use href="#i-cart"/></svg>
        <span class="ex-title">Build my list</span>
        <span class="ex-sub">What do I need to buy for dinner?</span>
      </button>
      <button class="example-card" type="button" data-query="plan my week">
        <svg viewBox="0 0 24 24" class="icon ex-icon" aria-hidden="true"><use href="#i-calendar"/></svg>
        <span class="ex-title">Plan the week</span>
        <span class="ex-sub">Five dinners, no repeats</span>
      </button>
    </div>
    <p class="welcome-note">Allergies in your profile are <strong>hard rules</strong> — a
       deterministic gate checks every dish, every time.</p>`;
  welcome.querySelectorAll(".example-card").forEach((cardBtn) => {
    cardBtn.addEventListener("click", () => submitQuery(cardBtn.dataset.query));
  });
  conversation.append(welcome);
}

function clearWelcome() {
  document.querySelector("#welcome")?.remove();
}

function renderSafetyStrip() {
  const strip = $("#safety-strip");
  const p = loadProfile();
  strip.textContent = "";
  const pill = (cls, iconName, label, title) => {
    const b = el("button", { cls: `safety-pill ${cls}`, attrs: { type: "button", title } });
    b.append(icon(iconName, "icon icon--xs"), el("span", { text: label }));
    b.addEventListener("click", openProfile);
    return b;
  };
  for (const a of p.allergies || []) {
    strip.append(pill("safety-pill--allergy", "ban", ALLERGEN_LABELS[a] || a,
      "Hard rule — the Dietitian rejects any dish containing this"));
  }
  if (p.diet && p.diet !== "none") {
    strip.append(pill("safety-pill--diet", "leaf", p.diet, "Dietary rule — enforced on every dish"));
  }
  if (p.budget_per_meal_usd != null && p.budget_per_meal_usd !== "") {
    strip.append(pill("", "cart", `$${Number(p.budget_per_meal_usd).toFixed(2)}/meal`,
      "Soft goal — flagged when over"));
  }
  strip.hidden = strip.childElementCount === 0;
}

// ============================================================
// Agents panel
// ============================================================

async function loadAgentTeam() {
  if (agentTeam) return agentTeam;
  const data = await fetchAgents(getApiUrl());
  agentTeam = Array.isArray(data.agents) ? data.agents : [];
  return agentTeam;
}

function renderAgentsPanel(team) {
  const opts = loadAgentOptions();
  agentsBody.textContent = "";

  for (const a of team) {
    const row = el("div", { cls: `agent-row ${a.id === "dietitian" ? "agent-row--safety" : ""}` });

    const head = el("div", { cls: "agent-row-head" });
    const title = el("div", { cls: "agent-row-title" });
    const nameEl = el("span", { cls: `agent-name ${AGENT_CLS[a.name] || ""}`, text: a.name });
    title.append(nameEl, el("span", { cls: "agent-role", text: a.role }));
    head.append(title);

    if (a.toggleable && a.toggle_key) {
      const sw = el("button", {
        cls: "switch",
        attrs: {
          type: "button", role: "switch", "aria-checked": String(Boolean(opts[a.toggle_key])),
          "aria-label": a.toggle_label || `Toggle ${a.name}`,
        },
      });
      sw.append(el("span", { cls: "switch-knob", attrs: { "aria-hidden": "true" } }));
      sw.addEventListener("click", () => {
        const next = sw.getAttribute("aria-checked") !== "true";
        sw.setAttribute("aria-checked", String(next));
        setAgentOption(a.toggle_key, next);
        syncCreativeIndicator();
      });
      head.append(sw);
    } else {
      const lock = el("span", { cls: "agent-lock", attrs: { title: a.always_on_reason || "Always on" } });
      lock.append(icon("lock", "icon icon--xs"), el("span", { text: "always on" }));
      head.append(lock);
    }
    row.append(head);

    if (a.toggleable && a.toggle_label) {
      row.append(el("p", { cls: "agent-toggle-label", text: a.toggle_label }));
    }
    if (!a.toggleable && a.always_on_reason) {
      row.append(el("p", { cls: "agent-reason", text: a.always_on_reason }));
    }

    // Expandable detail — keyboard-accessible disclosure.
    const detailId = `agent-detail-${a.id}`;
    const more = el("button", {
      cls: "agent-more",
      attrs: { type: "button", "aria-expanded": "false", "aria-controls": detailId },
    });
    more.append(icon("chevron", "icon icon--xs chevron"), el("span", { text: "What it does" }));
    const detail = el("p", { cls: "agent-detail", text: a.detail || "", attrs: { id: detailId, hidden: "" } });
    more.addEventListener("click", () => {
      const open = more.getAttribute("aria-expanded") === "true";
      more.setAttribute("aria-expanded", String(!open));
      detail.hidden = open;
    });
    row.append(more, detail);

    if (a.id === "chef") {
      row.append(el("p", { cls: "agent-note",
        text: "Creative mode uses a language model to invent dishes from your exact words. Every result still passes the safety gate." }));
    }

    agentsBody.append(row);
  }
}

async function openAgents() {
  try {
    const team = await loadAgentTeam();
    renderAgentsPanel(team);
  } catch {
    agentsBody.textContent = "";
    agentsBody.append(el("p", { cls: "agent-reason",
      text: `Can't load the team — is the backend running at ${getApiUrl()}?` }));
  }
  if (typeof agentsDialog.showModal === "function") agentsDialog.showModal();
  else agentsDialog.setAttribute("open", "");
}

function closeAgents() {
  if (typeof agentsDialog.close === "function") agentsDialog.close();
  else agentsDialog.removeAttribute("open");
}

/** The composer-area banner shown while Creative mode is on. */
function syncCreativeIndicator() {
  creativeIndicator.hidden = !loadAgentOptions().creative_chef;
}

agentsBtn.addEventListener("click", openAgents);
$("#agents-close").addEventListener("click", closeAgents);
creativeIndicator.addEventListener("click", openAgents);

// ============================================================
// Sending a turn
// ============================================================

async function submitQuery(rawQuery) {
  const query = (rawQuery ?? "").trim();
  if (!query || inFlight) return;

  clearWelcome();
  renderUserMessage(query);
  queryInput.value = "";
  setBusy(true);

  const typing = renderTyping();
  const profile = toWireProfile(loadProfile(), userId);
  const options = loadAgentOptions();

  try {
    const data = await sendChat(getApiUrl(), { user_id: userId, query, profile, options });
    typing.remove();
    renderAssistantResponse(data);
    // A successful turn proves the backend is up — recover the badge if it was down.
    if (!healthBadge.classList.contains("health-badge--ok")) refreshHealth();
  } catch (err) {
    typing.remove();
    renderError(err);
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
  setHealth("unknown", "Checking");
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
  themeBtn.setAttribute("aria-pressed", String(theme === "dark"));
}

themeBtn.addEventListener("click", () => {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  setTheme(next);
  applyTheme(next);
});

// ============================================================
// Profile dialog
// ============================================================

function buildAllergenChips() {
  const host = $("#pf-allergies");
  host.textContent = "";
  for (const a of ALLERGENS) {
    const label = el("label", { cls: "allergen" });
    const input = el("input", { attrs: { type: "checkbox", name: "allergy", value: a } });
    label.append(input, document.createTextNode(ALLERGEN_LABELS[a] || a));
    host.append(label);
  }
}

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

function readAndSaveProfile() {
  const allergies = [...profileForm.querySelectorAll('input[name="allergy"]:checked')].map((b) => b.value);
  const dislikes = profileForm.dislikes.value.split(",").map((s) => s.trim()).filter(Boolean);
  const budgetRaw = profileForm.budget.value.trim();

  saveProfile({
    name: profileForm.name.value.trim(),
    allergies,
    diet: profileForm.diet.value || "none",
    budget_per_meal_usd: budgetRaw === "" ? null : Number(budgetRaw),
    skill: profileForm.skill.value || "",
    dislikes,
  });

  const apiUrl = normalizeBaseUrl($("#pf-api").value) || DEFAULT_API_URL;
  setApiUrl(apiUrl);
}

function openProfile() {
  fillProfileForm();
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
  profileForm.name.focus();
}

function closeProfile() {
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
}

profileBtn.addEventListener("click", openProfile);
$("#profile-cancel").addEventListener("click", closeProfile);
$("#profile-cancel-2").addEventListener("click", closeProfile);

profileForm.addEventListener("submit", (e) => {
  if (e.submitter && e.submitter.id !== "profile-save") return;
  readAndSaveProfile();
  applyPostProfileState();
});

function applyPostProfileState() {
  refreshHealth();
  renderSafetyStrip();
  agentTeam = null;              // API URL may have changed — refetch team next open
  if (document.querySelector("#welcome")) {
    clearWelcome();
    renderWelcome();
  }
}

// ============================================================
// Wiring + boot
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

function boot() {
  applyTheme(getTheme());
  buildAllergenChips();
  renderWelcome();
  renderSafetyStrip();
  syncCreativeIndicator();
  refreshHealth();

  if (!hasProfile()) {
    setTimeout(openProfile, 350);
  }

  queryInput.focus();
}

boot();
