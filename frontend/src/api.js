const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export function getToken() {
  return localStorage.getItem("pulse_token");
}
export function setToken(t) {
  localStorage.setItem("pulse_token", t);
}
export function clearToken() {
  localStorage.removeItem("pulse_token");
}

async function req(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const t = getToken();
    if (t) headers.Authorization = `Bearer ${t}`;
  }
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
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
    const error = new Error(message);
    error.status = res.status;
    throw error;
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  base: BASE,
  emailLogin: (email) => req("/auth/email-login", { method: "POST", body: { email }, auth: false }),
  me: () => req("/me"),
  categories: () => req("/categories"),
  setCategories: (category_ids) => req("/me/categories", { method: "POST", body: { category_ids } }),
  feed: (limit = 20) => req(`/feed?limit=${limit}`),
  search: (q, market_id, limit = 20) =>
    req(`/search?q=${encodeURIComponent(q)}&market_id=${market_id}&limit=${limit}`),
  lock: (market_id, object_id, raw_text) =>
    req("/predictions", { method: "POST", body: { market_id, object_id, raw_text } }),
  reveal: (prediction_id) => req(`/predictions/${prediction_id}/reveal`, { method: "POST" }),
  history: (limit = 50) => req(`/me/history?limit=${limit}`),
  profileStats: () => req("/me/stats"),
  leaderboard: () => req("/leaderboard"),
};
