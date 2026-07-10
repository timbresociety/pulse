# Pulse — Rigged Demo

A PWA demo of **Pulse Markets**: a swipe-feed cultural prediction game ("how well
can you read culture?"). This version exists to test the core dopamine loop —
swipe → lock a call → reveal → win coins → climb the leaderboard — with **rigged**
outcomes, **real** Google auth, and **real** measurement.

Design spec: [`docs/superpowers/specs/2026-06-18-pulse-rigged-demo-design.md`](docs/superpowers/specs/2026-06-18-pulse-rigged-demo-design.md)

## What's real vs faked

| Real | Faked |
|---|---|
| Google auth, user records | win/lose outcome (weighted random + guardrails) |
| category selections | crowd distribution % at reveal |
| markets, objects, fuzzy search | leaderboard competitors |
| every prediction (pick, timing) | |
| coins + pulse derived from wins | |

## Stack

- **Backend:** FastAPI (async) + Postgres (SQLAlchemy 2.0 + asyncpg), `pg_trgm`
  fuzzy search.
- **Frontend:** React + Vite PWA (simple light theme).
- **Auth:** Google OAuth (+ an email-only `/auth/dev-login` for local testing).

## Run it locally

### 1. Backend

```bash
cd backend

# Start Postgres (or use your own and set DATABASE_URL)
docker compose up -d

# Python env
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Config
cp .env.example .env          # defaults work with the docker compose db

# Run — creates tables, enables pg_trgm, seeds 12 categories on first boot
uvicorn app.main:app --reload
```

Check it: open http://localhost:8000/health → `{"status":"ok", ...}`.
API docs at http://localhost:8000/docs.

**Testing without Google:** with `DEBUG=true` (the default), you can log in with
just an email via `POST /auth/dev-login?email=you@example.com`. The frontend's
login screen exposes this as a "Dev login" box.

**Enabling Google OAuth:** create OAuth credentials at
https://console.cloud.google.com/apis/credentials, set the redirect URI to
`http://localhost:8000/auth/google/callback`, and fill `GOOGLE_CLIENT_ID` /
`GOOGLE_CLIENT_SECRET` in `.env`.

### 2. Frontend

```bash
cd frontend
cp .env.example .env          # VITE_API_URL=http://localhost:8000
npm install
npm run dev                   # http://localhost:5173
```

Open http://localhost:5173, log in (use Dev login for speed), pick your
categories, and start swiping.

## Questions (static seed)

The feed is seeded from **14,400 questions** — **200 per subcategory**, 6
subcategories × 12 categories (1,200 per category). They live as compact JSON in
`backend/app/data/markets/<category>.json`, grouped by subcategory, and load at
first boot.

Regenerate or tweak them with the template generator:

```bash
cd backend && python scripts/build_market_seed.py   # rewrites the JSON files
```

Each question is templated as `superlative × object_type × facet` within a
subcategory scope, and every question's `object_type` is restricted to the types
that category actually has seeded answers for — so the fuzzy search always has
real objects to match. To reload after regenerating, drop and recreate the DB
(seeding only runs on an empty database).

## Optional: dynamic LLM top-up

With 14,400 static questions the feed effectively never runs dry, so this is
off by default. If you set `ANTHROPIC_API_KEY`, the backend will *also* generate
fresh questions on the fly with Claude (`claude-opus-4-8`) when a user's
unanswered count in a category drops below `FEED_TOPUP_THRESHOLD`:

- **On category select** — picking categories kicks off background generation
  for each, so the feed grows as you start playing.
- **Auto top-up** — when a category's unanswered count for a user drops below
  `FEED_TOPUP_THRESHOLD`, the feed fires a background batch of
  `FEED_TOPUP_BATCH` new questions.

Generated prompts are constrained (via structured outputs) to the `object_type`s
each category actually has seeded answers for, so fuzzy search always has real
objects to match. It's fully best-effort: no key, or any API error, and the feed
just falls back to the seeded markets — nothing in the request path blocks on it.

Set `ANTHROPIC_API_KEY` in `backend/.env` to enable it.

## Game tuning (backend `.env`)

| Var | Default | Meaning |
|---|---|---|
| `REVEAL_START_SECONDS` | 30 | delay before the 1st locked market reveals |
| `REVEAL_INCREMENT_SECONDS` | 30 | added to each subsequent reveal (linear: 30, 60, 90…) |
| `WIN_PROBABILITY` | 0.65 | base win chance per reveal |
| `FIRST_MARKET_ALWAYS_WIN` | true | guarantee a first-win dopamine hit |
| `NO_BACK_TO_BACK_LOSS_WINDOW` | 5 | no two losses in a row within first N markets |
| `STARTING_COINS` | 100 | balance on signup |
| `BASE_COIN_PAYOUT` | 50 | base coins per win (×contrarian multiplier) |
| `LEADERBOARD_RANK_METRIC` | coins | `coins` or `pulse` |

## Project layout

```
backend/
  app/
    main.py            # app wiring, table create + seed on startup
    config.py          # env settings + game knobs
    models.py          # SQLAlchemy models
    auth.py            # JWT sessions, get_current_user, upsert_user
    game.py            # rigging: timers, outcomes, crowd, coins, pulse
    seed_data.py       # the 12-category catalog
    seed.py            # idempotent seeding
    routers/           # auth, users, feed, predictions, leaderboard
  docker-compose.yml   # Postgres 16
frontend/
  src/
    api.js             # fetch client
    auth.jsx           # token + useAuth
    App.jsx            # router + nav + login gate
    screens/           # Login, Categories, Feed, Reveal, Leaderboard, Profile
docs/superpowers/specs/ # design spec
```

## Deploy to Vercel

This repository deploys as one Vercel **Services** project: the Vite frontend
at `/` and the FastAPI backend at `/api/*`. The root
[`vercel.json`](vercel.json) defines both services and strips the public `/api`
prefix before the backend handles a request. `frontend/.env.production` makes
the built frontend call that same-origin `/api` path.

1. Import the repository into Vercel and set **Framework Preset** to
   **Services** in **Settings → Build and Deployment**. Do not set a root
   directory; Vercel needs the repository root to read `vercel.json`.
2. Create a managed Postgres database (for example, Vercel Postgres, Neon, or
   Supabase) and use its async SQLAlchemy connection string for `DATABASE_URL`.
3. Add these environment variables to the Vercel project for Production (and
   Preview if you want preview deployments to work):

   ```text
   DATABASE_URL=postgresql+asyncpg://...
   JWT_SECRET=<a long, random secret>
   DEBUG=false
   FRONTEND_URL=https://<your-production-domain>
   GOOGLE_CLIENT_ID=<optional>
   GOOGLE_CLIENT_SECRET=<optional>
   GOOGLE_REDIRECT_URI=https://<your-production-domain>/api/auth/google/callback
   ANTHROPIC_API_KEY=<optional>
   ```

4. If Google login is enabled, add the same `GOOGLE_REDIRECT_URI` in the Google
   Cloud OAuth client. For each preview domain you want to test with Google,
   add its exact callback URL as well.
5. Deploy. Verify the backend through
   `https://<your-production-domain>/api/health` and then open the root URL.

Vercel Services is currently in beta; it builds the two directories separately
but exposes them on one domain. The backend is a Vercel Function, so the
database must be external and reachable over TLS.

## Notes for the frontend dev

The UI is intentionally minimal (plain CSS, button-based "swipe"). The backend
contract is stable — see `frontend/src/api.js` for every endpoint. Good next
steps: real swipe gestures, animated reveal/coin counter, category-themed feed
skins, streaks, share cards.
