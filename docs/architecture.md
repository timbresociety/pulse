# Pulse Backend Architecture

## Core Rule

Markets are finite-universe markets. A market is publishable only when an admin
supplies a mutually exclusive and collectively exhaustive object list for the
market scope, tied to a source of record.

Completeness cannot be proven by code alone, so the product requires a source
URL, source freshness date, scope statement, and coverage statement. Mechanical
validation enforces the pieces the server can prove:

- at least three active objects
- no duplicate canonical object names
- no alias collision across different canonical objects
- every market object matches the market category and object type
- a persisted `market_universes` record with source metadata and object hash

## Data Model

- `users`: cloud-backed identity, username, coins, pulse score, admin flag.
- `categories`: browseable market categories.
- `objects`: canonical market answers scoped by category and object type.
- `object_aliases`: alternate spellings and common names for retrieval.
- `markets`: prompts, category, object type, open/close/settlement timestamps.
- `market_objects`: finite answer universe for a market.
- `market_universes`: source name, URL, scope, coverage, freshness, object count,
  and coverage hash for the market universe.
- `predictions`: one user call per market, settlement outcome, payout, and pulse
  delta.
- `email_login_challenges`: one-use code and magic-link digests.

All runtime data is stored through `DATABASE_URL`, which should point at managed
Postgres in production.

## Retrieval

Search is market-restricted. The resolver joins `market_objects` to `objects`
and `object_aliases`, normalizes the query, and ranks only objects in that
market's universe. There is no global "anything on the internet" fallback at
lock time, because that would let users select objects outside the declared
market scope.

For source freshness, the admin workflow captures `source_updated_at` and
coverage text at creation time. For high-churn markets, create a new market from
an updated source snapshot rather than mutating an active universe after calls
have been locked.

## Settlement

Markets settle after `closes_at`. Settlement reads real `predictions` rows:

- winner is the most-called object in the market
- ties break deterministically by earliest locked call, then object id
- gross pool is `prediction_count * ENTRY_COST`
- distributable pool is gross pool less platform rake
- winners split the distributable pool
- all prediction outcomes, payouts, and pulse deltas are persisted
- the market stores `winning_object_id`, `status=settled`, and `settled_at`

Standings, wallet history, feed counts, and reveal data derive from these same
persisted rows.

## Admin Access

Admin access is email allowlist based. `ADMIN_EMAILS` defaults to
`luckyloot786@gmail.com`. Admin users see the market creation screen in the app
after authentication and username onboarding.
