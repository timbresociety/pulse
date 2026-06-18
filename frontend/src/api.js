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
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  base: BASE,
  devLogin: (email) =>
    req(`/auth/dev-login?email=${encodeURIComponent(email)}`, { method: "POST", auth: false }),
  me: () => req("/me"),
  categories: () => req("/categories"),
  setCategories: (category_ids) => req("/me/categories", { method: "POST", body: { category_ids } }),
  feed: (limit = 20) => req(`/feed?limit=${limit}`),
  search: (q, market_id) =>
    req(`/search?q=${encodeURIComponent(q)}&market_id=${market_id}`),
  lock: (market_id, object_id, raw_text) =>
    req("/predictions", { method: "POST", body: { market_id, object_id, raw_text } }),
  reveal: (prediction_id) => req(`/predictions/${prediction_id}/reveal`, { method: "POST" }),
  leaderboard: () => req("/leaderboard"),
};
