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
const QUERY_CACHE_PREFIX = "pulse_query_v1:";
const USER_CACHE_KEY = "pulse_user_v1";
const QUERY_TTL_MS = 30_000;
const CATALOG_TTL_MS = 5 * 60_000;
const memoryCache = new Map();
const inFlight = new Map();
let cacheGeneration = 0;

function readStorage(storage, key) {
  try {
    const value = storage.getItem(key);
    return value ? JSON.parse(value) : null;
  } catch {
    return null;
  }
}

function writeStorage(storage, key, value) {
  try {
    storage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage can be unavailable in private contexts. The memory cache still works.
  }
}

function removeStorage(storage, key) {
  try {
    storage.removeItem(key);
  } catch {
    // Best effort only.
  }
}

function cacheKey(name) {
  return `${QUERY_CACHE_PREFIX}${name}`;
}

function readQueryCache(name) {
  if (memoryCache.has(name)) return memoryCache.get(name);
  const entry = readStorage(sessionStorage, cacheKey(name));
  if (entry && typeof entry.savedAt === "number" && "value" in entry) {
    memoryCache.set(name, entry);
    return entry;
  }
  return null;
}

function writeQueryCache(name, value) {
  const entry = { savedAt: Date.now(), value };
  memoryCache.set(name, entry);
  writeStorage(sessionStorage, cacheKey(name), entry);
  return value;
}

function clearQueryCache() {
  cacheGeneration += 1;
  memoryCache.clear();
  inFlight.clear();
  try {
    Object.keys(sessionStorage)
      .filter((key) => key.startsWith(QUERY_CACHE_PREFIX))
      .forEach((key) => sessionStorage.removeItem(key));
  } catch {
    // Best effort only.
  }
}

function peek(name) {
  return readQueryCache(name)?.value ?? null;
}

export function getToken() {
  return localStorage.getItem("pulse_token");
}
export function setToken(t) {
  if (getToken() !== t) {
    clearQueryCache();
    removeStorage(localStorage, USER_CACHE_KEY);
  }
  localStorage.setItem("pulse_token", t);
}
export function clearToken() {
  localStorage.removeItem("pulse_token");
  removeStorage(localStorage, USER_CACHE_KEY);
  clearQueryCache();
}

export function getCachedUser() {
  if (!getToken()) return null;
  return readStorage(localStorage, USER_CACHE_KEY);
}

export function setCachedUser(user) {
  if (user) {
    writeStorage(localStorage, USER_CACHE_KEY, user);
  } else {
    removeStorage(localStorage, USER_CACHE_KEY);
  }
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

async function cachedGet(name, path, { force = false, ttlMs = QUERY_TTL_MS } = {}) {
  const cached = readQueryCache(name);
  if (!force && cached && Date.now() - cached.savedAt < ttlMs) {
    return cached.value;
  }
  if (inFlight.has(name)) return inFlight.get(name);

  const generation = cacheGeneration;
  let request;
  request = req(path)
    .then((value) => {
      if (generation !== cacheGeneration) {
        return cachedGet(name, path, { force: true, ttlMs });
      }
      return writeQueryCache(name, value);
    })
    .finally(() => {
      if (inFlight.get(name) === request) inFlight.delete(name);
    });
  inFlight.set(name, request);
  return request;
}

function seedBootstrap(data) {
  // A mutation may have invalidated the cache while bootstrap was in flight.
  // Only seed its child entries when this response is still the active one.
  if (!data || peek("bootstrap") !== data) return data;
  writeQueryCache("me", data.user);
  writeQueryCache("profileStats", data.profile_stats);
  writeQueryCache("wallet", data.wallet);
  writeQueryCache("leaderboard", data.leaderboard);
  return data;
}

function getBootstrap({ force = false } = {}) {
  return cachedGet("bootstrap", "/bootstrap", { force }).then(seedBootstrap);
}

function summaryGet(name, path, bootstrapField, { force = false } = {}) {
  const cached = readQueryCache(name);
  if (!force && cached && Date.now() - cached.savedAt < QUERY_TTL_MS) {
    return Promise.resolve(cached.value);
  }
  if (!force && inFlight.has("bootstrap")) {
    return inFlight.get("bootstrap")
      .then(seedBootstrap)
      .then((data) => data[bootstrapField]);
  }
  return cachedGet(name, path, { force });
}

async function mutate(path, options) {
  const value = await req(path, options);
  clearQueryCache();
  if (getToken()) {
    // Refill all summary caches while the user continues with the local
    // optimistic UI. A destination screen can join this same request.
    void getBootstrap({ force: true }).catch(() => {});
  }
  return value;
}

export const api = {
  base: BASE,
  peek,
  clearCache: clearQueryCache,
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
  bootstrap: getBootstrap,
  me: ({ force = false } = {}) => cachedGet("me", "/me", { force }),
  categories: ({ force = false } = {}) =>
    cachedGet("categories", "/categories", { force, ttlMs: CATALOG_TTL_MS }),
  setCategories: (category_ids) =>
    mutate("/me/categories", { method: "POST", body: { category_ids } }),
  feed: (limit = 20, { force = false } = {}) =>
    cachedGet(`feed:${limit}`, `/feed?limit=${limit}`, { force }),
  lock: (market_id, vote_option_id, forecast_bps, stake_cents) =>
    mutate("/predictions", {
      method: "POST",
      body: { market_id, vote_option_id, forecast_bps, stake_cents },
    }),
  reveal: (prediction_id) =>
    mutate(`/predictions/${prediction_id}/reveal`, { method: "POST" }),
  history: (limit = 50, { force = false } = {}) =>
    cachedGet(`history:${limit}`, `/me/history?limit=${limit}`, { force }),
  wallet: ({ force = false } = {}) =>
    summaryGet("wallet", "/me/wallet", "wallet", { force }),
  profileStats: ({ force = false } = {}) =>
    summaryGet("profileStats", "/me/stats", "profile_stats", { force }),
  leaderboard: ({ force = false } = {}) =>
    summaryGet("leaderboard", "/leaderboard", "leaderboard", { force }),
  addTestCredits: () => mutate("/debug/credits", { method: "POST" }),
  resolveNow: (prediction_id) =>
    mutate(`/debug/predictions/${prediction_id}/resolve`, { method: "POST" }),
  resolveRevealable: () =>
    mutate("/debug/resolve-revealable", { method: "POST" }),
  resetGameplay: () =>
    mutate("/debug/reset-gameplay", { method: "POST" }),
};
