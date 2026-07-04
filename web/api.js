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
 * POST /chat — send a natural-language turn.
 * @param {string} baseUrl
 * @param {{user_id:string, query:string, profile:object}} payload
 * @returns {Promise<object>} the chat response (see API contract)
 */
export async function sendChat(baseUrl, payload, { signal } = {}) {
  const url = `${normalizeBaseUrl(baseUrl)}/chat`;
  let res;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (err) {
    throw new ApiError(err.message || "Network error", { unreachable: true });
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
