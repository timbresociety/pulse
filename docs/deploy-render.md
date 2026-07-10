# Deploy the Pulse Backend on Render

This repo includes `render.yaml`, which creates:

- a Docker web service for `backend/`
- a managed Postgres database
- generated `JWT_SECRET`
- the admin allowlist with `luckyloot786@gmail.com`

## 1. Create the Render Blueprint

1. Push this repo to GitHub.
2. In Render, create a new Blueprint from `https://github.com/timbresociety/pulse`.
3. Render will detect `render.yaml` and create `pulse-api` plus `pulse-db`.

## 2. Set Required Secret Environment Variables

Set these on the `pulse-api` service before using login:

```bash
RESEND_API_KEY=re_...
EMAIL_FROM="Psyblr <signin@your-domain.com>"
FRONTEND_URL=https://your-frontend-domain.com
PUBLIC_API_URL=https://your-render-backend-url.onrender.com
CORS_ORIGINS=https://your-frontend-domain.com
```

`RESEND_API_KEY` and `EMAIL_FROM` are what fix the "Email sign-in is not
configured yet" error.

## 3. Optional Google OAuth

In Google Cloud Console, add this authorized redirect URI:

```text
https://your-render-backend-url.onrender.com/auth/google/callback
```

Then set:

```bash
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://your-render-backend-url.onrender.com/auth/google/callback
```

## 4. Point the Frontend at the Cloud API

Set the frontend build env var wherever the frontend is hosted:

```bash
VITE_API_URL=https://your-render-backend-url.onrender.com
```

For local frontend testing against the cloud backend, set `frontend/.env` to
that same `VITE_API_URL` and restart Vite.

## 5. Verify

After the Render service is live:

```bash
curl https://your-render-backend-url.onrender.com/health
```

Expected response:

```json
{"status":"ok","google_auth":true,"debug":false}
```

`google_auth` is `false` until Google credentials are set, but email login works
as soon as Resend settings are present.
