// =========================================================================
// api.js — thin client for the kitchenaid backend.
// No DOM here; just fetch + a friendly error type. Keeps app.js focused on UI.
// =========================================================================

/** Raised when we can't reach or don't get a sane answer from the backend. */
export class ApiError extends Error {
  constructor(message, { unreachable = false, status = 0 } = {}) {
    super(message);
    this.name = "ApiError";
    this.unreachable = unreachable; // true = network/CORS/DNS, i.e. backend likely not running
    this.status = status;
  }
}

/** Normalize a base URL: trim, drop trailing slash. */
export function normalizeBaseUrl(url) {
  return (url || "").trim().replace(/\/+$/, "");
}

/**
 * GET /health — returns the parsed JSON, or throws ApiError.
 * Kept short so the header badge can poll it cheaply.
 */
export async function checkHealth(baseUrl, { signal } = {}) {
  const url = `${normalizeBaseUrl(baseUrl)}/health`;
  let res;
  try {
    res = await fetch(url, { method: "GET", signal });
  } catch (err) {
    // fetch rejects only on network-level failure (server down, CORS, DNS).
    throw new ApiError(err.message || "Network error", { unreachable: true });
  }
  if (!res.ok) throw new ApiError(`Health check failed (${res.status})`, { status: res.status });
  return res.json();
}

/**
 * GET /agents — team metadata (name, role, detail, toggleability).
 * The Agents panel renders entirely from this; nothing is hardcoded.
 */
export async function fetchAgents(baseUrl, { signal } = {}) {
  const url = `${normalizeBaseUrl(baseUrl)}/agents`;
  let res;
  try {
    res = await fetch(url, { method: "GET", signal });
  } catch (err) {
    throw new ApiError(err.message || "Network error", { unreachable: true });
  }
  if (!res.ok) throw new ApiError(`Couldn't load the team (${res.status})`, { status: res.status });
  return res.json();
}

/**
 * POST /chat — send a natural-language turn.
 * @param {string} baseUrl
 * @param {{user_id:string, query:string, profile:object, options:object}} payload
 * @returns {Promise<object>} the chat response (see API contract)
 */
export async function sendChat(baseUrl, payload, { signal, timeoutMs = 45000 } = {}) {
  const url = `${normalizeBaseUrl(baseUrl)}/chat`;
  // Creative (LLM) turns can take several seconds — give them room, but never hang forever.
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  if (signal) signal.addEventListener("abort", () => ctrl.abort(), { once: true });
  let res;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: ctrl.signal,
    });
  } catch (err) {
    const timedOut = err?.name === "AbortError";
    throw new ApiError(timedOut ? "That took too long — try again or turn Creative mode off."
                                : (err.message || "Network error"),
                       { unreachable: !timedOut });
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    // Try to surface FastAPI's error detail if present, but never crash on parse.
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? "");
    } catch {
      /* body wasn't JSON; ignore */
    }
    throw new ApiError(
      `The kitchen had trouble (${res.status})${detail ? `: ${detail}` : ""}`,
      { status: res.status }
    );
  }

  return res.json();
}
