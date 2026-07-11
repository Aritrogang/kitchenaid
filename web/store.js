// =========================================================================
// store.js — localStorage-backed profile + settings, plus a stable user_id.
// Pure data; no DOM. All values survive a page reload.
// =========================================================================

const KEYS = {
  profile: "kitchenaid.profile",
  userId: "kitchenaid.user_id",
  apiUrl: "kitchenaid.api_url",
  theme: "kitchenaid.theme",
  agentOptions: "kitchenaid.agent_options",
  token: "kitchenaid.token",
  username: "kitchenaid.username",
};

export const ALLERGENS = [
  "peanut", "tree_nut", "milk", "egg", "soy",
  "wheat", "fish", "shellfish", "sesame",
];

// Local dev serves the web on :3000 and the API on :8000; a deployed build (e.g. Vercel)
// serves both from the same origin, so the API is reached with relative paths ("").
export const DEFAULT_API_URL =
  (location.hostname === "localhost" || location.hostname === "127.0.0.1")
    ? "http://localhost:8000"
    : "";

/** RFC-4122 v4 uuid. Uses crypto.randomUUID when available, else a fallback. */
function uuid() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  // Fallback for older/insecure contexts.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/** Read (creating + persisting on first run) the stable per-user id. */
export function getUserId() {
  let id = localStorage.getItem(KEYS.userId);
  if (!id) {
    id = uuid();
    localStorage.setItem(KEYS.userId, id);
  }
  return id;
}

/** The saved API base URL, or the sensible default. */
export function getApiUrl() {
  return localStorage.getItem(KEYS.apiUrl) || DEFAULT_API_URL;
}
export function setApiUrl(url) {
  localStorage.setItem(KEYS.apiUrl, url || DEFAULT_API_URL);
}

// ---------------------------------------------------------------------------
// Auth — a bearer token issued by the backend's login. Present only when the
// deployment has auth enabled (KITCHENAID_AUTH_SECRET set).
// ---------------------------------------------------------------------------
export function getToken() {
  return localStorage.getItem(KEYS.token) || "";
}
export function setToken(token) {
  localStorage.setItem(KEYS.token, token);
}
export function getUsername() {
  return localStorage.getItem(KEYS.username) || "";
}
export function setUsername(name) {
  localStorage.setItem(KEYS.username, name);
}
export function clearAuth() {
  localStorage.removeItem(KEYS.token);
  localStorage.removeItem(KEYS.username);
}

export function getTheme() {
  return localStorage.getItem(KEYS.theme) || "light";
}
export function setTheme(theme) {
  localStorage.setItem(KEYS.theme, theme);
}

// ---------------------------------------------------------------------------
// Agent toggles — sent as `options` on every /chat turn.
// Defaults mirror the backend's AgentOptions; server-provided defaults from
// GET /agents win for keys the user has never touched (handled in app.js).
// ---------------------------------------------------------------------------
export const DEFAULT_AGENT_OPTIONS = {
  creative_chef: false,
  shopper: true,
  taster: true,
};

/** Stored toggle state merged over defaults; always returns all three keys. */
export function loadAgentOptions() {
  let stored = {};
  try {
    stored = JSON.parse(localStorage.getItem(KEYS.agentOptions) || "{}");
  } catch {
    stored = {};
  }
  const opts = { ...DEFAULT_AGENT_OPTIONS };
  for (const key of Object.keys(opts)) {
    if (typeof stored[key] === "boolean") opts[key] = stored[key];
  }
  return opts;
}

export function saveAgentOptions(opts) {
  localStorage.setItem(KEYS.agentOptions, JSON.stringify(opts));
}

/** Flip a single toggle and persist; returns the full updated options. */
export function setAgentOption(key, value) {
  const opts = loadAgentOptions();
  opts[key] = Boolean(value);
  saveAgentOptions(opts);
  return opts;
}

/**
 * Load the raw stored profile (UI-friendly shape), with safe defaults.
 * We keep the stored shape close to the wire shape to keep mapping trivial.
 */
export function loadProfile() {
  let stored = {};
  try {
    stored = JSON.parse(localStorage.getItem(KEYS.profile) || "{}");
  } catch {
    stored = {};
  }
  return {
    name: stored.name || "",
    allergies: Array.isArray(stored.allergies) ? stored.allergies : [],
    diet: stored.diet || "none",
    budget_per_meal_usd: stored.budget_per_meal_usd ?? null,
    skill: stored.skill || "",
    dislikes: Array.isArray(stored.dislikes) ? stored.dislikes : [],
  };
}

export function saveProfile(profile) {
  localStorage.setItem(KEYS.profile, JSON.stringify(profile));
}

/** True until the user has saved a profile at least once. */
export function hasProfile() {
  return localStorage.getItem(KEYS.profile) !== null;
}

/**
 * Build the exact `profile` object the API expects from the stored profile.
 * Optional fields are omitted when empty so we never send junk like budget:null.
 */
export function toWireProfile(profile, userId) {
  const wire = {
    user_id: userId,
    name: profile.name || "",
    allergies: profile.allergies || [],
    diet: profile.diet || "none",
  };
  if (profile.budget_per_meal_usd != null && profile.budget_per_meal_usd !== "") {
    wire.budget_per_meal_usd = Number(profile.budget_per_meal_usd);
  }
  if (profile.skill) wire.skill = profile.skill;
  if (profile.dislikes && profile.dislikes.length) wire.dislikes = profile.dislikes;
  return wire;
}
