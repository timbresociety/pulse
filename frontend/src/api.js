function normalizeApiBase(value) {
  const base = (value || "/api").trim().replace(/\/+$/, "");
  return base.endsWith("/api") ? base : `${base}/api`;
}

const BASE = normalizeApiBase(import.meta.env.VITE_API_URL);
// Vercel's Python function and the SMTP provider can both be cold on the first
// request. Keep the ordinary API timeout responsive, but give email delivery
// enough time to complete before aborting a request that may already succeed.
const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS) || 20000;
const EMAIL_REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_EMAIL_TIMEOUT_MS) || 30000;

export function getToken() {
  return localStorage.getItem("pulse_token");
}
export function setToken(t) {
  localStorage.setItem("pulse_token", t);
}
export function clearToken() {
  localStorage.removeItem("pulse_token");
}

async function req(
  path,
  {
    method = "GET",
    body,
    auth = true,
    timeoutMs = REQUEST_TIMEOUT_MS,
    timeoutMessage = "Pulse is taking longer than expected. Please try again.",
  } = {},
) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const t = getToken();
    if (t) headers.Authorization = `Bearer ${t}`;
  }
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(timeoutMessage);
    }
    if (error instanceof TypeError) {
      throw new Error(
        import.meta.env.DEV
          ? "Can't reach the Pulse API. Start the backend on port 8000 and try again."
          : "Can't reach Pulse right now. Check your connection and try again.",
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
  if (res.status === 401) {
    clearToken();
    throw new Error("unauthorized");
  }
  if (!res.ok) {
    const text = await res.text();
    let message = text || res.statusText;
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed.detail === "string") {
        message = parsed.detail;
      } else if (Array.isArray(parsed.detail)) {
        message = parsed.detail.map((item) => item.msg || "Validation error").join(" ");
      }
    } catch {
      // Keep the plain response body when it is not JSON.
    }
    if (res.status >= 500 && (!message || message === "Internal Server Error")) {
      message = "The Pulse API is unavailable. If you're running locally, start the backend on port 8000.";
    }
    const error = new Error(message);
    error.status = res.status;
    throw error;
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  base: BASE,
  authMethods: () => req("/auth/methods", { auth: false }),
  emailLogin: (email) => req("/auth/email-login", { method: "POST", body: { email }, auth: false }),
  requestEmailOtp: (email) =>
    req("/auth/email-otp/request", {
      method: "POST",
      body: { email },
      auth: false,
      timeoutMs: EMAIL_REQUEST_TIMEOUT_MS,
      timeoutMessage: "Sending the code is taking longer than expected. Please wait a moment and try again.",
    }),
  verifyEmailOtp: (challenge_id, code) =>
    req("/auth/email-otp/verify", {
      method: "POST",
      body: { challenge_id, code },
      auth: false,
    }),
  me: () => req("/me"),
  categories: () => req("/categories"),
  setCategories: (category_ids) => req("/me/categories", { method: "POST", body: { category_ids } }),
  feed: (limit = 20) => req(`/feed?limit=${limit}`),
  lock: (market_id, vote_option_id, forecast_bps, stake_cents) =>
    req("/predictions", {
      method: "POST",
      body: { market_id, vote_option_id, forecast_bps, stake_cents },
    }),
  reveal: (prediction_id) => req(`/predictions/${prediction_id}/reveal`, { method: "POST" }),
  history: (limit = 50) => req(`/me/history?limit=${limit}`),
  wallet: () => req("/me/wallet"),
  profileStats: () => req("/me/stats"),
  leaderboard: () => req("/leaderboard"),
  addTestCredits: () => req("/debug/credits", { method: "POST" }),
  resolveNow: (prediction_id) => req(`/debug/predictions/${prediction_id}/resolve`, { method: "POST" }),
  resolveRevealable: () => req("/debug/resolve-revealable", { method: "POST" }),
  resetGameplay: () => req("/debug/reset-gameplay", { method: "POST" }),
};
