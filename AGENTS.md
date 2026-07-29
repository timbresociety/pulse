# Production safety

- Do not deploy to production while implementing or reviewing a change.
- Never deploy an uncommitted or untracked working tree.
- Use a Vercel preview deployment for ordinary validation.
- A production release requires an explicit production-release request from the
  user in the current turn.
- Production releases must run `scripts/deploy-production.sh`; do not invoke
  `vercel deploy --prod`, `vercel promote`, `vercel alias`, or `vercel rollback`
  directly.
- The release script must pass backend tests, the frontend production build,
  and smoke tests against the unaliased production build before it changes the
  live domain.
- Database migrations and catalog seeding are release operations. Keep
  `INITIALIZE_DATABASE=false` and `SEED_DATABASE=false` in production so a
  serverless cold start never performs DDL or catalog writes.
