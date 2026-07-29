# Pulse Markets v0

A PWA prototype for a fixed-option cultural polling game: vote what you think,
predict the complete crowd distribution, stake fake USD credits, and reveal how
accurately you read a deterministic simulated crowd.

## What's real vs simulated

| Real | Simulated |
|---|---|
| prototype email sign-in, user records | 500–2,000 deterministic dummy participants |
| category selections and per-user reveal timing | dummy votes, forecasts, and fake stakes |
| vote, full forecast, fake USD stake and settlement | 5,200 deterministic leaderboard competitors |
| balance ledger, payout, PnL, accuracy and Pulse Score | |

## Stack

- **Backend:** FastAPI (async) + Postgres (SQLAlchemy 2.0 + asyncpg), `pg_trgm`
  fuzzy search.
- **Frontend:** React + Vite PWA.
- **Auth:** passwordless prototype email sign-in (plus optional Google OAuth).

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

# Run — migrates the schema and idempotently seeds 8 categories / 64 markets
uvicorn app.main:app --reload
```

Check it: open http://localhost:8000/api/health → `{"status":"ok", ...}`.
The database-backed readiness probe is at
http://localhost:8000/api/ready → `{"status":"ready"}`.
Its production timeout allows managed Postgres to wake from an idle cold start
without reporting a false outage.
API docs at http://localhost:8000/docs.

**Email authentication:** Pulse supports six-digit, one-time email codes through
`POST /api/auth/email-otp/request` and `/api/auth/email-otp/verify`. Configure
`RESEND_API_KEY` (recommended for Vercel) or the `SMTP_*` variables to enable
delivery in production. Codes are hashed at rest, expire after 10 minutes, are
single-use, and have resend and attempt limits. In local `DEBUG` mode, the
request response includes `dev_code` when no delivery provider is configured.

**Testing without an email provider:** the login screen can fall back to the
prototype `POST /api/auth/email-login` flow while
`EMAIL_LOGIN_ENABLED=true`. This does not verify mailbox ownership, so use it
only for a shareable demo and turn it off once OTP delivery is configured. The legacy
`POST /api/auth/dev-login?email=you@example.com` endpoint remains available only
with `DEBUG=true`.

**Enabling Google OAuth:** create OAuth credentials at
https://console.cloud.google.com/apis/credentials, set the redirect URI to
`http://localhost:8000/api/auth/google/callback`, and fill `GOOGLE_CLIENT_ID` /
`GOOGLE_CLIENT_SECRET` in `.env`.

### 2. Frontend

```bash
cd frontend
cp .env.example .env          # VITE_API_URL=/api (proxied to port 8000 in dev)
npm install
npm run dev                   # http://localhost:5173
```

Open http://localhost:5173, log in with any valid email address, pick your
categories, and start swiping.

## Market catalog

The active feed is owned by `backend/app/data/pulse_markets_v0.json`: 64 manually
curated fixed-option polls across Internet, Music, Entertainment, Fashion,
Technology, Crypto, Culture, and Experiences. Every market has four to eight
ordered options and hidden authored simulation weights totalling 10,000 basis
points. Legacy open-ended catalogs remain only for compatibility and never enter
the active feed. LLM top-up is disabled for Pulse Poll markets.

## Upgrade an existing database

The migration is additive and preserves legacy users, markets, predictions, and
category selections. Back up production first, then run:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```

Start the API once after migration so the idempotent seed can upsert categories,
markets, options, bot profiles, and user backfills. Re-running both migration and
seed is safe. Do not drop or recreate the database. Local startup also runs the
migration when `INITIALIZE_DATABASE=true`; production should run the migration
and seed as release steps before deploying with `INITIALIZE_DATABASE=false` and
`SEED_DATABASE=false`.

## Game tuning (backend `.env`)

| Var | Default | Meaning |
|---|---|---|
| `REVEAL_START_SECONDS` | 30 | delay before the 1st locked market reveals |
| `REVEAL_INCREMENT_SECONDS` | 30 | added to each subsequent reveal (linear: 30, 60, 90…) |
| `STARTING_BALANCE_CENTS` | 1000000 | new-user fake USD balance ($10,000) |
| `STARTING_PULSE_SCORE` | 1000 | new-user Pulse Score |

The platform fee is fixed at 2% for this prototype.

## Project layout

```
backend/
  app/
    main.py            # app wiring, table create + seed on startup
    config.py          # env settings + game knobs
    models.py          # SQLAlchemy models
    auth.py            # JWT sessions, get_current_user, upsert_user
    game.py            # timers, deterministic crowd, accuracy and settlement
    data/pulse_markets_v0.json # 64-market fixed-option catalog
    seed.py            # idempotent catalog migration/seed
    routers/           # auth, users, feed, predictions, leaderboard
  migrations/          # additive Alembic migration for existing databases
  tests/               # catalog, validation and settlement tests
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
[`vercel.json`](vercel.json) defines both services. Vercel forwards the public
`/api` path to FastAPI unchanged, so the backend exposes its routes under
`/api`. `frontend/.env.production` makes the built frontend call that
same-origin path.

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
   EMAIL_LOGIN_ENABLED=true
   OTP_EMAIL_ENABLED=true
   OTP_PEPPER=<a second long, random secret>
   OTP_FROM_EMAIL=Pulse <login@your-verified-domain.example>
   RESEND_API_KEY=<recommended; alternatively configure SMTP_*>
   INITIALIZE_DATABASE=false
   SEED_DATABASE=false
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
   `https://<your-production-domain>/api/health`, verify database readiness
   through `https://<your-production-domain>/api/ready`, and then open the
   root URL.

Vercel Services builds the two directories separately but exposes them on one
domain. The backend is a Vercel Function, so the database and email provider
must be external and reachable over TLS.

### Safe production releases

Do not deploy an in-progress working tree. Production releases use:

```bash
CONFIRM_PRODUCTION_DEPLOY=psyblr.vercel.app ./scripts/deploy-production.sh
```

The script refuses dirty, non-`main`, or unpushed code; runs backend tests and
the frontend build; creates a production-environment deployment without moving
the live domain; smoke-tests its frontend, liveness, database readiness, and
catalog; and only then promotes it. If the post-promotion smoke test fails, it
rolls back to the previous deployment.

Vercel Git auto-deployments are disabled in `vercel.json`. Merging to `main`
updates the release source but does not change the live domain; production moves
only through the guarded command above. `.vercelignore` and the release
preflight prevent local secrets, dependency trees, and build/test artifacts from
being uploaded by the CLI.

For a read-only check of the current production deployment:

```bash
./scripts/smoke-production.sh
```

The default sign-in is intentionally a low-friction, **unverified email**
identity for prototype testers. It is suitable for sharing a demo link, but it
is not a replacement for real password or email-link authentication.

## Notes for the frontend dev

The UI is intentionally minimal (plain CSS, button-based "swipe"). The backend
contract is stable — see `frontend/src/api.js` for every endpoint. Good next
steps: real swipe gestures, animated reveal/coin counter, category-themed feed
skins, streaks, share cards.
