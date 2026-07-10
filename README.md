# Pulse / Psyblr

A culture-market PWA where users lock canonical calls, wait for markets to close,
and see how their picks settle against the market result.

The current architecture is source-bound: a market cannot be created from a
prompt alone. Admin-created markets require a category, object type, source URL,
source freshness date, scope statement, coverage statement, and a MECE object
universe. Search and locking are restricted to that finite universe.

## Stack

- Backend: FastAPI, SQLAlchemy 2.0 async, managed Postgres-compatible storage.
- Frontend: React + Vite PWA.
- Auth: Google OAuth plus passwordless email sign-in with a one-time code and
  one-use magic link.
- Admin: allowlisted emails can create markets. `luckyloot786@gmail.com` is in
  the default admin allowlist.

## Data Contract

- User records, username onboarding, predictions, markets, objects, aliases,
  market universes, email challenges, and settlements are all persisted in
  Postgres via `DATABASE_URL`.
- Public standings use real signed-in users with usernames.
- Pools, counts, settlement winners, payouts, and history are computed from
  persisted prediction rows.
- Development fixtures must stay isolated from public accounting surfaces.

## Run Locally

Backend:

```bash
cd backend
docker compose up -d
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173`. The backend health check is at
`http://localhost:8000/health`.

## Auth Setup

Google OAuth:

- Create credentials in Google Cloud Console.
- Set the redirect URI to `http://localhost:8000/auth/google/callback` locally,
  or your production backend callback URL in production.
- Fill `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI`.

Email sign-in:

- Production uses `EMAIL_DELIVERY=resend`, `RESEND_API_KEY`, and `EMAIL_FROM`.
- The email contains both a six-digit code and a magic link.
- The magic link redirects back to `FRONTEND_URL` with an access token fragment.
- Local development can use `EMAIL_DELIVERY=console` with `DEBUG=true`; the code
  is written to backend logs only.

## Market Creation

Admin users see a Create tab after login. To publish a market they must provide:

- prompt
- category
- object type
- close duration
- source name and URL
- source last-updated date
- scope statement
- coverage statement
- MECE object list with optional aliases

The API rejects duplicate canonical objects and alias collisions. Once published,
retrieval is object-restricted: autocomplete and lock resolution only search
objects linked through `market_objects` for that market.

See `docs/architecture.md` for the backend model and settlement details.

## Cloud Deploy

The backend is packaged for Render with `render.yaml` and `backend/Dockerfile`.
Follow `docs/deploy-render.md` to create the web service, managed Postgres
database, Resend email settings, Google OAuth redirect, and frontend
`VITE_API_URL`.
