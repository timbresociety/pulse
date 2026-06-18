# Pulse — Rigged Demo Design

**Date:** 2026-06-18
**Status:** Approved design, pre-implementation
**Goal:** A PWA demo of Pulse Markets that tests the core dopamine loop (swipe →
lock a call → reveal → win/rank) with *rigged* outcomes, real auth, and real
measurement. Not the full predict-the-popular engine yet.

---

## 1. What this is (and isn't)

This is a **rigged demo**, not the real game. The win/lose outcomes are
fabricated to deliver a tuned dopamine curve, and there is no real crowd yet, so
the "% of people who picked this" is generated. Everything *around* the rig is
real: Google auth, user records, category choices, the questions/objects, every
user pick, and all timing/engagement data.

The data model is intentionally **forward-compatible** with the full Pulse
system design (taxonomy tree + object graph), so none of this seed work is
thrown away when the real engine is built.

### Faked vs Real

| Faked | Real |
|---|---|
| win/lose outcome of each market | Google auth + user records |
| crowd distribution % shown at reveal | category selections |
| leaderboard names + scores | markets, objects, aliases (the content) |
| | every user prediction (pick, skip, timing) |
| | pulse score derived from rigged wins |

---

## 2. Stack

- **Frontend:** PWA — React + Vite, installable, service worker for app shell.
  Swipe-card UI for the feed.
- **Backend:** FastAPI (async) + Postgres (SQLAlchemy 2.0 + asyncpg).
  `pg_trgm` extension for fuzzy object search.
- **Auth:** Google OAuth via Authlib. Server issues a session JWT after the
  Google callback; frontend stores it and sends it as a Bearer token.
- **Dev:** everything runs locally (Postgres via Docker or local install,
  uvicorn for the API, Vite dev server for the PWA).
- **Deploy (later):** Railway — backend service + managed Postgres, frontend
  static build.

Python performance is a non-issue at demo scale; FastAPI async + Postgres is
comfortably fast.

---

## 3. Screens

### Screen 1 — Onboarding / Category Select
- Entry point. User signs in with Google.
- After login, user picks which categories they want to play (all 12 available,
  multi-select). Stored in `user_category`.
- Persisted so returning users skip straight to the feed (with an edit option).

### Screen 2 — Feed
- A swipeable stack of **market cards** drawn from the user's chosen categories.
- Each card shows: category, prompt, a natural-language **search box**, and a
  per-card countdown.
- Flow: user types an answer → fuzzy search returns canonical object candidates →
  user taps one → **swipe right to lock** (spends nothing in demo / optional coin
  cosmetic) or **swipe left to skip**.
- If no object matches what they typed, they can submit it as free text (stored
  as a pending answer).
- On lock, the market gets a per-user `reveal_seconds` (accelerating timer, see
  §4) and a reveal is scheduled client-side.

### Screen 3 — Reveal
- When a locked market's timer fires, show a **reveal card**: win or miss, the
  "top call" object with a generated %, the user's pick, the pulse delta, and —
  on a win — the **coins won** (winning tickets), with the coin balance ticking
  up.

### Screen 4 — Leaderboard (its own screen)
- A dedicated, always-accessible leaderboard screen (tab in nav).
- **Fake** seeded competitors (names + scores/coins) into which the real user is
  blended by their score, so wins visibly move them up the ranks.
- Ranked by coin balance (or pulse score — config; default coins, since coins
  are the visible "number go up").

---

## 4. Rigged mechanics

### 4.1 Accelerating reveal timers (per user, for testing)
- Reveal delay grows **linearly**: start 30s, **+30s each subsequent locked
  market**. So: 30s, 1m, 1.5m, 2m, 2.5m, …
- Computed from the user's locked-market index for the session.
- `start_seconds` (30) and `increment_seconds` (30) are **config values** for
  easy retuning. No cap (per decision), but configurable.

### 4.2 Outcome — weighted random + dopamine guardrails
- Base probability: **~65% win / 35% lose** per reveal (config value).
- Guardrails so no early bad streak:
  - **Market #1 is always a win.**
  - **No two losses back-to-back** within the first ~5 markets.
- Outcome decided **at reveal time**, stored on the prediction
  (`outcome: win|lose`).
- The user's real pick is **always stored**, independent of outcome — that's the
  measurement signal.

### 4.3 Fabricated crowd distribution
- No real crowd yet, so the reveal card generates believable numbers:
  - **Win:** user's picked object shown as the top call at a plausible share
    (e.g. 18–34%).
  - **Lose:** a different object shown winning; user's pick gets a lower share.
- Generated deterministically per prediction so it's stable on re-view.

### 4.4 Pulse score + coins (winning tickets)
- **Pulse score:** win → +points; bigger bonus when the shown winning share is
  low ("contrarian-looking" win). Lose → small or zero.
- **Coins (winning tickets):** a win awards coins to the user's balance — the
  visible "number go up." Payout scales with the win (e.g. base payout × a
  multiplier that's higher for low-share contrarian wins). Lose → no coins (and,
  if we later add an entry cost, that cost is forfeited; entry is free in v0).
- Coins are the default leaderboard ranking metric; pulse score is the
  identity/skill metric.

---

## 5. Data model (Postgres)

Tables (forward-compatible with the full spec):

- **user** — `id, email, google_sub, display_name, avatar_url, coins,
  pulse_score, created_at`
- **category** — seeded 12 categories: `id, name, slug, theme`
- **user_category** — M:N: `user_id, category_id`
- **object** — seeded canonical answers:
  `id, canonical_name, object_type, category_id, metadata(jsonb), status`
- **object_alias** — search strings → object: `id, object_id, alias`
- **market** — pre-seeded prompts served into the feed:
  `id, prompt, category_id, object_type, status, created_at`
- **prediction** — one per user per market:
  `id, user_id, market_id, object_id(nullable), raw_text(nullable),
   outcome(nullable until reveal), reveal_seconds, locked_at, resolved_at,
   shown_winner_object_id, shown_share, coins_won, pulse_delta`
- **leaderboard_entry** — fake seeded competitors:
  `id, display_name, coins, pulse_score, is_bot`

Notes:
- `object` is tagged to a `category_id` for the demo (single category) rather
  than the full many-node graph; the richer `object_tag` graph comes with the
  real engine.
- Measurement queries fall out of `prediction` directly: pick rates, skip rates,
  time-to-lock, repeat sessions, per-category engagement.

---

## 6. Backend API (FastAPI)

- `GET  /auth/google/login` → redirect to Google.
- `GET  /auth/google/callback` → exchange code, upsert user, issue session JWT.
- `GET  /me` → current user + chosen categories.
- `GET  /categories` → all 12.
- `POST /me/categories` → set chosen categories.
- `GET  /feed` → next batch of markets for the user's categories (excludes
  already-answered).
- `GET  /search?q=&market_id=` → fuzzy object candidates (pg_trgm over
  `canonical_name` + `object_alias`), constrained to the market's `object_type`.
- `POST /predictions` → lock a call: `{market_id, object_id|raw_text}`; returns
  `reveal_seconds`.
- `POST /predictions/{id}/reveal` → compute & store outcome + fabricated crowd,
  award coins + pulse on win, return reveal card payload (outcome, shown winner,
  share, coins_won, pulse_delta, new balance).
- `GET  /leaderboard` → fake entries blended with the real user, ranked by coins
  (default) or pulse.

Game logic (rigging, timers, scoring, crowd fabrication) lives in the FastAPI
layer, not in the DB or frontend.

---

## 7. Seed data

All **12 categories** seeded **deep** (density beats breadth for the demo):
- Each category: a handful of markets (~5–8) + a solid object set (~15–25) with
  aliases for fuzzy search.
- Source content from the existing Pulse Seed Spec v2 (nodes, objects, templates)
  as the starting catalog, expanded for volume.

---

## 8. Out of scope (for this demo)

- Real predict-the-popular resolution (real crowd tally).
- Canonical resolver dedupe/merge jobs.
- The full taxonomy tree + many-node object graph.
- Coins economy / payments / top-ups.
- Real leaderboard from real users.
- Honest-pick mechanic, communities, connection layer.

---

## 9. Open config values (tune without code changes)

- `reveal_start_seconds = 30`
- `reveal_increment_seconds = 30`
- `win_probability = 0.65`
- `no_back_to_back_loss_window = 5`
- `first_market_always_win = true`
- crowd share ranges for win/lose reveals
- `base_coin_payout` + contrarian multiplier (low shown-share → more coins)
- `leaderboard_rank_metric = coins` (or `pulse`)
- `starting_coins` (initial balance on signup)
